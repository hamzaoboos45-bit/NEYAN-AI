"""Chat persistence and forming-trip fallback regressions."""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    original_path = config.DATABASE_PATH
    config.DATABASE_PATH = path
    try:
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as test_client:
            yield test_client
    finally:
        config.DATABASE_PATH = original_path
        if os.path.exists(path):
            os.remove(path)


def login(client, user_id=1, session_id=None):
    from backend.security.csrf import SESSION_KEY
    token = "chat-persistence-token"
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["role"] = "customer"
        if session_id:
            sess["session_id"] = session_id
        sess[SESSION_KEY] = token
    return token


def chat(client, token, message):
    response = client.post("/api/chat", json={"message": message, "csrf_token": token})
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def test_history_is_persisted_restored_and_user_bound(client):
    token = login(client, user_id=1)
    posted = chat(client, token, "مرحبا")
    initial = client.get("/api/chat/history")
    assert initial.status_code == 200
    payload = initial.get_json()
    assert payload["session_id"] == posted["session_id"]
    assert [(message["sender"], message["message_text"]) for message in payload["messages"]][0] == ("user", "مرحبا")
    assert len(payload["messages"]) == 2

    # Simulate a normal signed-session recreation.  The server resolves the
    # same user's latest transcript without accepting a client-supplied ID.
    with client.session_transaction() as sess:
        sess.pop("session_id", None)
    restored = client.get("/api/chat/history").get_json()
    assert restored["session_id"] == posted["session_id"]
    assert restored["messages"] == payload["messages"]

    login(client, user_id=2)
    other_user = client.get("/api/chat/history").get_json()
    assert other_user["messages"] == []
    assert other_user["session_id"] != posted["session_id"]


def test_reset_creates_a_fresh_empty_visible_conversation(client):
    token = login(client, user_id=1)
    original_id = chat(client, token, "مرحبا")["session_id"]
    reset = client.post("/api/chat/reset", json={"csrf_token": token})
    assert reset.status_code == 200
    assert reset.get_json()["session_id"] != original_id
    current = client.get("/api/chat/history").get_json()
    assert current["messages"] == []


def test_no_scheduled_trip_offers_then_creates_forming_request_only_after_confirmation(client):
    token = login(client, user_id=1)
    chat(client, token, "اريد حجز رحلة من عمان الى العقبة")
    chat(client, token, "2030-07-01")
    chat(client, token, "لشخصين")
    offer = chat(client, token, "اقتصادي")["reply"]
    assert "طلب رحلة" in offer and "حجز" in offer

    from database.db import get_db_connection
    conn = get_db_connection()
    assert conn.execute("SELECT COUNT(*) AS count FROM trip_requests").fetchone()["count"] == 0
    conn.close()

    choice = chat(client, token, "نعم")["reply"]
    assert "مشترك" in choice and "خاص" in choice
    confirmation = chat(client, token, "خاص")["reply"]
    assert "هل تريد إنشاء" in confirmation
    completed = chat(client, token, "نعم")["reply"]
    assert "تم إنشاء طلب الرحلة" in completed
    conn = get_db_connection()
    row = conn.execute("SELECT minimum_passengers, maximum_passengers FROM trip_requests").fetchone()
    conn.close()
    assert (row["minimum_passengers"], row["maximum_passengers"]) == (12, 45)


def test_compatible_forming_trip_is_never_joined_until_explicit_confirmation(client):
    from backend.transportation.trip_request_service import TripRequestService
    token = login(client, user_id=1)
    TripRequestService.create(2, {
        "from_city": "عمان", "to_city": "العقبة", "requested_date": "2030-07-01",
        "requested_time_start": "", "requested_time_end": "", "desired_vehicle_type": "bus",
        "desired_trip_class": "economy", "passenger_quantity": 2, "sharing_mode": "shared",
    })
    chat(client, token, "اريد حجز رحلة من عمان الى العقبة")
    chat(client, token, "2030-07-01")
    chat(client, token, "لشخصين")
    offer = chat(client, token, "اقتصادي")["reply"]
    assert "هل تريد الانضمام" in offer

    from database.db import get_db_connection
    conn = get_db_connection()
    assert conn.execute("SELECT COUNT(*) AS count FROM trip_request_members WHERE user_id=1").fetchone()["count"] == 0
    conn.close()
    joined = chat(client, token, "نعم")["reply"]
    assert "تم الانضمام" in joined
    conn = get_db_connection()
    assert conn.execute("SELECT passenger_quantity FROM trip_request_members WHERE user_id=1").fetchone()["passenger_quantity"] == 2
    conn.close()


def test_arabic_destination_context_and_unrelated_flow_switch_are_safe(client):
    token = login(client, user_id=1)
    first = chat(client, token, "بدي اروح العقبة بكرا")["reply"]
    assert "من أي مدينة" in first
    second = chat(client, token, "من عمان")["reply"]
    # Aqaba and tomorrow were retained, so the assistant asks only for
    # passengers rather than restarting the route/date collection.
    assert "مقاعد" in second
    maintenance = chat(client, token, "بدي صيانة")["reply"]
    assert "صيانة" in maintenance or "الخدمة" in maintenance


def test_time_and_class_correction_replace_existing_booking_context(client):
    token = login(client, user_id=1, session_id="correction-session")
    from backend.chatbot import ChatbotEngine
    from backend import states
    engine = ChatbotEngine("correction-session", user_id=1)
    engine.memory.update(states.STATE_BOOKING_COMPANY, {
        "from_city": "عمان", "to_city": "العقبة", "date": "2030-07-01",
        "time": "06:00", "seats": 2, "trip_class": "economy", "available_companies": [],
    })
    chat(client, token, "لا قصدي الساعة 8")
    chat(client, token, "خليها VIP")
    context = ChatbotEngine("correction-session", user_id=1).memory.get_context_dict()
    assert context["time"] == "08:00"
    assert context["trip_class"] == "vip"
