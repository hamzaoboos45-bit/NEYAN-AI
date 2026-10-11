"""Phase 6 regressions: ownership, exact-trip selection, and API hardening."""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config


TEST_TRIP_DATE = "2099-07-01"


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
        # This fixture preserves the historical trip IDs while making its
        # deliberate booking candidates future departures.
        from database.db import get_db_connection
        conn = get_db_connection()
        try:
            conn.execute("UPDATE trips SET departure_time=replace(departure_time, '2025-07-01', ?), arrival_time=replace(arrival_time, '2025-07-01', ?)", (TEST_TRIP_DATE, TEST_TRIP_DATE))
            conn.commit()
        finally:
            conn.close()
        with app.test_client() as test_client:
            yield test_client
    finally:
        config.DATABASE_PATH = original_path
        if os.path.exists(path):
            os.remove(path)


def login_customer(client, user_id=2, session_id="phase6-session"):
    from backend.security.csrf import SESSION_KEY
    token = "phase6-csrf-token"
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["role"] = "customer"
        sess["session_id"] = session_id
        sess[SESSION_KEY] = token
    return token


def chat(client, token, message):
    response = client.post("/api/chat", json={"message": message, "csrf_token": token})
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()["reply"]


def complete_booking(client, token, option="1"):
    chat(client, token, "اريد حجز رحلة")
    chat(client, token, "عمان")
    chat(client, token, "اربد")
    chat(client, token, TEST_TRIP_DATE)
    chat(client, token, "1")
    chat(client, token, "اقتصادي")
    chat(client, token, option)
    return chat(client, token, "نعم")


def test_chat_booking_is_owned_and_keeps_exact_selected_trip(client):
    token = login_customer(client)
    assert "تأكيد" in complete_booking(client, token, option="2")

    from database.db import get_db_connection
    conn = get_db_connection()
    booking = conn.execute(
        "SELECT user_id, trip_id FROM bookings ORDER BY booking_id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert booking["user_id"] == 2
    # The second displayed economy option is the 11:00 trip, not the first
    # company/route match. This guards against an ambiguous second lookup.
    assert booking["trip_id"] == 3


def test_chat_booking_honours_explicit_departure_time(client):
    token = login_customer(client)
    chat(client, token, f"اريد حجز رحلة من عمان الى اربد بتاريخ {TEST_TRIP_DATE} الساعة 11 لشخصين")
    chat(client, token, "اقتصادي")
    chat(client, token, "1")
    complete = chat(client, token, "نعم")
    assert "تأكيد" in complete

    from database.db import get_db_connection
    conn = get_db_connection()
    booking = conn.execute("SELECT trip_id, user_id FROM bookings ORDER BY booking_id DESC LIMIT 1").fetchone()
    conn.close()
    assert booking["trip_id"] == 3
    assert booking["user_id"] == 2


def test_chat_maintenance_request_is_owned(client):
    token = login_customer(client)
    chat(client, token, "بدي صيانة")
    chat(client, token, "تغيير زيت")
    chat(client, token, "المحرك يصدر صوتاً")
    chat(client, token, "عمان")
    chat(client, token, TEST_TRIP_DATE)
    assert "تم استلام" in chat(client, token, "نعم")

    from database.db import get_db_connection
    conn = get_db_connection()
    request = conn.execute(
        "SELECT user_id, service_type FROM maintenance_requests ORDER BY request_id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert request["user_id"] == 2
    assert request["service_type"] == "oil_change"


def test_chat_rejects_bad_messages_before_processing(client):
    token = login_customer(client)
    headers = {"X-CSRFToken": token}
    for payload, code in [
        ({"message": "   "}, "empty_message"),
        ({"message": 12}, "invalid_message"),
        ({"message": "x" * (config.CHAT_MAX_MESSAGE_LENGTH + 1)}, "message_too_long"),
        ({}, "missing_message"),
    ]:
        response = client.post("/api/chat", json=payload, headers=headers)
        assert response.status_code == 400
        assert response.get_json()["code"] == code


def test_chat_rejects_malformed_json(client):
    token = login_customer(client)
    response = client.post(
        "/api/chat",
        data="{not json",
        content_type="application/json",
        headers={"X-CSRFToken": token},
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_json"


def test_chat_rate_limit_returns_structured_429(client):
    token = login_customer(client)
    old_user_limit, old_ip_limit = config.CHAT_RATE_LIMIT_USER_REQUESTS, config.CHAT_RATE_LIMIT_IP_REQUESTS
    config.CHAT_RATE_LIMIT_USER_REQUESTS = 1
    config.CHAT_RATE_LIMIT_IP_REQUESTS = 1
    try:
        chat(client, token, "مرحبا")
        response = client.post("/api/chat", json={"message": "مرحبا", "csrf_token": token})
    finally:
        config.CHAT_RATE_LIMIT_USER_REQUESTS = old_user_limit
        config.CHAT_RATE_LIMIT_IP_REQUESTS = old_ip_limit
    assert response.status_code == 429
    assert response.get_json()["code"] == "rate_limited"


def test_conversation_owned_by_another_user_is_not_reused(client):
    token = login_customer(client, user_id=2, session_id="owned-session")
    chat(client, token, "اريد حجز رحلة")

    # Simulate a different authenticated identity with a stale browser session
    # identifier. The route must make a fresh conversation instead of reading
    # user 2's booking state.
    token = login_customer(client, user_id=3, session_id="owned-session")
    response = client.post("/api/chat", json={"message": "مرحبا", "csrf_token": token})
    assert response.status_code == 200
    assert response.get_json()["session_id"] != "owned-session"
    assert "من أي مدينة" not in response.get_json()["reply"]


def test_dual_passenger_form_is_kept_when_provided_before_date(client):
    token = login_customer(client)
    chat(client, token, "اريد حجز رحلة من عمان الى اربد")
    chat(client, token, "لشخصين")
    reply = chat(client, token, TEST_TRIP_DATE)
    assert "درجة" in reply
