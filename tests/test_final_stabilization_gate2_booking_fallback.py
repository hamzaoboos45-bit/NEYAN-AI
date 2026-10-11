"""Gate 2: real chat booking and forming-demand lifecycle verification.

Every scenario uses the Flask API plus an isolated SQLite database and then
asserts authoritative rows.  These tests intentionally do not mock the chat,
booking, pricing, or forming-trip services.
"""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config


FUTURE_DATE = "2099-07-01"


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    previous_path = config.DATABASE_PATH
    config.DATABASE_PATH = path
    try:
        from app import create_app

        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as test_client:
            yield test_client
    finally:
        config.DATABASE_PATH = previous_path
        if os.path.exists(path):
            os.remove(path)


def login(client, user_id=1, session_id="gate2-session"):
    from backend.security.csrf import SESSION_KEY

    token = f"gate2-token-{user_id}-{session_id}"
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["role"] = "customer"
        session["session_id"] = session_id
        session[SESSION_KEY] = token
    return token


def chat(client, token, message):
    response = client.post("/api/chat", json={"message": message, "csrf_token": token})
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()["reply"]


def db():
    from database.db import get_db_connection

    return get_db_connection()


def add_future_trip(*, route=("عمان", "إربد"), seats=5, price=9.0, company_id=1):
    conn = db()
    try:
        trip_id = conn.execute(
            """INSERT INTO trips
               (company_id, from_city, to_city, departure_time, arrival_time,
                vehicle_type, trip_class, total_seats, available_seats, price_jod, status)
               VALUES (?, ?, ?, ?, ?, 'bus', 'economy', ?, ?, ?, 'active')""",
            (company_id, route[0], route[1], f"{FUTURE_DATE} 10:00:00", f"{FUTURE_DATE} 13:00:00", seats, seats, price),
        ).lastrowid
        conn.commit()
        return trip_id
    finally:
        conn.close()


def add_request(user_id, *, route=("عمان", "العقبة"), quantity=2, sharing_mode="shared"):
    from backend.transportation.trip_request_service import TripRequestService

    return TripRequestService.create(user_id, {
        "from_city": route[0], "to_city": route[1], "requested_date": FUTURE_DATE,
        "requested_time_start": "", "requested_time_end": "", "desired_vehicle_type": "bus",
        "desired_trip_class": "economy", "passenger_quantity": quantity,
        "sharing_mode": sharing_mode,
    })


def begin_request(client, token, *, route=("عمان", "العقبة"), seats=2):
    return chat(
        client, token,
        f"اريد حجز رحلة من {route[0]} الى {route[1]} بتاريخ {FUTURE_DATE} لشخصين اقتصادي" if seats == 2
        else f"اريد حجز رحلة من {route[0]} الى {route[1]} بتاريخ {FUTURE_DATE} ل{seats} ركاب اقتصادي",
    )


def test_scheduled_chat_booking_uses_exact_trip_service_and_decrements_seats(client):
    trip_id = add_future_trip(seats=5, price=9.0)
    token = login(client, session_id="scheduled")

    offer = begin_request(client, token, route=("عمان", "إربد"))
    assert "الرحلات المتاحة" in offer
    assert "9.0" in offer
    assert "مقاعد" not in offer or "الرحلات" in offer
    assert "ملخص حجزك" in chat(client, token, "1")
    assert "تأكيد حجزك بنجاح" in chat(client, token, "نعم")

    conn = db()
    try:
        booking = conn.execute("SELECT user_id, trip_id, seats_booked, total_price, pricing_snapshot_fils FROM bookings WHERE trip_id=?", (trip_id,)).fetchone()
        trip = conn.execute("SELECT available_seats FROM trips WHERE trip_id=?", (trip_id,)).fetchone()
        assert tuple(booking) == (1, trip_id, 2, 18.0, 18000)
        assert trip["available_seats"] == 3
        assert conn.execute("SELECT COUNT(*) FROM bookings WHERE trip_id=?", (trip_id,)).fetchone()[0] == 1
    finally:
        conn.close()

    # A duplicate transport confirmation after the pending action was consumed
    # is idle chat, not a second mutation.
    chat(client, token, "نعم")
    conn = db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM bookings WHERE trip_id=?", (trip_id,)).fetchone()[0] == 1
    finally:
        conn.close()


