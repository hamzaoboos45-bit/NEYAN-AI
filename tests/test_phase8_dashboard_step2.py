"""Phase 8 Step 2: customer home dashboard, discovery, and role-routing tests."""

import json
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


def _identity(client, user_id, role="customer", company_id=None):
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["role"] = role
        session["company_id"] = company_id
        session["user_name"] = "Dashboard Test"


def _home_data(client):
    response = client.get("/api/dashboard/home")
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()["data"]


def _insert_trip(conn, company_id=1, departure="2099-01-01 08:00"):
    cursor = conn.execute(
        """
        INSERT INTO trips (company_id, from_city, to_city, departure_time, arrival_time,
                           vehicle_type, trip_class, total_seats, available_seats, price_jod, status)
        VALUES (?, 'عمان', 'إربد', ?, '2099-01-01 10:00', 'bus', 'economy', 30, 12, 5.50, 'active')
        """,
        (company_id, departure),
    )
    return cursor.lastrowid


def _insert_booking(conn, user_id, trip_id, booked_at="2098-01-01 09:00", status="confirmed"):
    cursor = conn.execute(
        """
        INSERT INTO bookings (user_id, trip_id, seats_booked, total_price, status,
                              payment_status, passenger_name, booked_at)
        VALUES (?, ?, 1, 5.50, ?, 'paid', 'Private Passenger', ?)
        """,
        (user_id, trip_id, status, booked_at),
    )
    return cursor.lastrowid


def test_customer_home_page_and_private_endpoint_require_customer_access(client):
    assert client.get("/api/dashboard/home").status_code == 401
    _identity(client, 2)
    assert client.get("/home").status_code == 200
    assert b"homeDashboardContent" in client.get("/home").data

    _identity(client, 1, "super_admin")
    assert client.get("/api/dashboard/home").status_code == 403


def test_home_role_routing_sends_admins_to_their_dashboard(client):
    _identity(client, 1, "super_admin")
    response = client.get("/home")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin")

    _identity(client, 4, "company_admin", company_id=1)
    response = client.get("/home")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin")


def test_customer_home_returns_only_own_booking_and_maintenance_data(client):
    _identity(client, 2)
    data = _home_data(client)
    recent_ids = {row["booking_id"] for row in data["recent_bookings"]}
    assert 2 not in recent_ids  # Seed booking #2 belongs to user 3.
    assert data["summary"]["total_bookings"] == 2
    serialized = json.dumps(data)
    assert "Private Passenger" not in serialized
    assert "passenger_name" not in serialized
    assert "customer_phone" not in serialized


def test_upcoming_booking_uses_real_datetime_boundary_and_correct_user(client):
    conn = get_db_connection()
    try:
        past_trip = _insert_trip(conn, departure="1999-01-01 08:00")
        near_trip = _insert_trip(conn, departure="2099-01-01 08:00")
        later_trip = _insert_trip(conn, departure="2100-01-01 08:00")
        _insert_booking(conn, 2, past_trip)
        expected_booking = _insert_booking(conn, 2, near_trip)
        _insert_booking(conn, 2, later_trip)
        _insert_booking(conn, 3, near_trip)
        conn.commit()
    finally:
        conn.close()

    _identity(client, 2)
    data = _home_data(client)
    assert data["next_booking"]["booking_id"] == expected_booking
    assert data["next_booking"]["departure_time"] == "2099-01-01 08:00"
    assert data["summary"]["upcoming_bookings"] == 2


def test_user_with_no_upcoming_data_receives_professional_empty_contract(client):
    _identity(client, 4)
    data = _home_data(client)
    assert data["summary"] == {
        "total_bookings": 0,
        "pending_bookings": 0,
        "confirmed_bookings": 0,
        "total_maintenance_requests": 0,
        "upcoming_bookings": 0,
    }
    assert data["next_booking"] is None
    assert data["recent_bookings"] == []
    assert data["latest_maintenance"] is None


def test_recent_bookings_are_bounded_and_stably_newest_first(client):
    conn = get_db_connection()
    try:
        trip_id = _insert_trip(conn)
        inserted = [_insert_booking(conn, 4, trip_id, f"2098-01-{day:02d} 09:00") for day in range(1, 8)]
        conn.commit()
    finally:
        conn.close()

    _identity(client, 4)
    recent = _home_data(client)["recent_bookings"]
    assert len(recent) == 5
    assert [row["booking_id"] for row in recent] == list(reversed(inserted[-5:]))


def test_latest_maintenance_request_is_owned_by_authenticated_customer(client):
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO maintenance_requests (user_id, company_id, service_type, location, preferred_date, status, customer_name, created_at) VALUES (2, 5, 'oil_change', 'Private location', '2099-01-10', 'pending', 'User Two', '2099-01-01 10:00')"
        )
        conn.execute(
            "INSERT INTO maintenance_requests (user_id, company_id, service_type, location, preferred_date, status, customer_name, created_at) VALUES (3, 5, 'engine', 'Other private location', '2099-01-11', 'completed', 'User Three', '2100-01-01 10:00')"
        )
        conn.commit()
    finally:
        conn.close()

    _identity(client, 2)
    latest = _home_data(client)["latest_maintenance"]
    assert latest["service_type"] == "oil_change"
    assert "location" not in latest
    assert "customer_name" not in latest


def test_company_cards_are_real_active_companies_without_legacy_ratings_or_booking_volume(client):
    conn = get_db_connection()
    try:
        inactive_id = conn.execute(
            "INSERT INTO companies (name, name_ar, company_type, city, status) VALUES ('Hidden Co', 'شركة مخفية', 'transport', 'عمان', 'inactive')"
        ).lastrowid
        _insert_trip(conn, inactive_id, "2099-02-01 08:00")
        conn.commit()
    finally:
        conn.close()

    _identity(client, 2)
    data = _home_data(client)
    assert len(data["companies"]) <= 6
    assert all(card["company_id"] != inactive_id for card in data["companies"])
    assert all("rating" not in card and "bookings" not in card for card in data["companies"])
    assert all(set(card) == {"company_id", "name_ar", "name", "city", "available_upcoming_trips", "available_upcoming_routes", "average_rating", "review_count"} for card in data["companies"])
    assert all(card["average_rating"] is None and card["review_count"] == 0 for card in data["companies"])


def test_discovery_lists_are_bounded_and_do_not_expose_private_fields(client):
    _identity(client, 2)
    data = _home_data(client)
    assert len(data["upcoming_trips"]) <= 6
    serialized = json.dumps({"companies": data["companies"], "trips": data["upcoming_trips"]})
    for private_field in ("booking_id", "user_id", "email", "phone", "passenger_name"):
        assert private_field not in serialized


@pytest.mark.parametrize("selector", ["user_id=3", "company_id=2", "role=super_admin"])
def test_customer_identity_selector_tampering_is_rejected(client, selector):
    _identity(client, 2)
    response = client.get("/api/dashboard/home?" + selector)
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_query"
