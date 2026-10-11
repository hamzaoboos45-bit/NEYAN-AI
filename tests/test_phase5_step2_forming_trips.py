"""Focused Phase 5 Step 2 tests for the isolated forming-trip foundation."""

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


def _identity(client, user_id, role="customer"):
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["role"] = role
        session["user_name"] = "Demand Test"
        session["company_id"] = None
        session["_csrf_token"] = "phase5-test-token"


def _headers():
    return {"X-CSRFToken": "phase5-test-token"}


def _payload(**changes):
    payload = {
        "from_city": "Amman", "to_city": "Aqaba",
        "requested_date": (date.today() + timedelta(days=30)).isoformat(),
        "requested_time_start": "10:00", "requested_time_end": "12:00",
        "passenger_quantity": 2, "desired_vehicle_type": "bus",
        "desired_trip_class": "economy", "sharing_mode": "shared",
    }
    payload.update(changes)
    return payload


def _create(client, **changes):
    return client.post("/api/trip-requests", json=_payload(**changes), headers=_headers())


def test_schema_is_additive_and_enforces_request_member_constraints(client):
    conn = get_db_connection()
    try:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"trip_requests", "trip_request_members", "trips", "bookings", "reviews"}.issubset(tables)
        indexes = {row["name"] for row in conn.execute("PRAGMA index_list('trip_requests')")}
        assert {"idx_trip_requests_compatibility", "idx_trip_requests_assigned_status", "idx_trip_requests_expiry_status"}.issubset(indexes)
        with pytest.raises(Exception):
            conn.execute("INSERT INTO trip_request_members (request_id, user_id, passenger_quantity) VALUES (999, 1, 0)")
    finally:
        conn.close()


def test_customer_create_atomically_creates_creator_membership_and_normalizes_cities(client):
    _identity(client, 1)
    response = _create(client)
    assert response.status_code == 201
    card = response.get_json()["data"]
    assert card["from_city"] == "عمان" and card["to_city"] == "العقبة"
    assert card["current_passengers"] == 2
    assert card["minimum_passengers"] == config.TRIP_REQUEST_DEFAULT_MIN_PASSENGERS
    assert card["maximum_passengers"] == config.TRIP_REQUEST_DEFAULT_MAX_PASSENGERS
    assert card["is_member"] and card["is_creator"]
    conn = get_db_connection()
    try:
        member = conn.execute("SELECT passenger_quantity, member_status FROM trip_request_members WHERE request_id=? AND user_id=1", (card["request_id"],)).fetchone()
        assert dict(member) == {"passenger_quantity": 2, "member_status": "active"}
    finally:
        conn.close()


@pytest.mark.parametrize("field,value", [("passenger_quantity", 0), ("requested_time_end", "09:00")])
def test_create_rejects_invalid_quantity_or_time_window(client, field, value):
    _identity(client, 1)
    response = _create(client, **{field: value})
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] in {"invalid_field", "invalid_time_window"}


@pytest.mark.parametrize("field", ["creator_user_id", "assigned_company_id", "status", "minimum_passengers"])
def test_create_rejects_client_authority_fields(client, field):
    _identity(client, 1)
    response = _create(client, **{field: 99})
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "forbidden_field"


def test_customer_only_and_csrf_are_enforced(client):
    _identity(client, 1, "super_admin")
    assert _create(client).status_code == 403
    _identity(client, 1)
    assert client.post("/api/trip-requests", json=_payload()).status_code == 400


def test_compatible_requests_are_surfaced_and_never_silently_merged(client):
    _identity(client, 1)
    first = _create(client)
    assert first.status_code == 201
    _identity(client, 2)
    duplicate = _create(client)
    assert duplicate.status_code == 409
    error = duplicate.get_json()["error"]
    assert error["code"] == "compatible_request_exists"
    assert error["details"]["compatible_requests"][0]["request_id"] == first.get_json()["data"]["request_id"]
    response = client.get("/api/trip-requests/compatible?from=Amman&to=Aqaba&date=" + _payload()["requested_date"] + "&time_start=10:00&time_end=12:00&vehicle=bus&class=economy")
    assert response.status_code == 200 and len(response.get_json()["data"]) == 1


def test_join_boundaries_capacity_and_duplicate_protection(client):
    _identity(client, 1)
    request_id = _create(client, passenger_quantity=11).get_json()["data"]["request_id"]
    _identity(client, 2)
    joined = client.post(f"/api/trip-requests/{request_id}/join", json={"passenger_quantity": 1}, headers=_headers())
    assert joined.status_code == 200
    assert joined.get_json()["data"]["status"] == "minimum_reached"
    assert client.post(f"/api/trip-requests/{request_id}/join", json={"passenger_quantity": 1}, headers=_headers()).get_json()["error"]["code"] == "already_member"
    _identity(client, 3)
    full = client.post(f"/api/trip-requests/{request_id}/join", json={"passenger_quantity": 33}, headers=_headers())
    assert full.status_code == 200 and full.get_json()["data"]["current_passengers"] == 45
    _identity(client, 4)
    over = client.post(f"/api/trip-requests/{request_id}/join", json={"passenger_quantity": 1}, headers=_headers())
    assert over.status_code == 409 and over.get_json()["error"]["code"] == "capacity_exceeded"


