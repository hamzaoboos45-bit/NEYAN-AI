"""Phase 5 Step 4 assignment and company-decision security/lifecycle tests."""

from datetime import date, timedelta
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from database.db import get_db_connection


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


def _identity(client, user_id, role, company_id=None):
    with client.session_transaction() as session:
        session.update(user_id=user_id, role=role, company_id=company_id, user_name="Step 4 Test", _csrf_token="phase5-step4-token")


def _headers():
    return {"X-CSRFToken": "phase5-step4-token"}


def _create(client, passengers=12, days=30):
    _identity(client, 2, "customer")
    payload = {
        "from_city": "Amman", "to_city": "Aqaba",
        "requested_date": (date.today() + timedelta(days=days)).isoformat(),
        "requested_time_start": "10:00", "requested_time_end": "12:00",
        "passenger_quantity": passengers, "desired_vehicle_type": "bus", "desired_trip_class": "economy",
    }
    response = client.post("/api/trip-requests", json=payload, headers=_headers())
    assert response.status_code == 201
    return response.get_json()["data"]["request_id"]


def _assign(client, request_id, company_id=1):
    _identity(client, 1, "super_admin")
    return client.post(f"/api/admin/trip-requests/{request_id}/assign", json={"company_id": company_id}, headers=_headers())


def test_super_admin_queue_assignment_and_audit_metadata(client):
    request_id = _create(client)
    _identity(client, 1, "super_admin")
    queue = client.get("/api/admin/trip-requests")
    assert queue.status_code == 200 and queue.get_json()["data"][0]["request_id"] == request_id
    companies = client.get("/api/admin/transport-companies").get_json()["data"]
    assert companies and all(c["status"] == "active" for c in companies)
    assigned = _assign(client, request_id)
    assert assigned.status_code == 200
    card = assigned.get_json()["data"]
    assert card["assigned_company_id"] == 1 and card["company_decision"] == "pending" and card["assigned_at"]
    conn = get_db_connection()
    try:
        assert conn.execute("SELECT COUNT(*) FROM activity_logs WHERE action_type='admin_action'").fetchone()[0] == 1
    finally:
        conn.close()


def test_below_minimum_expired_and_inactive_company_cannot_be_assigned(client):
    below = _create(client, passengers=2)
    response = _assign(client, below)
    assert response.status_code == 409 and response.get_json()["error"]["code"] == "not_eligible"
    eligible = _create(client, days=31)
    conn = get_db_connection()
    try:
        conn.execute("UPDATE trip_requests SET expires_at='2000-01-01 00:00:00' WHERE request_id=?", (eligible,))
        inactive = conn.execute("INSERT INTO companies (name, name_ar, company_type, status) VALUES ('Inactive', 'Inactive', 'transport', 'inactive')").lastrowid
        conn.commit()
    finally:
        conn.close()
    assert _assign(client, eligible).status_code == 409
    fresh = _create(client, days=32)
    invalid = _assign(client, fresh, inactive)
    assert invalid.status_code == 400 and invalid.get_json()["error"]["code"] == "invalid_company"


def test_terminal_requests_and_forged_authority_fields_are_rejected(client):
    request_id = _create(client)
    _identity(client, 1, "super_admin")
    forged = client.post(
        f"/api/admin/trip-requests/{request_id}/assign",
        json={"company_id": 1, "status": "converted", "converted_trip_id": 1}, headers=_headers(),
    )
    assert forged.status_code == 400 and forged.get_json()["error"]["code"] == "invalid_assignment_payload"

    cancelled = _create(client, days=33)
    _identity(client, 2, "customer")
    assert client.post(f"/api/trip-requests/{cancelled}/cancel", headers=_headers()).status_code == 200
    assert _assign(client, cancelled).status_code == 409

    expiring = _create(client, days=34)
    assert _assign(client, expiring).status_code == 200
    conn = get_db_connection()
    try:
        conn.execute("UPDATE trip_requests SET expires_at='2000-01-01 00:00:00' WHERE request_id=?", (expiring,))
        conn.commit()
    finally:
        conn.close()
    _identity(client, 4, "company_admin", 1)
    expired = client.post(f"/api/company/trip-requests/{expiring}/accept", json={}, headers=_headers())
    assert expired.status_code == 409 and expired.get_json()["error"]["code"] == "not_eligible"


