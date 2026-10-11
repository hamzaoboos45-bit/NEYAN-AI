"""Focused Company Admin operational-dashboard regression coverage."""

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


def _identity(client, role, company_id=None):
    with client.session_transaction() as session:
        session.update(user_id=4, user_name="Company Admin", role=role, company_id=company_id)


def test_company_admin_page_exposes_real_operational_dashboard_sections(client):
    _identity(client, "company_admin", 1)
    response = client.get("/admin")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    for marker in (
        "companyDashboardKpis",
        "companyUpcomingTrips",
        "companyRecentBookings",
        "companyMaintenanceRequests",
        "demandAdminQueue",
        "company-admin-dashboard.js",
        "admin-forming-trips.js",
    ):
        assert marker in html
    assert "control-center.js" not in html


def test_company_dashboard_client_uses_one_server_scoped_contract_without_identity_selectors():
    root = os.path.join(os.path.dirname(__file__), "..", "frontend", "static", "js")
    with open(os.path.join(root, "company-admin-dashboard.js"), encoding="utf-8") as handle:
        source = handle.read()

    assert source.count('fetch("/api/dashboard/admin"') == 1
    assert "company_id=" not in source
    assert "company_id:" not in source
    assert "JSON.stringify" not in source
    assert "innerHTML" not in source
    assert "neyan:languagechange" in source
    assert "Total trips" in source and "إجمالي الرحلات" in source


def test_company_admin_page_is_not_available_to_customers_and_admin_endpoint_remains_server_scoped(client):
    _identity(client, "customer")
    assert client.get("/admin").status_code == 302
    assert client.get("/api/dashboard/admin").status_code == 403

    _identity(client, "company_admin", 1)
    response = client.get("/api/dashboard/admin?company_id=2")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_query"
