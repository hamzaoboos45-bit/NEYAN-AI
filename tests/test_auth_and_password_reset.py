"""
tests/test_auth_and_password_reset.py — Phase 3 continuation.

Formalizes into the permanent suite everything that was manually verified
against the real dev database during Phase 3 (login, admin creation, RBAC,
CSRF), plus new coverage for the password-reset + email infrastructure
added in this continuation: token expiry/single-use, rate limiting, and
both email providers (SMTP, SendGrid) with mocked transport so credential
handling and failure paths are tested without needing real credentials or
network access.

Same isolated-temp-database pattern as tests/test_chatbot_integration.py —
never touches database/transport.db, safe to run repeatedly.
"""
import os
import re
import smtplib
import sys
import tempfile
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    original_path = config.DATABASE_PATH
    original_provider = config.EMAIL_PROVIDER
    config.DATABASE_PATH = path
    try:
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c
    finally:
        config.DATABASE_PATH = original_path
        config.EMAIL_PROVIDER = original_provider  # tests below flip this; always restore
        if os.path.exists(path):
            os.remove(path)


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────

def _form_token(html):
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert m, "no csrf_token found in page"
    return m.group(1)


def _register(client, name, email, password="password123"):
    r = client.get("/register")
    token = _form_token(r.get_data(as_text=True))
    return client.post(
        "/register",
        data={"csrf_token": token, "name": name, "email": email, "password": password},
        follow_redirects=True,
    )


def _login(client, email, password="password123"):
    r = client.get("/login")
    token = _form_token(r.get_data(as_text=True))
    return client.post(
        "/login", data={"csrf_token": token, "email": email, "password": password}, follow_redirects=True
    )


def _api_token(client):
    """Grabs a live CSRF token from any authenticated page's <meta> tag,
    for use as the X-CSRFToken header on JSON API calls."""
    r = client.get("/home")
    m = re.search(r'name="csrf-token" content="([^"]+)"', r.get_data(as_text=True))
    if not m:
        r = client.get("/admin")
        m = re.search(r'name="csrf-token" content="([^"]+)"', r.get_data(as_text=True))
    assert m, "no csrf-token meta tag found"
    return m.group(1)


def _make_super_admin(email):
    from database.db import get_db_connection
    conn = get_db_connection()
    conn.execute(
        "UPDATE users SET role='admin', status='approved', company_id=NULL WHERE lower(email)=?",
        (email.lower(),),
    )
    conn.commit()
    conn.close()


def _first_company_id():
    from database.db import get_db_connection
    conn = get_db_connection()
    row = conn.execute("SELECT company_id FROM companies LIMIT 1").fetchone()
    conn.close()
    return row["company_id"]


# ─────────────────────────────────────────────────────────────────────────
# Test 1 / 2 / 3 — registration + public-registration cannot request admin
# ─────────────────────────────────────────────────────────────────────────

def test_normal_registration_works(client):
    r = _register(client, "Ahmad Q", "ahmadq@example.com")
    assert r.status_code == 200

    from database.db import get_db_connection
    conn = get_db_connection()
    row = conn.execute("SELECT role, status, company_id FROM users WHERE email='ahmadq@example.com'").fetchone()
    conn.close()
    assert row["role"] == "user"
    assert row["status"] == "active"
    assert row["company_id"] is None


