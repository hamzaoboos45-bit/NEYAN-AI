"""Phase 8 Step 1: secure bootstrap and scoped dashboard foundation tests."""

import os
import re
import sys
import tempfile

import bcrypt
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from backend.dashboard.contracts import DashboardValidationError, parse_pagination
from backend.security.admin_bootstrap import BootstrapError, provision_first_super_admin
from database.db import get_db_connection
from database.init_db import initialize_database


@pytest.fixture()
def fresh_database():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    original_path = config.DATABASE_PATH
    config.DATABASE_PATH = path
    try:
        initialize_database()
        yield path
    finally:
        config.DATABASE_PATH = original_path
        if os.path.exists(path):
            os.remove(path)


@pytest.fixture()
def client(fresh_database):
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def _form_token(html):
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "No CSRF token found"
    return match.group(1)


def _login(client, email, password):
    token = _form_token(client.get("/login").get_data(as_text=True))
    return client.post(
        "/login",
        data={"csrf_token": token, "email": email, "password": password},
        follow_redirects=True,
    )


def _set_identity(client, user_id, role, company_id=None):
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["role"] = role
        session["company_id"] = company_id


def _count(conn, query, params=()):
    return conn.execute(query, params).fetchone()[0]


def test_fresh_database_bootstraps_first_super_admin_with_real_hash_and_login(client):
    result = provision_first_super_admin("Platform Owner", "OWNER@example.com", "OwnerPass123")
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT email, password_hash, role, company_id, status, is_active FROM users WHERE user_id = ?",
            (result.user_id,),
        ).fetchone()
    finally:
        conn.close()

    assert result.email == "owner@example.com"
    assert row["role"] == "admin"
    assert row["company_id"] is None
    assert row["status"] == "approved"
    assert row["is_active"] == 1
    assert row["password_hash"] != "OwnerPass123"
    assert bcrypt.checkpw(b"OwnerPass123", row["password_hash"].encode("utf-8"))
    assert "Platform Dashboard" in _login(client, "owner@example.com", "OwnerPass123").get_data(as_text=True)


def test_existing_valid_super_admin_is_never_overwritten(fresh_database):
    first = provision_first_super_admin("First Owner", "first@example.com", "FirstPass123")
    conn = get_db_connection()
    try:
        original_hash = conn.execute("SELECT password_hash FROM users WHERE user_id = ?", (first.user_id,)).fetchone()[0]
    finally:
        conn.close()

    with pytest.raises(BootstrapError, match="already exists"):
        provision_first_super_admin("Second Owner", "second@example.com", "SecondPass123")

    conn = get_db_connection()
    try:
        assert conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND company_id IS NULL").fetchone()[0] == 1
        assert conn.execute("SELECT password_hash FROM users WHERE user_id = ?", (first.user_id,)).fetchone()[0] == original_hash
    finally:
        conn.close()


@pytest.mark.parametrize(
    "name,email,password",
    [
        ("A", "owner@example.com", "OwnerPass123"),
        ("Owner", "not-an-email", "OwnerPass123"),
        ("Owner", "owner@example.com", "weakpass"),
    ],
)
def test_bootstrap_rejects_invalid_input_safely(fresh_database, name, email, password):
    with pytest.raises(BootstrapError):
        provision_first_super_admin(name, email, password)