def test_rbac_company_isolation_and_csrf(client):
    request_id = _create(client)
    _identity(client, 2, "customer")
    assert client.post(f"/api/admin/trip-requests/{request_id}/assign", json={"company_id": 1}, headers=_headers()).status_code == 403
    _identity(client, 4, "company_admin", 1)
    assert client.post(f"/api/admin/trip-requests/{request_id}/assign", json={"company_id": 1}, headers=_headers()).status_code == 403
    assert client.post(f"/api/admin/trip-requests/{request_id}/assign", json={"company_id": 1}).status_code == 400
    assert _assign(client, request_id).status_code == 200
    _identity(client, 3, "company_admin", 2)
    assert client.get("/api/company/trip-requests").get_json()["data"] == []
    assert client.post(f"/api/company/trip-requests/{request_id}/accept", json={}, headers=_headers()).status_code == 403
    _identity(client, 4, "company_admin", 1)
    assert client.get("/api/company/trip-requests").get_json()["data"][0]["request_id"] == request_id


def test_acceptance_is_not_conversion_and_freezes_customer_membership(client):
    request_id = _create(client)
    assert _assign(client, request_id).status_code == 200
    conn = get_db_connection()
    try:
        before = (conn.execute("SELECT COUNT(*) FROM trips").fetchone()[0], conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0], conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0])
    finally:
        conn.close()
    _identity(client, 4, "company_admin", 1)
    accepted = client.post(f"/api/company/trip-requests/{request_id}/accept", json={}, headers=_headers())
    assert accepted.status_code == 200 and accepted.get_json()["data"]["company_decision"] == "accepted"
    assert client.post(f"/api/company/trip-requests/{request_id}/accept", json={}, headers=_headers()).status_code == 409
    _identity(client, 3, "customer")
    frozen = client.post(f"/api/trip-requests/{request_id}/join", json={"passenger_quantity": 1}, headers=_headers())
    assert frozen.status_code == 409 and frozen.get_json()["error"]["code"] == "request_frozen"
    conn = get_db_connection()
    try:
        assert before == (conn.execute("SELECT COUNT(*) FROM trips").fetchone()[0], conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0], conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0])
    finally:
        conn.close()


def test_rejection_returns_to_assignment_queue_and_reassignment_is_audited(client):
    request_id = _create(client)
    assert _assign(client, request_id, 1).status_code == 200
    _identity(client, 4, "company_admin", 1)
    rejected = client.post(f"/api/company/trip-requests/{request_id}/reject", json={}, headers=_headers())
    assert rejected.status_code == 200
    card = rejected.get_json()["data"]
    assert card["company_decision"] == "rejected" and card["assigned_company_id"] is None
    _identity(client, 1, "super_admin")
    assert client.get("/api/admin/trip-requests").get_json()["data"][0]["company_decision"] == "rejected"
    reassigned = _assign(client, request_id, 2)
    assert reassigned.status_code == 200 and reassigned.get_json()["data"]["assigned_company_id"] == 2


def test_admin_ui_contract_is_localized_aggregate_only_and_uses_dashboard_scope(client):
    _identity(client, 1, "super_admin")
    html = client.get("/admin").get_data(as_text=True)
    assert "demandAdminQueue" in html and "admin-forming-trips.js" in html
    source = open(os.path.join(os.path.dirname(__file__), "..", "frontend", "static", "js", "admin-forming-trips.js"), encoding="utf-8").read()
    assert "Forming Trip Requests" in source and "طلبات الرحلات قيد الاكتمال" in source
    assert "/api/admin/trip-requests" in source and "/api/company/trip-requests" in source
    assert "innerHTML" not in source and "textContent" in source
    for prohibited in ("email", "phone", "user_id", "booking_id", "members"):
        assert prohibited not in source