def test_shared_fallback_excludes_private_and_creates_only_membership_after_confirmation(client):
    private = add_request(3, quantity=2, sharing_mode="private")
    shared = add_request(2, quantity=3, sharing_mode="shared")
    token = login(client, session_id="shared")

    offer = begin_request(client, token)
    assert "هل تريد الانضمام" in offer
    assert "sample" not in offer.lower()
    from backend.chatbot import ChatbotEngine
    assert ChatbotEngine("shared", user_id=1).memory.get_context_dict()["forming_request_id"] == shared["request_id"]
    conn = db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM trip_request_members WHERE request_id=? AND user_id=1", (shared["request_id"],)).fetchone()[0] == 0
    finally:
        conn.close()

    assert "تم الانضمام" in chat(client, token, "نعم")
    conn = db()
    try:
        member = conn.execute("SELECT passenger_quantity, member_status FROM trip_request_members WHERE request_id=? AND user_id=1", (shared["request_id"],)).fetchone()
        total = conn.execute("SELECT SUM(passenger_quantity) FROM trip_request_members WHERE request_id=? AND member_status='active'", (shared["request_id"],)).fetchone()[0]
        assert tuple(member) == (2, "active")
        assert total == 5
        assert conn.execute("SELECT COUNT(*) FROM bookings WHERE user_id=1").fetchone()[0] == 0
    finally:
        conn.close()

    chat(client, token, "نعم")
    conn = db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM trip_request_members WHERE request_id=? AND user_id=1", (shared["request_id"],)).fetchone()[0] == 1
    finally:
        conn.close()


def test_shared_rejection_offers_private_creation_with_creator_ownership_and_mine_listing(client):
    rejected = add_request(2, quantity=2, sharing_mode="shared")
    token = login(client, session_id="reject-create")

    assert "هل تريد الانضمام" in begin_request(client, token)
    declined = chat(client, token, "لا")
    assert "لن أنضم" in declined and "مشترك" in declined and "خاص" in declined
    assert "هل تريد إنشاء" in chat(client, token, "خاص")
    assert "تم إنشاء طلب الرحلة" in chat(client, token, "نعم")

    conn = db()
    try:
        created = conn.execute("SELECT request_id, creator_user_id, sharing_mode FROM trip_requests WHERE creator_user_id=1 ORDER BY request_id DESC LIMIT 1").fetchone()
        member = conn.execute("SELECT passenger_quantity, member_status FROM trip_request_members WHERE request_id=? AND user_id=1", (created["request_id"],)).fetchone()
        assert created["request_id"] != rejected["request_id"]
        assert tuple(created)[1:] == (1, "private")
        assert tuple(member) == (2, "active")
        assert conn.execute("SELECT COUNT(*) FROM trip_request_members WHERE request_id=? AND user_id=1", (rejected["request_id"],)).fetchone()[0] == 0
    finally:
        conn.close()
    listed = client.get("/api/trip-requests/mine").get_json()["data"]
    assert any(card["request_id"] == created["request_id"] and card["is_creator"] for card in listed)


def test_no_shared_match_and_private_only_match_offer_creation_without_private_disclosure(client):
    private = add_request(2, route=("عمان", "الزرقاء"), quantity=2, sharing_mode="private")
    token = login(client, session_id="private-only")

    offer = begin_request(client, token, route=("عمان", "الزرقاء"))
    assert "هل تريد الانضمام" not in offer
    assert "طلب رحلة جديد" in offer
    from backend.chatbot import ChatbotEngine
    assert "forming_request_id" not in ChatbotEngine("private-only", user_id=1).memory.get_context_dict()
    assert "هل تريد إنشاء" in chat(client, token, "خاص")
    assert "تم إنشاء طلب الرحلة" in chat(client, token, "نعم")
    conn = db()
    try:
        row = conn.execute("SELECT sharing_mode FROM trip_requests WHERE creator_user_id=1 ORDER BY request_id DESC LIMIT 1").fetchone()
        assert row["sharing_mode"] == "private"
    finally:
        conn.close()


