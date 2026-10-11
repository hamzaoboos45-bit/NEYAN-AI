"""Phase 8 Step 4: real, eligible customer review and rating system."""

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
        session["user_name"] = "Review Test"


def _csrf(client):
    client.get("/home")
    with client.session_transaction() as session:
        return session["_csrf_token"]


def _post_review(client, booking_id, rating=5, review_text="", extra=None):
    payload = {"booking_id": booking_id, "rating": rating, "review_text": review_text}
    if extra:
        payload.update(extra)
    return client.post("/api/reviews", json=payload, headers={"X-CSRFToken": _csrf(client)})


def _new_company_trip_booking(user_id=2, departure="2000-01-01 08:00", booking_status="confirmed", trip_status="active", company_id=None):
    conn = get_db_connection()
    try:
        if company_id is None:
            company_id = conn.execute(
                "INSERT INTO companies (name, name_ar, company_type, city, rating) VALUES ('Review Co', 'شركة المراجعات', 'transport', 'عمان', 4.9)"
            ).lastrowid
        trip_id = conn.execute(
            """INSERT INTO trips (company_id, from_city, to_city, departure_time, arrival_time, vehicle_type,
               trip_class, total_seats, available_seats, price_jod, status)
               VALUES (?, 'عمان', 'إربد', ?, '2100-01-01 10:00', 'bus', 'economy', 30, 10, 8, ?)""",
            (company_id, departure, trip_status),
        ).lastrowid
        booking_id = conn.execute(
            """INSERT INTO bookings (user_id, trip_id, seats_booked, total_price, status, payment_status, booked_at)
               VALUES (?, ?, 2, 16, ?, 'unpaid', '2000-01-01 07:00')""",
            (user_id, trip_id, booking_status),
        ).lastrowid
        conn.commit()
        return company_id, trip_id, booking_id
    finally:
        conn.close()


def test_schema_has_one_review_per_booking_and_review_indexes(client):
    conn = get_db_connection()
    try:
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'reviews'").fetchone()[0]
        indexes = {row["name"] for row in conn.execute("PRAGMA index_list('reviews')").fetchall()}
    finally:
        conn.close()
    assert "CHECK(rating BETWEEN 1 AND 5)" in sql and "booking_id" in sql and "UNIQUE" in sql
    assert {"idx_reviews_company", "idx_reviews_user_created"}.issubset(indexes)


def test_eligible_owned_confirmed_past_booking_can_be_reviewed_with_csrf(client):
    _, _, booking_id = _new_company_trip_booking()
    _identity(client, 2)
    assert client.post("/api/reviews", json={"booking_id": booking_id, "rating": 5}).status_code == 400
    response = _post_review(client, booking_id, 5, "<b>Great</b>")
    assert response.status_code == 201
    assert response.get_json()["data"]["rating"] == 5
    assert response.get_json()["data"]["review_text"] == "<b>Great</b>"


@pytest.mark.parametrize(
    "owner,status,departure,trip_status,expected_status",
    [(3, "confirmed", "2000-01-01 08:00", "active", 403), (2, "confirmed", "2100-01-01 08:00", "active", 403), (2, "cancelled", "2000-01-01 08:00", "active", 403), (2, "confirmed", "2000-01-01 08:00", "cancelled", 403)],
)
def test_ineligible_other_future_cancelled_booking_or_trip_cannot_be_reviewed(client, owner, status, departure, trip_status, expected_status):
    _, _, booking_id = _new_company_trip_booking(owner, departure, status, trip_status)
    _identity(client, 2)
    assert _post_review(client, booking_id).status_code == expected_status
    assert _post_review(client, 999999).status_code == 403


@pytest.mark.parametrize("rating", [0, 6, -1, "5", 1.5, True])
def test_invalid_rating_values_are_rejected(client, rating):
    _, _, booking_id = _new_company_trip_booking()
    _identity(client, 2)
    response = _post_review(client, booking_id, rating)
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_rating"


