"""Regression coverage for final Intro, Sign In, and Home startup fixes."""
import os
import tempfile

import pytest

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


def _customer(client, user_id=2):
    with client.session_transaction() as session:
        session.update(user_id=user_id, user_name="Pre-closure Customer", role="customer", company_id=None)


def test_intro_is_typographic_and_has_no_logo_or_light_hero(client):
    html = client.get("/intro").get_data(as_text=True)
    with open("frontend/static/css/intro.css", encoding="utf-8") as handle:
        css = handle.read()

    assert 'id="introName"' in html and "NEYAN <em>AI</em>" in html
    assert "neyan-logo-full.png" not in html
    assert "<img" not in html
    for removed in ("intro-grid", "intro-orb", "wordGlow", "introPulse", "drop-shadow", "radial-gradient"):
        assert removed not in css
    assert "prefers-reduced-motion" in css


def test_login_uses_packaged_vector_n_mark_and_keeps_auth_form(client):
    html = client.get("/login").get_data(as_text=True)

    assert "neyan-logo-full.png" not in html
    assert "tp-full-logo" not in html
    assert '<img class="tp-n-mark"' in html
    assert "brand/neyan-n-mark.svg" in html
    assert "loginNBlue" not in html
    assert "name=\"email\"" in html and "name=\"password\"" in html
    assert "csrf_token" in html and "/forgot-password" in html and "/register" in html


def test_home_startup_has_one_ready_path_and_one_in_flight_request(client):
    with open("frontend/static/js/home-dashboard.js", encoding="utf-8") as handle:
        source = handle.read()

    assert "document.readyState" in source
    assert "var initialized = false" in source
    assert "var inFlightLoad = null" in source
    assert source.count('fetch("/api/dashboard/home")') == 1
    assert "if (inFlightLoad) return inFlightLoad" in source

    _customer(client)
    first = client.get("/api/dashboard/home")
    refresh = client.get("/api/dashboard/home")
    assert first.status_code == 200 and refresh.status_code == 200
    assert first.get_json()["data"]["summary"] == refresh.get_json()["data"]["summary"]


def test_empty_customer_home_and_unauthorized_boundary_remain_valid(client):
    assert client.get("/api/dashboard/home").status_code == 401
    _customer(client, user_id=4)
    payload = client.get("/api/dashboard/home").get_json()
    assert payload["data"]["summary"]["total_bookings"] == 0
    assert payload["data"]["recent_bookings"] == []


def test_dashboard_recovers_after_a_temporary_service_failure(client, monkeypatch):
    """The retry target remains a normal protected request after recovery."""
    from routes import dashboard_routes

    _customer(client)
    original = dashboard_routes.DashboardService.user_home

    def unavailable(*_args, **_kwargs):
        raise RuntimeError("temporary dashboard outage")

    monkeypatch.setattr(dashboard_routes.DashboardService, "user_home", unavailable)
    failed = client.get("/api/dashboard/home")
    assert failed.status_code == 500
    assert failed.get_json()["error"]["code"] == "dashboard_unavailable"

    monkeypatch.setattr(dashboard_routes.DashboardService, "user_home", original)
    recovered = client.get("/api/dashboard/home")
    assert recovered.status_code == 200
    assert recovered.get_json()["data"]["summary"]["total_bookings"] >= 0