def test_public_registration_and_customer_session_cannot_create_or_elevate_admin(client):
    token = _form_token(client.get("/register").get_data(as_text=True))
    response = client.post(
        "/register",
        data={
            "csrf_token": token,
            "name": "Public Customer",
            "email": "public@example.com",
            "password": "Customer123",
            "role": "admin",
            "company_id": "1",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT role, company_id FROM users WHERE email = 'public@example.com'").fetchone()
    finally:
        conn.close()
    assert row["role"] == "user"
    assert row["company_id"] is None

    _set_identity(client, 2, "customer")
    # There is deliberately no HTTP bootstrap endpoint. Use GET here because
    # the global CSRF guard correctly rejects unknown unsafe requests first.
    assert client.get("/api/bootstrap/super-admin").status_code == 404
    token = re.search(r'name="csrf-token" content="([^"]+)"', client.get("/home").get_data(as_text=True)).group(1)
    assert client.post(
        "/api/admin/users",
        json={"name": "Attack", "email": "attack@example.com", "password": "Attack123", "role": "super_admin"},
        headers={"X-CSRFToken": token},
    ).status_code == 403


def test_dashboard_platform_metrics_match_direct_database_counts_and_require_login(client):
    assert client.get("/api/dashboard/overview").status_code == 401
    owner = provision_first_super_admin("Platform Owner", "owner@example.com", "OwnerPass123")
    _set_identity(client, owner.user_id, "super_admin")

    response = client.get("/api/dashboard/overview")
    assert response.status_code == 200
    payload = response.get_json()
    conn = get_db_connection()
    try:
        expected = {
            "total_companies": _count(conn, "SELECT COUNT(*) FROM companies"),
            "total_users": _count(conn, "SELECT COUNT(*) FROM users"),
            "total_trips": _count(conn, "SELECT COUNT(*) FROM trips"),
            "total_bookings": _count(conn, "SELECT COUNT(*) FROM bookings"),
            "total_maintenance_requests": _count(conn, "SELECT COUNT(*) FROM maintenance_requests"),
        }
    finally:
        conn.close()
    assert payload["scope"] == "platform"
    assert payload["data"] == expected
    assert payload["date_range"] == {"from": None, "to": None, "timezone": "UTC"}
    assert payload["generated_at"].endswith("Z")


def test_company_metrics_are_server_scoped_and_client_company_selector_is_rejected(client):
    _set_identity(client, 4, "company_admin", company_id=1)
    response = client.get("/api/dashboard/overview")
    assert response.status_code == 200
    payload = response.get_json()
    conn = get_db_connection()
    try:
        expected = {
            "total_trips": _count(conn, "SELECT COUNT(*) FROM trips WHERE company_id = 1"),
            "total_bookings": _count(conn, "SELECT COUNT(*) FROM bookings b JOIN trips t ON b.trip_id = t.trip_id WHERE t.company_id = 1"),
            "total_maintenance_requests": _count(conn, "SELECT COUNT(*) FROM maintenance_requests WHERE company_id = 1"),
        }
    finally:
        conn.close()
    assert payload["scope"] == "company"
    assert payload["data"] == expected

    denied = client.get("/api/dashboard/overview?company_id=2")
    assert denied.status_code == 400
    assert denied.get_json()["error"]["code"] == "invalid_query"


def test_customer_metrics_are_server_scoped_and_client_user_selector_is_rejected(client):
    _set_identity(client, 2, "customer")
    response = client.get("/api/dashboard/overview")
    assert response.status_code == 200
    payload = response.get_json()
    conn = get_db_connection()
    try:
        expected = {
            "total_bookings": _count(conn, "SELECT COUNT(*) FROM bookings WHERE user_id = 2"),
            "total_maintenance_requests": _count(conn, "SELECT COUNT(*) FROM maintenance_requests WHERE user_id = 2"),
        }
    finally:
        conn.close()
    assert payload["scope"] == "user"
    assert payload["data"] == expected

    denied = client.get("/api/dashboard/overview?user_id=3")
    assert denied.status_code == 400
    assert denied.get_json()["error"]["code"] == "invalid_query"


@pytest.mark.parametrize(
    "query",
    ["from=invalid", "from=2026-02-02&to=2026-02-01", "from=2024-01-01&to=2026-01-02", "timezone=Asia/Amman"],
)
def test_dashboard_date_range_rejects_invalid_or_unsupported_values(client, query):
    _set_identity(client, 2, "customer")
    response = client.get(f"/api/dashboard/overview?{query}")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_query"


def test_pagination_contract_enforces_safe_limits():
    assert parse_pagination({}).as_response(51) == {"page": 1, "page_size": 25, "total": 51, "total_pages": 3}
    with pytest.raises(DashboardValidationError):
        parse_pagination({"page_size": "101"})
