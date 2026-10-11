"""Phase 8 Step 3: advanced, real, scoped admin dashboard coverage."""

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


def _identity(client, user_id, role, company_id=None):
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["role"] = role
        session["company_id"] = company_id
        session["user_name"] = "Admin test"


def _seed_analytics_data():
    """Create an isolated same-day data set so range assertions are exact."""
    conn = get_db_connection()
    try:
        company_one = conn.execute(
            "INSERT INTO companies (name, name_ar, company_type, city, status, created_at) VALUES ('Scope One', 'شركة النطاق الأولى', 'transport', 'عمان', 'active', '2099-04-10 08:00')"
        ).lastrowid
        company_two = conn.execute(
            "INSERT INTO companies (name, name_ar, company_type, city, status, created_at) VALUES ('Scope Two', 'شركة النطاق الثانية', 'transport', 'إربد', 'inactive', '2099-04-10 08:00')"
        ).lastrowid

        def trip(company_id, route):
            return conn.execute(
                """INSERT INTO trips (company_id, from_city, to_city, departure_time, arrival_time, vehicle_type,
                   trip_class, total_seats, available_seats, price_jod, status, created_at)
                   VALUES (?, ?, ?, '2100-01-01 08:00', '2100-01-01 10:00', 'bus', 'economy', 30, 12, 8, 'active', '2099-04-10 08:00')""",
                (company_id, *route),
            ).lastrowid

        first_trip = trip(company_one, ("عمان", "إربد"))
        second_trip = trip(company_two, ("الزرقاء", "العقبة"))

        def booking(trip_id, status, payment, price, stamp):
            return conn.execute(
                """INSERT INTO bookings (user_id, trip_id, seats_booked, total_price, status, payment_status,
                   passenger_name, passenger_phone, booked_at) VALUES (2, ?, 1, ?, ?, ?, 'Private Passenger', '0790000000', ?)""",
                (trip_id, price, status, payment, stamp),
            ).lastrowid

        first_ids = [
            booking(first_trip, "confirmed", "paid", 12.5, f"2099-04-10 {hour:02d}:00")
            for hour in range(1, 8)
        ]
        booking(first_trip, "pending", "unpaid", 7, "2099-04-10 10:00")
        booking(first_trip, "cancelled", "paid", 99, "2099-04-10 11:00")
        other_booking = booking(second_trip, "confirmed", "paid", 500, "2099-04-10 12:00")
        conn.execute(
            """INSERT INTO maintenance_requests (user_id, company_id, service_type, location, preferred_date,
               status, customer_name, customer_phone, created_at) VALUES (2, ?, 'oil_change', 'private garage',
               '2099-04-11', 'pending', 'Private Customer', '0790000001', '2099-04-10 13:00')""",
            (company_one,),
        )
        conn.execute(
            """INSERT INTO maintenance_requests (user_id, company_id, service_type, location, preferred_date,
               status, customer_name, customer_phone, created_at) VALUES (3, ?, 'battery', 'other private garage',
               '2099-04-11', 'completed', 'Other Customer', '0790000002', '2099-04-10 14:00')""",
            (company_two,),
        )
        conn.commit()
        return company_one, company_two, first_ids, other_booking
    finally:
        conn.close()


def _dashboard(client, query="from=2099-04-10&to=2099-04-10"):
    response = client.get(f"/api/dashboard/admin?{query}")
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def test_admin_dashboard_requires_authenticated_admin_and_rejects_identity_tampering(client):
    assert client.get("/api/dashboard/admin").status_code == 401
    _identity(client, 2, "customer")
    assert client.get("/api/dashboard/admin").status_code == 403
    _identity(client, 1, "super_admin")
    response = client.get("/api/dashboard/admin?company_id=2")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_query"


def test_platform_dashboard_uses_real_kpis_revenue_charts_and_bounded_private_previews(client):
    _seed_analytics_data()
    _identity(client, 1, "super_admin")
    payload = _dashboard(client)
    data = payload["data"]

    assert payload["scope"] == "platform"
    assert payload["date_range"] == {"from": "2099-04-10", "to": "2099-04-10", "timezone": "UTC"}
    assert data["kpis"]["total_companies"] == 2
    assert data["kpis"]["active_companies"] == 1
    assert data["kpis"]["total_trips"] == 2
    assert data["kpis"]["total_bookings"] == 10
    assert data["kpis"]["confirmed_bookings"] == 8
    assert data["kpis"]["pending_bookings"] == 1
    assert data["kpis"]["cancelled_bookings"] == 1
    assert data["kpis"]["paid_revenue_jod"] == 587.5  # confirmed + paid only; cancelled paid is excluded
    assert data["trends"]["bookings"] == [{"date": "2099-04-10", "count": 10}]
    assert {row["label"]: row["count"] for row in data["charts"]["bookings_by_company"]}["شركة النطاق الأولى"] == 9
    assert len(data["previews"]["bookings"]) == 5
    serialized = json.dumps(data, ensure_ascii=False)
    for private_field in ("passenger_name", "passenger_phone", "customer_name", "customer_phone", "private garage"):
        assert private_field not in serialized


def test_company_dashboard_isolated_to_server_session_company_for_kpis_charts_and_previews(client):
    company_one, company_two, first_ids, other_booking = _seed_analytics_data()
    _identity(client, 4, "company_admin", company_one)
    data = _dashboard(client)["data"]

    assert data["kpis"]["total_trips"] == 1
    assert data["kpis"]["total_bookings"] == 9
    assert data["kpis"]["paid_revenue_jod"] == 87.5
    assert data["kpis"]["total_maintenance_requests"] == 1
    assert data["trends"]["bookings"] == [{"date": "2099-04-10", "count": 9}]
    assert data["charts"]["popular_routes"] == [{"label": "عمان → إربد", "count": 9}]
    preview_ids = {row["booking_id"] for row in data["previews"]["bookings"]}
    assert len(preview_ids) == 5
    assert other_booking not in preview_ids
    assert all("company_name" not in row for row in data["previews"]["bookings"])
    assert company_two != company_one


def test_admin_date_range_applies_to_previews_and_invalid_range_is_safe(client):
    _seed_analytics_data()
    _identity(client, 1, "super_admin")
    data = _dashboard(client, "from=2099-04-11&to=2099-04-11")["data"]
    assert data["kpis"]["total_bookings"] == 0
    assert data["previews"]["bookings"] == []
    assert data["previews"]["maintenance"] == []
    response = client.get("/api/dashboard/admin?from=2099-04-11&to=2099-04-10")
    assert response.status_code == 400


def test_admin_page_loads_consolidated_analytics_asset_and_preserves_operations(client):
    _identity(client, 1, "super_admin")
    page = client.get("/admin")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "adminDateFilter" in html and "admin-analytics.js" in html
    with open(os.path.join(os.path.dirname(__file__), "..", "frontend", "static", "js", "admin-analytics.js"), encoding="utf-8") as handle:
        source = handle.read()
    assert "/api/dashboard/admin" in source
    assert "createElementNS" in source
    assert "passenger_name" not in source and "customer_name" not in source
