"""Critical final runtime-flow regression coverage."""

import os
import re
import sys
import tempfile

import bcrypt
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config


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


def _login_customer(client, user_id=1, session_id="critical-flow"):
    from backend.security.csrf import SESSION_KEY

    token = "critical-flow-csrf"
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["role"] = "customer"
        session["session_id"] = session_id
        session[SESSION_KEY] = token
    return token


def _chat(client, token, message):
    response = client.post("/api/chat", json={"message": message, "csrf_token": token})
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()["reply"]


def _insert_shared_policy():
    from database.db import get_db_connection

    conn = get_db_connection()
    try:
        conn.execute(
            """INSERT INTO transport_pricing_policies
               (from_city, to_city, vehicle_type, trip_class, base_trip_price_fils, is_active)
               VALUES ('عمان', 'العقبة', 'bus', 'economy', 25000, 1)"""
        )
        conn.commit()
    finally:
        conn.close()


def test_fully_prefilled_no_trip_uses_forming_fallback_before_any_write_and_discloses_policy_price(client):
    from backend import states
    from backend.chatbot import ChatbotEngine
    from database.db import get_db_connection

    _insert_shared_policy()
    token = _login_customer(client)
    reply = _chat(client, token, "اريد حجز رحلة من عمان الى العقبة بتاريخ 2030-07-01 لشخصين اقتصادي")
    assert "طلب رحلة" in reply
    assert "25.000" in reply
    assert "تعذر إكمال طلب الرحلة بأمان" not in reply
    assert ChatbotEngine("critical-flow", user_id=1).memory.get_state() == states.STATE_FORMING_MODE
    conn = get_db_connection()
    try:
        assert conn.execute("SELECT COUNT(*) FROM trip_requests").fetchone()[0] == 0
    finally:
        conn.close()


def test_declining_shared_option_offers_explicit_new_request_choice_without_writing(client):
    from backend import states
    from backend.chatbot import ChatbotEngine
    from backend.transportation.trip_request_service import TripRequestService
    from database.db import get_db_connection

    _insert_shared_policy()
    TripRequestService.create(2, {
        "from_city": "عمان", "to_city": "العقبة", "requested_date": "2030-07-01",
        "requested_time_start": "", "requested_time_end": "", "desired_vehicle_type": "bus",
        "desired_trip_class": "economy", "passenger_quantity": 2, "sharing_mode": "shared",
    })
    token = _login_customer(client)
    assert "هل تريد الانضمام" in _chat(client, token, "اريد حجز رحلة من عمان الى العقبة بتاريخ 2030-07-01 لشخصين اقتصادي")
    declined = _chat(client, token, "لا")
    assert "لن أنضم" in declined and "مشترك" in declined and "خاص" in declined
    assert ChatbotEngine("critical-flow", user_id=1).memory.get_state() == states.STATE_FORMING_MODE
    conn = get_db_connection()
    try:
        assert conn.execute("SELECT COUNT(*) FROM trip_request_members WHERE user_id=1").fetchone()[0] == 0
    finally:
        conn.close()


def test_maintenance_chat_confirmation_persists_through_shared_service(client):
    from database.db import get_db_connection

    token = _login_customer(client)
    for message in ("بدي صيانة", "تغيير زيت", "السيارة تحتاج تغيير زيت", "عمان", "2030-07-01"):
        _chat(client, token, message)
    reply = _chat(client, token, "نعم")
    assert "تم استلام طلب الصيانة" in reply
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT user_id, service_type FROM maintenance_requests ORDER BY request_id DESC LIMIT 1").fetchone()
        assert tuple(row) == (1, "oil_change")
    finally:
        conn.close()


def test_chat_domain_errors_are_specific_instead_of_the_old_generic_booking_error():
    from backend.chatbot import _forming_domain_error
    from backend.transportation.trip_request_service import TripRequestError

    reply = _forming_domain_error(TripRequestError("invalid_route", "test"))
    assert "مدينة الانطلاق" in reply
    assert "تعذر إكمال طلب الرحلة بأمان" not in reply


def test_first_real_login_redirect_and_home_payload_are_repeatable_for_an_empty_customer(client):
    from backend.security.credentials import hash_password
    from database.db import get_db_connection

    conn = get_db_connection()
    try:
        conn.execute(
            """INSERT INTO users (full_name, name, email, password_hash, role, status, is_active)
               VALUES ('Fresh Customer', 'Fresh Customer', 'fresh@example.test', ?, 'user', 'active', 1)""",
            (hash_password("FreshUser123"),),
        )
        conn.commit()
    finally:
        conn.close()
    login_page = client.get("/login").get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', login_page).group(1)
    response = client.post("/login", data={"csrf_token": token, "email": "fresh@example.test", "password": "FreshUser123"})
    assert response.status_code == 302 and response.headers["Location"].endswith("/home")
    first = client.get("/api/dashboard/home")
    refreshed = client.get("/api/dashboard/home")
    assert first.status_code == refreshed.status_code == 200
    assert first.get_json()["data"]["summary"] == refreshed.get_json()["data"]["summary"]


def test_local_super_admin_management_resets_hash_revokes_remember_tokens_and_only_lists_email(client):
    from backend.security.admin_bootstrap import provision_first_super_admin
    from backend.security.admin_management import list_super_admins, reset_super_admin_password
    from database.db import get_db_connection

    owner = provision_first_super_admin("Platform Owner", "owner@example.com", "OwnerPass123")
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO remember_tokens (selector, token_hash, user_id, expires_at) VALUES ('selector', 'hash', ?, '2030-01-01 00:00:00')", (owner.user_id,))
        conn.commit()
    finally:
        conn.close()
    identities = list_super_admins()
    assert [(item.user_id, item.email) for item in identities] == [(owner.user_id, "owner@example.com")]
    reset = reset_super_admin_password("OWNER@example.com", "NewOwnerPass123")
    assert reset.email == "owner@example.com"
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT password_hash FROM users WHERE user_id=?", (owner.user_id,)).fetchone()
        assert bcrypt.checkpw(b"NewOwnerPass123", row["password_hash"].encode("utf-8"))
        assert conn.execute("SELECT COUNT(*) FROM remember_tokens WHERE user_id=?", (owner.user_id,)).fetchone()[0] == 0
    finally:
        conn.close()
