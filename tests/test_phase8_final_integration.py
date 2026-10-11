"""Final Phase 8 integration boundaries: roles and shared-script ordering."""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config


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
        session["user_name"] = "Final integration test"


def test_phase8_private_api_role_matrix_and_direct_access_boundaries(client):
    for path in ("/api/dashboard/home", "/api/dashboard/admin", "/api/bookings"):
        assert client.get(path).status_code == 401

    _identity(client, 2, "customer")
    assert client.get("/api/dashboard/home").status_code == 200
    assert client.get("/api/dashboard/admin").status_code == 403
    assert client.get("/api/dashboard/home?company_id=1").status_code == 400

    _identity(client, 4, "company_admin", company_id=1)
    assert client.get("/api/dashboard/admin").status_code == 200
    assert client.get("/api/dashboard/home").status_code == 403
    assert client.get("/api/dashboard/admin?user_id=2").status_code == 400

    _identity(client, 1, "super_admin")
    assert client.get("/api/dashboard/admin").status_code == 200
    assert client.get("/api/dashboard/home").status_code == 403


def test_phase8_page_scripts_run_after_shared_csrf_and_language_initialization(client):
    _identity(client, 2, "customer")
    home = client.get("/home").get_data(as_text=True)
    assert home.index("js/csrf.js") < home.index("js/theme-lang.js") < home.index("js/home-dashboard.js")

    _identity(client, 1, "super_admin")
    admin = client.get("/admin").get_data(as_text=True)
    assert admin.index("js/csrf.js") < admin.index("js/theme-lang.js") < admin.index("js/admin-analytics.js") < admin.index("js/admin.js")