def test_public_registration_cannot_request_admin(client):
    """A direct POST trying to smuggle role=admin + company_id, exactly as
    a curl/devtools attacker (not the removed UI) would attempt it."""
    r = client.get("/register")
    token = _form_token(r.get_data(as_text=True))
    r = client.post(
        "/register",
        data={
            "csrf_token": token, "name": "Sneaky", "email": "sneaky@example.com",
            "password": "password123", "role": "admin", "company_id": "1",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200

    from database.db import get_db_connection
    conn = get_db_connection()
    row = conn.execute("SELECT role, status, company_id FROM users WHERE email='sneaky@example.com'").fetchone()
    conn.close()
    assert row["role"] == "user"
    assert row["status"] == "active"
    assert row["company_id"] is None


# ─────────────────────────────────────────────────────────────────────────
# Test 4 / 5 — login
# ─────────────────────────────────────────────────────────────────────────

def test_valid_login_succeeds(client):
    _register(client, "Login Test", "logintest@example.com")
    client.get("/logout")
    r = client.get("/login")
    token = _form_token(r.get_data(as_text=True))
    r = client.post("/login", data={"csrf_token": token, "email": "logintest@example.com", "password": "password123"})
    assert r.status_code == 302
    assert "/home" in r.headers["Location"]


def test_invalid_login_rejected(client):
    _register(client, "Login Test2", "logintest2@example.com")
    client.get("/logout")
    r = client.get("/login")
    token = _form_token(r.get_data(as_text=True))
    r = client.post(
        "/login", data={"csrf_token": token, "email": "logintest2@example.com", "password": "wrongpassword"},
        follow_redirects=True,
    )
    assert "Invalid email or password" in r.get_data(as_text=True)


def test_empty_fields_show_validation_message(client):
    r = client.get("/login")
    token = _form_token(r.get_data(as_text=True))
    r = client.post("/login", data={"csrf_token": token, "email": "", "password": ""}, follow_redirects=True)
    assert "valid email and password" in r.get_data(as_text=True)


# ─────────────────────────────────────────────────────────────────────────
# Logout / protected routes
# ─────────────────────────────────────────────────────────────────────────

def test_logout_clears_session_and_protects_routes(client):
    _register(client, "Logout Test", "logouttest@example.com")
    assert client.get("/home").status_code == 200
    client.get("/logout")
    assert client.get("/home").status_code == 302
    assert client.get("/profile").status_code == 302
    assert client.get("/api/admin/users").status_code == 401


def test_protected_page_without_login_rejected(client):
    assert client.get("/profile").status_code == 302
    assert client.get("/api/admin/users").status_code == 401


# ─────────────────────────────────────────────────────────────────────────
# Admin creation (the modal's backend) — valid, role, company, hashing
# ─────────────────────────────────────────────────────────────────────────

def test_admin_creation_valid_company_admin(client):
    _register(client, "Root Admin", "rootadmin@example.com")
    _make_super_admin("rootadmin@example.com")
    client.get("/logout")
    _login(client, "rootadmin@example.com")

    company_id = _first_company_id()
    token = _api_token(client)
    r = client.post(
        "/api/admin/users",
        json={"name": "New CoAdmin", "email": "newcoadmin@example.com", "password": "password123",
              "role": "company_admin", "company_id": str(company_id)},
        headers={"X-CSRFToken": token},
    )
    assert r.status_code == 201, r.get_json()

    from database.db import get_db_connection
    conn = get_db_connection()
    row = conn.execute(
        "SELECT role, status, company_id, is_active, password_hash FROM users WHERE email='newcoadmin@example.com'"
    ).fetchone()
    conn.close()
    assert row["role"] == "admin"
    assert row["status"] == "approved"
    assert row["is_active"] == 1
    assert row["company_id"] == company_id
    assert row["password_hash"] != "password123"
    assert row["password_hash"].startswith("$2b$")  # bcrypt


def test_admin_creation_duplicate_rejected_no_duplicate_row(client):
    _register(client, "Root Admin2", "rootadmin2@example.com")
    _make_super_admin("rootadmin2@example.com")
    client.get("/logout")
    _login(client, "rootadmin2@example.com")

    company_id = _first_company_id()
    token = _api_token(client)
    payload = {"name": "Dup", "email": "dup@example.com", "password": "password123",
               "role": "company_admin", "company_id": str(company_id)}
    r1 = client.post("/api/admin/users", json=payload, headers={"X-CSRFToken": token})
    r2 = client.post("/api/admin/users", json=payload, headers={"X-CSRFToken": token})
    assert r1.status_code == 201
    assert r2.status_code == 409
    assert "sqlite3" not in str(r2.get_json())

    from database.db import get_db_connection
    conn = get_db_connection()
    count = conn.execute("SELECT COUNT(*) c FROM users WHERE email='dup@example.com'").fetchone()["c"]
    conn.close()
    assert count == 1


def test_admin_creation_invalid_data_rejected(client):
    _register(client, "Root Admin3", "rootadmin3@example.com")
    _make_super_admin("rootadmin3@example.com")
    client.get("/logout")
    _login(client, "rootadmin3@example.com")
    token = _api_token(client)

    bad_email = client.post("/api/admin/users", json={"name": "Valid Name", "email": "not-an-email",
                             "password": "password123", "role": "customer"}, headers={"X-CSRFToken": token})
    weak_pw = client.post("/api/admin/users", json={"name": "Valid Name", "email": "weak@example.com",
                           "password": "weak", "role": "customer"}, headers={"X-CSRFToken": token})
    bad_role = client.post("/api/admin/users", json={"name": "Valid Name", "email": "badrole@example.com",
                            "password": "password123", "role": "not_a_role"}, headers={"X-CSRFToken": token})
    no_company = client.post("/api/admin/users", json={"name": "Valid Name", "email": "nocompany@example.com",
                              "password": "password123", "role": "company_admin"}, headers={"X-CSRFToken": token})
    non_numeric_company = client.post(
        "/api/admin/users",
        json={"name": "Valid Name", "email": "badcompany@example.com", "password": "password123",
              "role": "company_admin", "company_id": "not-a-number"},
        headers={"X-CSRFToken": token},
    )

    assert bad_email.status_code == 400
    assert weak_pw.status_code == 400
    assert bad_role.status_code == 400
    assert no_company.status_code == 400
    # This is the exact input shape that used to crash with an unhandled
    # 500 before the Phase 3 fix (see the phase report) — must now be a
    # clean 400, never a raw traceback.
    assert non_numeric_company.status_code == 400
    assert "Invalid company" in non_numeric_company.get_json()["error"]


# ─────────────────────────────────────────────────────────────────────────
# RBAC — the API must be authoritative, not just the UI
# ─────────────────────────────────────────────────────────────────────────

def test_customer_cannot_create_admin_via_api(client):
    _register(client, "Plain Customer", "plaincust@example.com")
    token = _api_token(client)
    r = client.post(
        "/api/admin/users",
        json={"name": "Hacker", "email": "hacker@example.com", "password": "password123", "role": "super_admin"},
        headers={"X-CSRFToken": token},
    )
    assert r.status_code == 403

    from database.db import get_db_connection
    conn = get_db_connection()
    exists = conn.execute("SELECT 1 FROM users WHERE email='hacker@example.com'").fetchone()
    conn.close()
    assert exists is None


def test_company_admin_cannot_create_admin_or_reach_platform_analytics(client):
    _register(client, "Scoped Admin", "scopedadmin@example.com")
    company_id = _first_company_id()
    from database.db import get_db_connection
    conn = get_db_connection()
    conn.execute(
        "UPDATE users SET role='admin', status='approved', company_id=? WHERE email='scopedadmin@example.com'",
        (company_id,),
    )
    conn.commit()
    conn.close()

    client.get("/logout")
    _login(client, "scopedadmin@example.com")
    token = _api_token(client)

    r = client.post(
        "/api/admin/users",
        json={"name": "Hacker2", "email": "hacker2@example.com", "password": "password123", "role": "super_admin"},
        headers={"X-CSRFToken": token},
    )
    assert r.status_code == 403
    assert client.get("/api/analytics/companies").status_code == 403


# ─────────────────────────────────────────────────────────────────────────
# CSRF
# ─────────────────────────────────────────────────────────────────────────

def test_csrf_missing_token_rejected(client):
    _register(client, "Csrf Test", "csrftest@example.com")
    r = client.post("/api/maintenance/requests",
                     json={"service_type": "oil_change", "location": "Amman", "preferred_date": "2026-09-01"})
    assert r.status_code in (400, 403)


# ─────────────────────────────────────────────────────────────────────────
# Password reset — token lifecycle
# ─────────────────────────────────────────────────────────────────────────

def test_forgot_password_unknown_email_same_generic_message(client):
    r = client.get("/forgot-password")
    token = _form_token(r.get_data(as_text=True))
    r = client.post("/forgot-password", data={"csrf_token": token, "email": "doesnotexist@example.com"})
    html = r.get_data(as_text=True)
    assert "a password reset link has been generated" in html
    assert "/reset-password/" not in html  # no token exists for a nonexistent account


def test_forgot_password_valid_account_generates_dev_link_when_unconfigured(client):
    _register(client, "Forgot Test", "forgottest@example.com")
    client.get("/logout")
    r = client.get("/forgot-password")
    token = _form_token(r.get_data(as_text=True))
    r = client.post("/forgot-password", data={"csrf_token": token, "email": "forgottest@example.com"})
    html = r.get_data(as_text=True)
    assert "Development mode" in html
    assert "/reset-password/" in html


def test_reset_token_expired_is_rejected(client):
    _register(client, "Expiry Test", "expirytest@example.com")
    from database.db import get_db_connection
    from backend.security import password_reset
    conn = get_db_connection()
    user_id = conn.execute("SELECT user_id FROM users WHERE email='expirytest@example.com'").fetchone()["user_id"]
    conn.close()

    token = password_reset.create_reset_token(user_id)
    conn = get_db_connection()
    conn.execute("UPDATE password_resets SET expires_at = datetime('now', '-1 minute') WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

    r = client.get(f"/reset-password/{token}", follow_redirects=True)
    assert "invalid or has expired" in r.get_data(as_text=True)


def test_reset_token_single_use_and_password_actually_changes(client):
    _register(client, "Reuse Test", "reusetest@example.com")
    from database.db import get_db_connection
    from backend.security import password_reset
    conn = get_db_connection()
    user_id = conn.execute("SELECT user_id FROM users WHERE email='reusetest@example.com'").fetchone()["user_id"]
    conn.close()
    token = password_reset.create_reset_token(user_id)

    r = client.get(f"/reset-password/{token}")
    reset_csrf = _form_token(r.get_data(as_text=True))
    r = client.post(f"/reset-password/{token}",
                     data={"csrf_token": reset_csrf, "password": "brandnewpass123", "confirm_password": "brandnewpass123"},
                     follow_redirects=True)
    assert "Your password has been reset" in r.get_data(as_text=True)

    # same token again -> rejected (single-use)
    r2 = client.get(f"/reset-password/{token}", follow_redirects=True)
    assert "invalid or has expired" in r2.get_data(as_text=True)

    # old password no longer works, new one does
    client.get("/logout")
    r = client.get("/login")
    t = _form_token(r.get_data(as_text=True))
    r = client.post("/login", data={"csrf_token": t, "email": "reusetest@example.com", "password": "password123"},
                     follow_redirects=True)
    assert "Invalid email or password" in r.get_data(as_text=True)

    client.get("/logout")
    r = client.get("/login")
    t = _form_token(r.get_data(as_text=True))
    r = client.post("/login", data={"csrf_token": t, "email": "reusetest@example.com", "password": "brandnewpass123"})
    assert r.status_code == 302 and "/home" in r.headers["Location"]


def test_forgot_password_rate_limited_same_message_fewer_tokens(client):
    _register(client, "Rate Test", "ratetest@example.com")
    client.get("/logout")

    dev_links_shown = 0
    for _ in range(5):  # threshold is 3 per email / 15 min
        r = client.get("/forgot-password")
        t = _form_token(r.get_data(as_text=True))
        r = client.post("/forgot-password", data={"csrf_token": t, "email": "ratetest@example.com"})
        html = r.get_data(as_text=True)
        assert "a password reset link has been generated" in html  # identical every time
        if "/reset-password/" in html:
            dev_links_shown += 1
    assert dev_links_shown == 3


# ─────────────────────────────────────────────────────────────────────────
# Email service — provider config + mocked transport (no real network)
# ─────────────────────────────────────────────────────────────────────────

def test_email_not_configured_by_default():
    from backend.email import email_service
    assert config.EMAIL_PROVIDER == "console"
    assert email_service.is_configured() is False
    result = email_service.send_password_reset_email("x@example.com", "https://x/reset/1")
    assert result.attempted is False
    assert result.sent is False


def test_email_smtp_success_and_failure_mocked():
    from backend.email import email_service
    config.EMAIL_PROVIDER = "smtp"
    config.SMTP_HOST = "smtp.gmail.com"
    config.SMTP_USERNAME = "fake@gmail.com"
    config.SMTP_PASSWORD = "fake-app-password-not-real"
    config.EMAIL_FROM = "fake@gmail.com"
    try:
        assert email_service.is_configured() is True

        with patch("smtplib.SMTP") as mock_smtp:
            mock_smtp.return_value.__enter__.return_value = MagicMock()
            result = email_service.send_password_reset_email("someone@example.com", "https://x/reset/1")
        assert result.attempted is True and result.sent is True and result.error is None

        with patch("smtplib.SMTP") as mock_smtp:
            instance = mock_smtp.return_value.__enter__.return_value
            instance.login.side_effect = smtplib.SMTPAuthenticationError(535, b"bad creds")
            result = email_service.send_password_reset_email("someone@example.com", "https://x/reset/1")
        assert result.attempted is True and result.sent is False
        assert config.SMTP_PASSWORD not in (result.error or "")
    finally:
        config.EMAIL_PROVIDER = "console"


def test_email_sendgrid_success_and_failure_mocked():
    from backend.email import email_service
    config.EMAIL_PROVIDER = "sendgrid"
    config.SENDGRID_API_KEY = "SG.fake-key-not-real"
    config.EMAIL_FROM = "fake@neyan.example"
    try:
        assert email_service.is_configured() is True

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.status = 202
            mock_urlopen.return_value.__enter__.return_value = mock_resp
            result = email_service.send_password_reset_email("someone@example.com", "https://x/reset/1")
        assert result.attempted is True and result.sent is True

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)
            result = email_service.send_password_reset_email("someone@example.com", "https://x/reset/1")
        assert result.attempted is True and result.sent is False
        assert config.SENDGRID_API_KEY not in (result.error or "")
    finally:
        config.EMAIL_PROVIDER = "console"


def test_forgot_password_hides_dev_link_when_real_provider_configured(client):
    _register(client, "Real Send", "realsend@example.com")
    client.get("/logout")

    config.EMAIL_PROVIDER = "smtp"
    config.SMTP_HOST = "smtp.gmail.com"
    config.SMTP_USERNAME = "fake@gmail.com"
    config.SMTP_PASSWORD = "fake-app-password"
    config.EMAIL_FROM = "fake@gmail.com"
    try:
        with patch("smtplib.SMTP") as mock_smtp:
            instance = mock_smtp.return_value.__enter__.return_value
            r = client.get("/forgot-password")
            t = _form_token(r.get_data(as_text=True))
            r = client.post("/forgot-password", data={"csrf_token": t, "email": "realsend@example.com"})
            html = r.get_data(as_text=True)
        assert "/reset-password/" not in html
        assert "Development mode" not in html
        assert "a password reset link has been generated" in html
        assert instance.sendmail.called
    finally:
        config.EMAIL_PROVIDER = "console"


def test_production_never_exposes_reset_link_when_console_or_smtp_is_unavailable(client, monkeypatch):
    _register(client, "Production Reset", "production-reset@example.com")
    client.get("/logout")
    monkeypatch.setattr(config, "IS_PRODUCTION", True)
    monkeypatch.setattr(config, "EMAIL_PROVIDER", "console")
    r = client.get("/forgot-password")
    token = _form_token(r.get_data(as_text=True))
    r = client.post("/forgot-password", data={"csrf_token": token, "email": "production-reset@example.com"})
    assert "/reset-password/" not in r.get_data(as_text=True)
    monkeypatch.setattr(config, "EMAIL_PROVIDER", "smtp")
    monkeypatch.setattr(config, "SMTP_USERNAME", "")
    monkeypatch.setattr(config, "SMTP_PASSWORD", "")
    r = client.get("/forgot-password")
    token = _form_token(r.get_data(as_text=True))
    r = client.post("/forgot-password", data={"csrf_token": token, "email": "production-reset@example.com"})
    assert "/reset-password/" not in r.get_data(as_text=True)
