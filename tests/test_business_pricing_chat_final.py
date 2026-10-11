"""Final-pass coverage for Chat orchestration of authoritative business services."""
import os
import tempfile
from pathlib import Path

import config
import pytest


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    old_path = config.DATABASE_PATH
    config.DATABASE_PATH = path
    try:
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as test_client:
            yield test_client
    finally:
        config.DATABASE_PATH = old_path
        if os.path.exists(path):
            os.remove(path)


def identity(client, user_id, role):
    with client.session_transaction() as session:
        session.update(user_id=user_id, user_name="Chat Pricing Test", role=role,
                       company_id=None, _csrf_token="chat-pricing-token")


def chat(client, message):
    response = client.post("/api/chat", json={"message": message, "csrf_token": "chat-pricing-token"})
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()["reply"]


def test_chat_uses_catalog_snapshot_and_safe_why_context(client):
    identity(client, 1, "super_admin")
    created = client.post("/api/admin/pricing/maintenance-services", json={
        "service_key": "engine", "name_en": "Engine check", "name_ar": "فحص المحرك",
        "pricing_type": "range", "minimum_price_jod": "10.000", "maximum_price_jod": "15.000"},
        headers={"X-CSRFToken": "chat-pricing-token"})
    assert created.status_code == 201

    identity(client, 2, "customer")
    first = chat(client, "السلام عليكم عندي عطل بالمحرك")
    assert "10.000" in first and "15.000" in first and "نهائي" in first
    chat(client, "صوت في المحرك")
    chat(client, "شارع الجامعة، عمان")
    confirmation = chat(client, "2030-07-01")
    assert "تأكيد" in confirmation
    assert "تم استلام طلب الصيانة" in chat(client, "نعم")

    from database.db import get_db_connection
    conn = get_db_connection()
    try:
        request = conn.execute("SELECT catalog_service_id,total_minimum_fils_snapshot,total_maximum_fils_snapshot FROM maintenance_requests WHERE user_id=2 ORDER BY request_id DESC LIMIT 1").fetchone()
        assert (request["total_minimum_fils_snapshot"], request["total_maximum_fils_snapshot"]) == (10000, 15000)
    finally:
        conn.close()

    chat(client, "حجز")
    chat(client, "عمان")
    chat(client, "العقبة")
    chat(client, "2030-07-01")
    chat(client, "شخصين")
    assert "مشترك" in chat(client, "اقتصادي")
    assert "لم يتم إنشاء" in chat(client, "لا")
    why = chat(client, "ليش؟")
    assert "لم يتم إنشاء" in why


def test_maintenance_creation_rejects_forged_catalog_price_fields(client):
    identity(client, 2, "customer")
    rejected = client.post("/api/maintenance/requests", json={
        "service_type": "other", "location": "Amman", "preferred_date": "2030-07-01",
        "total_price": "0.001", "user_id": 1}, headers={"X-CSRFToken": "chat-pricing-token"})
    assert rejected.status_code == 400
    assert rejected.get_json()["code"] == "forbidden_field"


def test_maintenance_standard_form_notes_are_accepted_and_catalog_ui_reloads_history(client):
    """The single maintenance handler stores notes and reloads server history once."""
    identity(client, 2, "customer")
    response = client.post("/api/maintenance/requests", json={
        "service_type": "engine", "service_details": "Intermittent starting issue",
        "location": "Amman", "preferred_date": "2030-01-02",
        "customer_name": "Customer", "customer_phone": "0790000000",
        "notes": "Please call first"}, headers={"X-CSRFToken": "chat-pricing-token"})
    assert response.status_code == 201

    project_root = Path(__file__).parents[1]
    template = (project_root / "frontend" / "templates" / "maintenance.html").read_text(encoding="utf-8")
    catalog_script = (project_root / "frontend" / "static" / "js" / "maintenance-pricing.js").read_text(encoding="utf-8")
    assert 'form.addEventListener("submit",submitRequest)' in catalog_script
    assert catalog_script.count('form.addEventListener("submit",submitRequest)') == 1
    assert 'await loadMyRequests()' in catalog_script
    assert 'neyan:maintenance-request-created' not in template
