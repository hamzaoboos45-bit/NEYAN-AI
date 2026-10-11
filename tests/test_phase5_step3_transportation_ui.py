"""Phase 5 Step 3 customer discovery/UI and scheduled-availability coverage."""

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


def _identity(client, user_id=2):
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["role"] = "customer"
        session["user_name"] = "Transportation Test"
        session["company_id"] = None
        session["_csrf_token"] = "phase5-step3-token"


def _insert_trip(company_id, departure, seats, status="active"):
    conn = get_db_connection()
    try:
        trip_id = conn.execute(
            """INSERT INTO trips (company_id, from_city, to_city, departure_time, arrival_time,
               vehicle_type, trip_class, total_seats, available_seats, price_jod, status)
               VALUES (?, 'عمان', 'العقبة', ?, ?, 'bus', 'economy', 20, ?, 8.5, ?)""",
            (company_id, departure, departure[:10] + " 22:00", seats, status),
        ).lastrowid
        conn.commit()
        return trip_id
    finally:
        conn.close()


def test_customer_discovery_only_returns_future_active_company_trips_with_seats(client):
    _identity(client)
    future = (date.today() + timedelta(days=14)).isoformat() + " 09:00"
    past = "2000-01-01 09:00"
    offered_id = _insert_trip(1, future, 3)
    _insert_trip(1, future.replace("09:00", "10:00"), 0)
    _insert_trip(1, past, 3)
    conn = get_db_connection()
    try:
        inactive_company = conn.execute(
            "INSERT INTO companies (name, name_ar, company_type, status) VALUES ('Inactive', 'شركة غير نشطة', 'transport', 'inactive')"
        ).lastrowid
        conn.commit()
    finally:
        conn.close()
    _insert_trip(inactive_company, future.replace("09:00", "11:00"), 3)

    response = client.get("/api/trips?from=عمان&to=العقبة&date=" + future[:10] + "&vehicle_type=bus&class=economy")
    assert response.status_code == 200
    assert [row["trip_id"] for row in response.get_json()] == [offered_id]


def test_transportation_page_has_three_clear_sections_and_phase9_assets(client):
    _identity(client)
    html = client.get("/trips").get_data(as_text=True)
    assert "available-trips" in html and "forming-trips" in html and "my-transportation" in html
    assert "transportSearchForm" in html and "transportDialog" in html
    assert "js/csrf.js" in html and "js/theme-lang.js" in html and "js/transportation.js" in html
    assert html.index("js/csrf.js") < html.index("js/theme-lang.js") < html.index("js/transportation.js")
    assert "neyan-mark.svg" in html


def test_forming_card_ui_contract_is_localized_pii_minimized_and_uses_real_api_actions(client):
    _identity(client)
    source = open(os.path.join(os.path.dirname(__file__), "..", "frontend", "static", "js", "transportation.js"), encoding="utf-8").read()
    assert "Minimum reached" in source and "تم بلوغ الحد الأدنى" in source
    assert "not a confirmed booking" in source and "ليس حجزاً مؤكداً" in source
    assert "/api/trip-requests/" in source and "join\"" in source and "leave\"" in source and "cancel\"" in source
    assert "compatible_request_exists" not in source  # UI treats the 409 candidate payload generically, not as a raw error.
    assert "innerHTML" not in source and "textContent" in source
    for prohibited in ("participant", "email", "phone", "creator_user_id", "company_id"):
        assert prohibited not in source


def test_my_transportation_keeps_real_bookings_and_forming_demand_separate(client):
    _identity(client, 1)
    payload = {
        "from_city": "Amman", "to_city": "Aqaba",
        "requested_date": (date.today() + timedelta(days=30)).isoformat(),
        "requested_time_start": "10:00", "requested_time_end": "12:00",
        "passenger_quantity": 2, "desired_vehicle_type": "bus", "desired_trip_class": "economy",
    }
    created = client.post("/api/trip-requests", json=payload, headers={"X-CSRFToken": "phase5-step3-token"})
    assert created.status_code == 201
    assert client.get("/api/bookings").status_code == 200
    mine = client.get("/api/trip-requests/mine").get_json()["data"]
    assert mine[0]["is_creator"] and mine[0]["my_passenger_quantity"] == 2