def test_rating_boundaries_comment_validation_and_client_company_tampering(client):
    _, _, one = _new_company_trip_booking()
    _, _, five = _new_company_trip_booking()
    _identity(client, 2)
    assert _post_review(client, one, 1).status_code == 201
    assert _post_review(client, five, 5).status_code == 201
    _, _, long_text_booking = _new_company_trip_booking()
    assert _post_review(client, long_text_booking, 5, "x" * 1001).status_code == 400
    _, _, tamper_booking = _new_company_trip_booking()
    assert _post_review(client, tamper_booking, 5, extra={"company_id": 999}).status_code == 400


def test_duplicate_review_is_prevented_by_api_and_database_constraint(client):
    company_id, _, booking_id = _new_company_trip_booking()
    _identity(client, 2)
    assert _post_review(client, booking_id).status_code == 201
    assert _post_review(client, booking_id).status_code == 409
    conn = get_db_connection()
    try:
        with pytest.raises(Exception):
            conn.execute("INSERT INTO reviews (user_id, booking_id, company_id, rating) VALUES (2, ?, ?, 4)", (booking_id, company_id))
    finally:
        conn.close()


def test_real_aggregation_ignores_seed_rating_and_zero_review_company_is_null(client):
    company_id, _, booking_one = _new_company_trip_booking(user_id=2)
    _, _, booking_two = _new_company_trip_booking(user_id=3, company_id=company_id)
    zero_company, _, _ = _new_company_trip_booking(user_id=2)
    _identity(client, 2)
    assert _post_review(client, booking_one, 5).status_code == 201
    _identity(client, 3)
    assert _post_review(client, booking_two, 1).status_code == 201

    _identity(client, 2)
    home = client.get("/api/dashboard/home").get_json()["data"]
    cards = {card["company_id"]: card for card in home["companies"]}
    assert cards[company_id]["average_rating"] == 3.0 and cards[company_id]["review_count"] == 2
    assert cards[zero_company]["average_rating"] is None and cards[zero_company]["review_count"] == 0
    assert cards[company_id]["average_rating"] != 4.9


def test_home_review_opportunity_and_own_review_are_returned_without_unsafe_public_identity(client):
    _, _, booking_id = _new_company_trip_booking()
    _identity(client, 2)
    first = client.get("/api/dashboard/home").get_json()["data"]
    assert booking_id in {row["booking_id"] for row in first["review_opportunities"]}
    assert _post_review(client, booking_id, 4, "<img src=x onerror=alert(1)>").status_code == 201
    second = client.get("/api/dashboard/home").get_json()["data"]
    assert booking_id not in {row["booking_id"] for row in second["review_opportunities"]}
    own = next(row for row in second["recent_bookings"] if row["booking_id"] == booking_id)
    assert own["review_rating"] == 4 and own["review_text"] == "<img src=x onerror=alert(1)>"
    with open(os.path.join(os.path.dirname(__file__), "..", "frontend", "static", "js", "home-dashboard.js"), encoding="utf-8") as handle:
        source = handle.read()
    assert "item.review_text" in source and ".innerHTML" not in source


def test_admin_rating_analytics_is_real_and_company_scoped_without_review_mutation_access(client):
    company_one, _, booking_one = _new_company_trip_booking(user_id=2)
    company_two, _, booking_two = _new_company_trip_booking(user_id=3)
    _identity(client, 2)
    assert _post_review(client, booking_one, 5).status_code == 201
    _identity(client, 3)
    assert _post_review(client, booking_two, 2).status_code == 201
    _identity(client, 1, "super_admin")
    platform = client.get("/api/dashboard/admin").get_json()["data"]["kpis"]
    assert platform["real_review_count"] == 2
    assert platform["reviewed_companies"] == 2
    assert platform["average_customer_rating"] == 3.5
    _identity(client, 4, "company_admin", company_one)
    company = client.get("/api/dashboard/admin").get_json()["data"]["kpis"]
    assert company["real_review_count"] == 1 and company["average_customer_rating"] == 5.0
    assert _post_review(client, booking_one, 4).status_code == 403
    assert company_two != company_one


def test_unauthenticated_review_creation_is_blocked(client):
    response = client.post("/api/reviews", json={"booking_id": 1, "rating": 5})
    assert response.status_code == 400  # CSRF rejects before route authorization.
