"""Regression coverage for real-browser dashboard and Chat date defect closure."""

import os
import tempfile

import pytest

import config
from backend.nlp.normalizer import classify_future_travel_date


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    previous = config.DATABASE_PATH
    config.DATABASE_PATH = path
    try:
        from app import create_app
        app = create_app()
        app.config.update(TESTING=True, SECRET_KEY="post-gate8-test-key")
        with app.test_client() as test_client:
            yield test_client
    finally:
        config.DATABASE_PATH = previous
        if os.path.exists(path):
            os.remove(path)


def _identity(client, user_id=1):
    with client.session_transaction() as session:
        session.update(user_id=user_id, user_name="Defect QA", role="customer", company_id=None, _csrf_token="defect-token")


def _chat(client, message):
    response = client.post("/api/chat", json={"message": message, "csrf_token": "defect-token"})
    assert response.status_code == 200
    return response.get_json()["reply"]


def _counts():
    from database.db import get_db_connection
    conn = get_db_connection()
    try:
        return tuple(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("bookings", "trip_requests", "trip_request_members"))
    finally:
        conn.close()


def test_dashboard_asset_version_and_state_machine_keep_error_loading_content_exclusive(client):
    _identity(client)
    page = client.get("/home")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "home-dashboard.js?v=post-gate8-defect-closure-1" in html
    source = open("frontend/static/js/home-dashboard.js", encoding="utf-8").read()
    assert "function setDashboardState(nextState)" in source
    assert 'loading.hidden = nextState !== "loading"' in source
    assert 'errorBox.hidden = nextState !== "error"' in source
    assert 'content.hidden = nextState !== "success"' in source
    assert source.count('fetch("/api/dashboard/home")') == 1


def test_invalid_and_past_travel_dates_do_not_search_or_mutate_and_correct_date_keeps_route(client, monkeypatch):
    _identity(client)
    from backend.transportation.booking_service import BookingService
    from backend.transportation.trip_request_service import TripRequestService

    monkeypatch.setattr(BookingService, "search_compatible", staticmethod(lambda **_kwargs: pytest.fail("invalid date reached booking search")))
    monkeypatch.setattr(TripRequestService, "compatible", staticmethod(lambda *_args, **_kwargs: pytest.fail("invalid date reached forming search")))
    before = _counts()
    _chat(client, "حجز")
    _chat(client, "عمان")
    _chat(client, "العقبة")
    assert "التاريخ غير صحيح" in _chat(client, "31/02/2030")
    assert "تاريخ سفر صحيحاً ومستقبلياً" in _chat(client, "لماذا؟")
    assert "التاريخ غير صحيح" in _chat(client, "2026-99-99")
    assert "تاريخاً قادماً" in _chat(client, "01/01/2025")
    assert _counts() == before
    continued = _chat(client, "15/09/2030")
    assert "عدد المقاعد" in continued
    assert _counts() == before


def test_date_classifier_normalizes_supported_dates_and_distinguishes_invalid_past_missing():
    assert classify_future_travel_date("15/09/2030").value == "2030-09-15"
    assert classify_future_travel_date("٢٠٣٠-٠٩-١٥").value == "2030-09-15"
    assert classify_future_travel_date("31/02/2030").status == "invalid"
    assert classify_future_travel_date("15/15/2030").status == "invalid"
    assert classify_future_travel_date("40/10/2030").status == "invalid"
    assert classify_future_travel_date("01/01/2025").status == "past"
    assert classify_future_travel_date("لا أعرف").status == "missing"


def test_date_classifier_accepts_persisted_relative_date_tokens():
    result = classify_future_travel_date("tomorrow")
    assert result.status == "valid"
    assert result.value is not None
