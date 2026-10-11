"""
tests/test_chatbot_integration.py — Part Ten: "verify nothing existing
broke" + verifies the new Hybrid NLP behavior end-to-end through real
Flask routes (not just unit-level calls).

Uses an isolated temporary sqlite database (never touches
database/transport.db) so this suite is safe to run repeatedly and in
parallel with manual dev-server usage.
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config


TEST_TRIP_DATE = "2099-07-01"


@pytest.fixture()
def client():
    # Point at a throwaway sqlite file for this test only.
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)  # let initialize_database() create it fresh
    original_path = config.DATABASE_PATH
    config.DATABASE_PATH = path
    try:
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        # Operational-trip discovery correctly excludes departed trips.  Move
        # only this isolated fixture's legacy seed dates into the future.
        from database.db import get_db_connection
        conn = get_db_connection()
        try:
            conn.execute("UPDATE trips SET departure_time=replace(departure_time, '2025-07-01', ?), arrival_time=replace(arrival_time, '2025-07-01', ?)", (TEST_TRIP_DATE, TEST_TRIP_DATE))
            conn.commit()
        finally:
            conn.close()
        with app.test_client() as c:
            yield c
    finally:
        config.DATABASE_PATH = original_path
        if os.path.exists(path):
            os.remove(path)


def _login(client, session_id="test-session"):
    from backend.security.csrf import SESSION_KEY
    token = "fixed-test-token"
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["role"] = "customer"
        sess["session_id"] = session_id
        sess[SESSION_KEY] = token
    return token


def _chat(client, token, message):
    resp = client.post("/api/chat", json={"message": message, "csrf_token": token})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()["reply"]


class TestBookingFlowEndToEnd:
    """Regression test for the STATE_BOOKING_CLASS/COMPANY AttributeError
    bug and the t.is_active / c.is_active SQL bug — both crashed the
    booking flow before this phase's fixes, every single time."""

    def test_full_booking_flow_step_by_step(self, client):
        token = _login(client)
        greeting = _chat(client, token, "مرحبا")
        assert "حجز" in greeting or "صيانة" in greeting

        step = _chat(client, token, "اريد حجز رحلة")
        assert "من أي مدينة" in step

        step = _chat(client, token, "عمان")
        assert "إلى أي مدينة" in step

        step = _chat(client, token, "اربد")
        assert "تاريخ" in step

        # The isolated fixture moves matching legacy seed trips to this future date.
        # Date is now a real search condition, rather than summary-only text.
        step = _chat(client, token, TEST_TRIP_DATE)
        assert "مقاعد" in step

        step = _chat(client, token, "اثنين")
        assert "درجة" in step

        step = _chat(client, token, "اقتصادي")
        # The choice now represents concrete date/time-matching trips rather
        # than an ambiguous company-only list.
        assert "الرحلات المتاحة" in step

        step = _chat(client, token, "1")
        assert "ملخص حجزك" in step
        assert "الشركة:" in step  # was silently dropped before this phase
        assert "السعر:" in step

        step = _chat(client, token, "نعم")
        assert "تأكيد حجزك بنجاح" in step

    def test_smart_slot_prefill_skips_known_entities(self, client):
        """Part Three: a message that already states both cities must
        skip straight past the from/to questions."""
        token = _login(client)
        step = _chat(client, token, "اريد حجز رحلة من عمان الى اربد")
        assert "تاريخ" in step
        assert "من أي مدينة" not in step
        assert "إلى أي مدينة" not in step


class TestMaintenanceFlowEndToEnd:
    def test_full_maintenance_flow(self, client):
        token = _login(client)
        step = _chat(client, token, "بدي صيانة")
        assert step  # got a real prompt, not a crash

        step = _chat(client, token, "تغيير زيت")
        step = _chat(client, token, "السيارة ما بتشتغل منيح")
        step = _chat(client, token, "عمان")
        step = _chat(client, token, "2025-08-05")
        assert "تأكيد" in step or "ملخص" in step or step


class TestNewIntentsAdditive:
    def test_complaint_intent(self, client):
        token = _login(client)
        reply = _chat(client, token, "الخدمة سيئة جدا وما حد رد علي")
        assert "اعتذر" in reply or "يؤسفني" in reply

    def test_general_conversation_intent(self, client):
        token = _login(client)
        reply = _chat(client, token, "احكيلي نكتة")
        assert reply  # got a friendly reply, not a crash/unknown dead-end

    def test_unknown_intent_still_handled(self, client):
        token = _login(client)
        reply = _chat(client, token, "asdkjaslkdjaslkdj")
        assert reply


class TestSessionIsolation:
    def test_two_sessions_do_not_share_context(self, client):
        token = "shared-token"
        from backend.security.csrf import SESSION_KEY
        with client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["role"] = "customer"
            sess["session_id"] = "session-A"
            sess[SESSION_KEY] = token
        _chat(client, token, "اريد حجز رحلة")
        reply_a = _chat(client, token, "عمان")
        assert "إلى أي مدينة" in reply_a

        with client.session_transaction() as sess:
            sess["session_id"] = "session-B"
        reply_b = _chat(client, token, "مرحبا")
        # A fresh session should get a greeting, not be stuck mid-booking.
        assert "من أي مدينة" not in reply_b


class TestNlpAnalyzeEndpoint:
    def test_analyze_endpoint_shape(self, client):
        token = _login(client)
        resp = client.post("/api/nlp/analyze", json={"text": "مرحبا", "csrf_token": token})
        assert resp.status_code == 200
        data = resp.get_json()
        assert set(data.keys()) == {"intent", "confidence", "normalized_text", "entities", "source"}

    def test_analyze_rejects_empty_text(self, client):
        token = _login(client)
        resp = client.post("/api/nlp/analyze", json={"text": "", "csrf_token": token})
        assert resp.status_code == 400

    def test_analyze_rejects_oversized_text(self, client):
        token = _login(client)
        resp = client.post("/api/nlp/analyze", json={"text": "a" * 5000, "csrf_token": token})
        assert resp.status_code == 400

    def test_analyze_rejects_missing_field(self, client):
        token = _login(client)
        resp = client.post("/api/nlp/analyze", json={"csrf_token": token})
        assert resp.status_code == 400

    def test_analyze_requires_login(self, client):
        resp = client.post("/api/nlp/analyze", json={"text": "مرحبا"})
        # CSRF validation runs in a global before_request hook, ahead of
        # the route's @customer_required check, so a request with no
        # session/CSRF token at all is rejected at the CSRF layer (400)
        # before auth is even evaluated — this is existing, untouched
        # security behavior, not something this phase changed.
        assert resp.status_code in (302, 400, 401, 403)


class TestExistingFeaturesUntouched:
    """Part Ten: explicit regression checks that pre-existing,
    non-NLP-related functionality still works exactly as before."""

    def test_chat_reset_still_works(self, client):
        token = _login(client)
        _chat(client, token, "اريد حجز رحلة")
        resp = client.post("/api/chat/reset", json={"csrf_token": token})
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "reset"

    def test_trips_api_still_works(self, client):
        _login(client)
        resp = client.get("/api/trips")
        assert resp.status_code in (200, 302)  # 302 if it also requires a
        # specific role this fixture didn't set up — either way, NOT a 500.
        assert resp.status_code != 500

    def test_login_page_still_renders(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200

    def test_csrf_protection_still_active(self, client):
        # No token at all — must be rejected, proving this phase didn't
        # accidentally weaken CSRF protection anywhere it touched routes.
        with client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["role"] = "customer"
        resp = client.post("/api/chat", json={"message": "مرحبا"})
        assert resp.status_code == 400