def test_leave_rejoin_and_creator_cancel_semantics(client):
    _identity(client, 1)
    request_id = _create(client, passenger_quantity=8).get_json()["data"]["request_id"]
    _identity(client, 2)
    assert client.post(f"/api/trip-requests/{request_id}/join", json={"passenger_quantity": 4}, headers=_headers()).get_json()["data"]["status"] == "minimum_reached"
    left = client.post(f"/api/trip-requests/{request_id}/leave", headers=_headers())
    assert left.status_code == 200 and left.get_json()["data"]["status"] == "collecting"
    rejoined = client.post(f"/api/trip-requests/{request_id}/join", json={"passenger_quantity": 4}, headers=_headers())
    assert rejoined.status_code == 200 and rejoined.get_json()["data"]["status"] == "minimum_reached"
    _identity(client, 1)
    assert client.post(f"/api/trip-requests/{request_id}/leave", headers=_headers()).get_json()["error"]["code"] == "creator_must_cancel"
    cancelled = client.post(f"/api/trip-requests/{request_id}/cancel", headers=_headers())
    assert cancelled.status_code == 200 and cancelled.get_json()["data"]["status"] == "cancelled"
    _identity(client, 3)
    assert client.post(f"/api/trip-requests/{request_id}/join", json={"passenger_quantity": 1}, headers=_headers()).get_json()["error"]["code"] == "not_joinable"


def test_non_creator_cannot_cancel_and_my_contract_has_no_other_member_pii(client):
    _identity(client, 1)
    request_id = _create(client).get_json()["data"]["request_id"]
    _identity(client, 2)
    assert client.post(f"/api/trip-requests/{request_id}/cancel", headers=_headers()).status_code == 403
    card = client.get("/api/trip-requests").get_json()["data"][0]
    assert card["is_member"] is False
    forbidden = {"members", "user_id", "creator_user_id", "email", "phone", "booking_id"}
    assert not forbidden.intersection(card)
    mine = client.get("/api/trip-requests/mine")
    assert mine.status_code == 200 and mine.get_json()["data"] == []


def test_expiration_is_authoritative_on_reads_and_mutations(client):
    _identity(client, 1)
    request_id = _create(client).get_json()["data"]["request_id"]
    conn = get_db_connection()
    try:
        conn.execute("UPDATE trip_requests SET expires_at='2000-01-01 00:00:00' WHERE request_id=?", (request_id,))
        conn.commit()
    finally:
        conn.close()
    assert client.get("/api/trip-requests").get_json()["data"] == []
    _identity(client, 2)
    response = client.post(f"/api/trip-requests/{request_id}/join", json={"passenger_quantity": 1}, headers=_headers())
    assert response.status_code == 409 and response.get_json()["error"]["code"] == "not_joinable"
    conn = get_db_connection()
    try:
        assert conn.execute("SELECT status FROM trip_requests WHERE request_id=?", (request_id,)).fetchone()["status"] == "expired"
    finally:
        conn.close()


def test_existing_operational_data_is_not_touched_by_forming_trip_actions(client):
    _identity(client, 1)
    conn = get_db_connection()
    try:
        before = conn.execute("SELECT COUNT(*) AS n FROM trips").fetchone()["n"], conn.execute("SELECT COUNT(*) AS n FROM bookings").fetchone()["n"]
    finally:
        conn.close()
    assert _create(client).status_code == 201
    conn = get_db_connection()
    try:
        after = conn.execute("SELECT COUNT(*) AS n FROM trips").fetchone()["n"], conn.execute("SELECT COUNT(*) AS n FROM bookings").fetchone()["n"]
        assert after == before
    finally:
        conn.close()


def test_documented_api_demand_progression_to_minimum_back_to_collecting_and_full(client):
    """The Phase 5 report scenario is exercised through the real API/service."""
    conn = get_db_connection()
    try:
        conn.execute(
            """INSERT INTO users (user_id, full_name, email, password_hash, role, status)
               VALUES (5, 'Demand Five', 'demand-five@example.jo', 'not-used-in-test', 'user', 'active')"""
        )
        conn.commit()
    finally:
        conn.close()

    _identity(client, 1)
    request_id = _create(client, passenger_quantity=2).get_json()["data"]["request_id"]
    _identity(client, 2)
    assert client.post(f"/api/trip-requests/{request_id}/join", json={"passenger_quantity": 3}, headers=_headers()).get_json()["data"]["current_passengers"] == 5
    _identity(client, 3)
    assert client.post(f"/api/trip-requests/{request_id}/join", json={"passenger_quantity": 2}, headers=_headers()).get_json()["data"]["current_passengers"] == 7
    _identity(client, 4)
    reached = client.post(f"/api/trip-requests/{request_id}/join", json={"passenger_quantity": 5}, headers=_headers()).get_json()["data"]
    assert (reached["current_passengers"], reached["status"]) == (12, "minimum_reached")
    _identity(client, 3)
    lowered = client.post(f"/api/trip-requests/{request_id}/leave", headers=_headers()).get_json()["data"]
    assert (lowered["current_passengers"], lowered["status"]) == (10, "collecting")
    assert client.post(f"/api/trip-requests/{request_id}/join", json={"passenger_quantity": 2}, headers=_headers()).get_json()["data"]["current_passengers"] == 12
    _identity(client, 5)
    full = client.post(f"/api/trip-requests/{request_id}/join", json={"passenger_quantity": 33}, headers=_headers()).get_json()["data"]
    assert (full["current_passengers"], full["status"], full["remaining_capacity"]) == (45, "minimum_reached", 0)
