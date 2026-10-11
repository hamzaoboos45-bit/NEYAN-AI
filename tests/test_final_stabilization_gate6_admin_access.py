"""Gate 6: trusted-shell Super Admin bootstrap and server-side RBAC contracts."""

import io
import os
import re
import sys
import tempfile

import bcrypt
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from backend.security.admin_bootstrap import BootstrapError, provision_first_super_admin
from backend.security.admin_management import AdminManagementError, reset_super_admin_password
from backend.security.credentials import hash_password
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
        app.config.update(TESTING=True, SECRET_KEY="gate6-test-key")
        with app.test_client() as test_client:
            yield test_client
    finally:
        config.DATABASE_PATH = original_path
        if os.path.exists(path):
            os.remove(path)


def _form_token(html):
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "expected a CSRF form token"
    return match.group(1)


def _login(client, email, password):
    token = _form_token(client.get("/login").get_data(as_text=True))
    return client.post(
        "/login",
        data={"csrf_token": token, "email": email, "password": password},
        follow_redirects=False,
    )


def _api_token(client):
    page = client.get("/admin").get_data(as_text=True)
    match = re.search(r'name="csrf-token" content="([^"]+)"', page)
    assert match, "expected an authenticated CSRF token"
    return match.group(1)


def _row(email):
    conn = get_db_connection()
    try:
        return conn.execute(
            "SELECT user_id, email, password_hash, role, status, is_active, company_id "
            "FROM users WHERE lower(email)=?",
            (email.lower(),),
        ).fetchone()
    finally:
        conn.close()


def test_official_cli_bootstrap_creates_one_hashed_platform_admin_that_can_log_in(client, monkeypatch, capsys):
    from scripts import bootstrap_super_admin

    monkeypatch.setattr(sys, "stdin", io.StringIO("OwnerPass123\n"))
    assert bootstrap_super_admin.main(
        ["--name", "Platform Owner", "--email", "OWNER@example.test", "--password-stdin"]
    ) == 0
    output = capsys.readouterr().out
    assert "owner@example.test" in output
    assert "OwnerPass123" not in output

    row = _row("owner@example.test")
    assert row["role"] == "admin"
    assert row["status"] == "approved"
    assert row["is_active"] == 1
    assert row["company_id"] is None
    assert row["password_hash"] != "OwnerPass123"
    assert bcrypt.checkpw(b"OwnerPass123", row["password_hash"].encode("utf-8"))

    login = _login(client, "OWNER@example.test", "OwnerPass123")
    assert login.status_code == 302 and login.headers["Location"].endswith("/admin")
    assert client.get("/admin").status_code == 200
    dashboard = client.get("/api/dashboard/admin")
    assert dashboard.status_code == 200
    assert dashboard.get_json()["scope"] == "platform"
    assert client.get("/api/admin/control-center/overview").status_code == 200


def test_repeated_bootstrap_is_safe_and_existing_customer_email_is_never_promoted(client):
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO users(full_name,name,email,password_hash,role,status,is_active) "
            "VALUES ('Customer Conflict','Customer Conflict','customer.conflict@example.test',?,'user','active',1)",
            (hash_password("CustomerPass123"),),
        )
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(BootstrapError, match="already exists"):
        provision_first_super_admin("Conflict", "CUSTOMER.CONFLICT@example.test", "ConflictPass123")
    conflict = _row("customer.conflict@example.test")
    assert conflict["role"] == "user" and conflict["company_id"] is None

    first = provision_first_super_admin("First Owner", "first@example.test", "FirstPass123")
    original_hash = _row("first@example.test")["password_hash"]
    with pytest.raises(BootstrapError, match="already exists"):
        provision_first_super_admin("Second Owner", "second@example.test", "SecondPass123")

    conn = get_db_connection()
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM users WHERE role='admin' AND company_id IS NULL"
        ).fetchone()[0]
    finally:
        conn.close()
    assert count == 1
    assert _row("first@example.test")["password_hash"] == original_hash


def test_admin_reset_uses_cli_service_rejects_unknowns_and_preserves_inactive_status(client, monkeypatch, capsys):
    from scripts import manage_super_admin

    owner = provision_first_super_admin("Platform Owner", "owner@example.test", "OwnerPass123")
    monkeypatch.setattr(sys, "stdin", io.StringIO("NewOwnerPass123\n"))
    assert manage_super_admin.main(
        ["--reset-password", "--email", "OWNER@example.test", "--password-stdin"]
    ) == 0
    output = capsys.readouterr().out
    assert "NewOwnerPass123" not in output
    assert _login(client, "owner@example.test", "OwnerPass123").status_code == 302
    assert _login(client, "owner@example.test", "NewOwnerPass123").status_code == 302
    assert client.get("/admin").status_code == 200

    conn = get_db_connection()
    try:
        conn.execute("UPDATE users SET is_active=0 WHERE user_id=?", (owner.user_id,))
        conn.commit()
    finally:
        conn.close()
    reset_super_admin_password("owner@example.test", "InactivePass123")
    inactive = _row("owner@example.test")
    assert inactive["is_active"] == 0
    client.get("/logout")
    denied = _login(client, "owner@example.test", "InactivePass123")
    assert denied.status_code == 302 and denied.headers["Location"].endswith("/login")
    with pytest.raises(AdminManagementError, match="No super-admin"):
        reset_super_admin_password("missing@example.test", "MissingPass123")


def test_company_admin_scope_is_server_derived_and_not_platform_wide(client):
    provision_first_super_admin("Platform Owner", "owner@example.test", "OwnerPass123")
    assert _login(client, "owner@example.test", "OwnerPass123").status_code == 302
    token = _api_token(client)
    created = client.post(
        "/api/admin/users",
        json={
            "name": "Company Operator",
            "email": "operator@example.test",
            "password": "OperatorPass123",
            "role": "company_admin",
            "company_id": 1,
        },
        headers={"X-CSRFToken": token},
    )
    assert created.status_code == 201
    client.get("/logout")
    login = _login(client, "operator@example.test", "OperatorPass123")
    assert login.status_code == 302 and login.headers["Location"].endswith("/admin")
    assert client.get("/api/analytics/summary").get_json()["scope"] == "company"
    scoped = client.get("/api/dashboard/admin")
    assert scoped.status_code == 200 and scoped.get_json()["scope"] == "company"
    assert client.get("/api/dashboard/admin?company_id=2").status_code == 400
    assert client.get("/api/admin/control-center/overview").status_code == 403
    assert client.get("/api/analytics/bookings-per-company").status_code == 403


def test_customer_unauthenticated_and_forged_public_payloads_cannot_gain_admin_access(client):
    assert client.get("/api/admin/control-center/overview").status_code == 401
    assert client.get("/api/admin/pricing/transport-policies").status_code == 401
    assert client.get("/api/bootstrap/super-admin").status_code == 404

    token = _form_token(client.get("/register").get_data(as_text=True))
    response = client.post(
        "/register",
        data={
            "csrf_token": token,
            "name": "Forged Customer",
            "email": "forged@example.test",
            "password": "CustomerPass123",
            "role": "super_admin",
            "company_id": "2",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302 and response.headers["Location"].endswith("/home")
    customer = _row("forged@example.test")
    assert customer["role"] == "user" and customer["company_id"] is None
    assert client.get("/api/admin/control-center/overview").status_code == 403
    assert client.get("/api/admin/pricing/transport-policies").status_code == 403


def test_no_public_bootstrap_route_is_registered(client):
    rules = {rule.rule for rule in client.application.url_map.iter_rules()}
    assert not any("bootstrap" in rule.lower() for rule in rules)