def test_capacity_and_expiration_after_offer_fail_safely_without_membership_mutation(client):
    nearly_full = add_request(2, quantity=43, sharing_mode="shared")
    token = login(client, session_id="capacity")
    assert "هل تريد الانضمام" in begin_request(client, token)
    # The offer was valid for two seats.  Another customer fills the final
    # capacity before confirmation, exercising the authoritative join guard.
    from backend.transportation.trip_request_service import TripRequestService
    TripRequestService.join(3, nearly_full["request_id"], {"passenger_quantity": 2})
    reply = chat(client, token, "نعم")
    assert "السعة" in reply or "المتبقية" in reply
    conn = db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM trip_request_members WHERE request_id=? AND user_id=1", (nearly_full["request_id"],)).fetchone()[0] == 0
    finally:
        conn.close()

    expiring = add_request(2, route=("إربد", "العقبة"), quantity=2, sharing_mode="shared")
    token = login(client, session_id="expired")
    assert "هل تريد الانضمام" in begin_request(client, token, route=("إربد", "العقبة"))
    conn = db()
    try:
        conn.execute("UPDATE trip_requests SET expires_at='2000-01-01 00:00:00' WHERE request_id=?", (expiring["request_id"],))
        conn.commit()
    finally:
        conn.close()
    reply = chat(client, token, "نعم")
    assert "لم يعد متاح" in reply
    conn = db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM trip_request_members WHERE request_id=? AND user_id=1", (expiring["request_id"],)).fetchone()[0] == 0
        assert conn.execute("SELECT status FROM trip_requests WHERE request_id=?", (expiring["request_id"],)).fetchone()[0] == "expired"
    finally:
        conn.close()


def test_invalid_city_and_correction_are_safe_and_invalidate_stale_selection(client):
    token = login(client, session_id="city-correction")
    assert "مدينة" in chat(client, token, "اريد حجز رحلة")
    invalid = chat(client, token, "مدينة غير معروفة")
    assert "لم أتمكن من التعرف" in invalid
    assert "must be" not in invalid
    conn = db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM trip_requests").fetchone()[0] == 0
    finally:
        conn.close()

    from backend import states
    from backend.chatbot import ChatbotEngine
    engine = ChatbotEngine("city-correction", user_id=1)
    engine.memory.update(states.STATE_BOOKING_COMPANY, {
        "from_city": "عمان", "to_city": "العقبة", "date": FUTURE_DATE,
        "seats": 2, "trip_class": "economy", "selected_trip_id": 999,
        "available_companies": [{"trip_id": 999}],
    })
    chat(client, token, "لا قصدي إربد")
    context = ChatbotEngine("city-correction", user_id=1).memory.get_context_dict()
    assert context["to_city"] == "إربد"
    assert "selected_trip_id" not in context
    assert "available_companies" not in context


def test_booking_service_capacity_guard_remains_atomic_for_two_customers(client):
    from backend.transportation.booking_service import BookingError, BookingService

    trip_id = add_future_trip(route=("الزرقاء", "العقبة"), seats=1, price=7.5)
    first = BookingService.create(user_id=1, trip_id=trip_id, seats=1)
    assert first["trip_id"] == trip_id
    with pytest.raises(BookingError) as error:
        BookingService.create(user_id=2, trip_id=trip_id, seats=1)
    assert error.value.code == "capacity_exceeded"
    conn = db()
    try:
        assert conn.execute("SELECT available_seats FROM trips WHERE trip_id=?", (trip_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM bookings WHERE trip_id=?", (trip_id,)).fetchone()[0] == 1
    finally:
        conn.close()
