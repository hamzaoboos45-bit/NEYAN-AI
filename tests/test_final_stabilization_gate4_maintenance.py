"""Gate 4 regression coverage: maintenance creation, pricing, and history."""
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
    previous = config.DATABASE_PATH
    config.DATABASE_PATH = path
    try:
        from app import create_app

        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as test_client:
            yield test_client
    finally:
        config.DATABASE_PATH = previous
        if os.path.exists(path):
            os.remove(path)


def identity(client, user_id=2, role="customer", session_id="gate4"):
    from backend.security.csrf import SESSION_KEY

    with client.session_transaction() as session:
        session.update(user_id=user_id, role=role, session_id=session_id, **{SESSION_KEY: "gate4-csrf"})
    return {"X-CSRFToken": "gate4-csrf"}


def create_catalog(client, *, service_key="oil_change", pricing_type="fixed", minimum="10.000", maximum="15.000", unit="12.000", fee="1.000", quantity_enabled=True):
    identity(client, 1, "super_admin")
    payload = {
        "service_key": service_key,
        "name_en": f"{service_key} service",
        "name_ar": f"خدمة {service_key}",
        "pricing_type": pricing_type,
        "service_fee_jod": fee,
        "quantity_enabled": quantity_enabled,
    }
    if pricing_type == "fixed":
        payload["unit_price_jod"] = unit
    else:
        payload.update(minimum_price_jod=minimum, maximum_price_jod=maximum)
    response = client.post("/api/admin/pricing/maintenance-services", json=payload, headers={"X-CSRFToken": "gate4-csrf"})
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()["data"]


def chat(client, message):
    response = client.post("/api/chat", json={"message": message, "csrf_token": "gate4-csrf"})
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()["reply"]


def test_chat_relative_date_is_normalized_before_authoritative_create(client):
    """Reproduces the reported final-date failure with the existing supported word بكرا."""
    create_catalog(client)
    identity(client)
    for message in ("بدي صيانة", "تغيير زيت", "تغيير الزيت ضروري", "عمان", "بكرا"):
        reply = chat(client, message)
    assert "تأكيد" in reply
    completed = chat(client, "نعم")
    assert "تم استلام طلب الصيانة" in completed


def test_fixed_quote_page_creation_snapshot_history_and_forged_fields(client):
    service = create_catalog(client, unit="12.000", fee="1.000")
    identity(client)
    quote = client.post("/api/maintenance/quote", json={"catalog_service_id": service["service_id"], "quantity": 2}, headers={"X-CSRFToken": "gate4-csrf"})
    assert quote.status_code == 200
    assert quote.get_json()["data"]["minimum_jod"] == "25.000"
    forged = client.post("/api/maintenance/requests", json={
        "service_type": "oil_change", "catalog_service_id": service["service_id"], "quantity": 2,
        "location": "Amman", "preferred_date": "2030-07-01", "user_id": 1, "status": "completed",
        "total": "0.001", "service_fee": "0.001", "minimum_price": "0.001",
    }, headers={"X-CSRFToken": "gate4-csrf"})
    assert forged.status_code == 400
    assert forged.get_json()["code"] == "forbidden_field"
    created = client.post("/api/maintenance/requests", json={
        "service_type": "oil_change", "catalog_service_id": service["service_id"], "quantity": 2,
        "service_details": "Oil and filter", "location": "Amman", "preferred_date": "2030-07-01",
        "notes": "Call first",
    }, headers={"X-CSRFToken": "gate4-csrf"})
    assert created.status_code == 201
    request_id = created.get_json()["request_id"]
    history = client.get("/api/maintenance/requests").get_json()
    row = next(item for item in history if item["request_id"] == request_id)
    assert row["price_semantics"] == "fixed_request_snapshot"
    assert row["total_minimum_jod"] == row["total_maximum_jod"] == "25.000"
    from database.db import get_db_connection
    conn = get_db_connection()
    try:
        persisted = conn.execute("SELECT user_id,status,quantity,total_minimum_fils_snapshot,notes FROM maintenance_requests WHERE request_id=?", (request_id,)).fetchone()
        assert tuple(persisted) == (2, "pending", 2, 25000, "Call first")
    finally:
        conn.close()


def test_range_and_inspection_snapshots_survive_catalog_price_change(client):
    service = create_catalog(client, service_key="engine", pricing_type="range", minimum="10.000", maximum="15.000", fee="1.000")
    identity(client)
    original = client.post("/api/maintenance/requests", json={
        "service_type": "engine", "catalog_service_id": service["service_id"], "quantity": 2,
        "location": "Irbid", "preferred_date": "2030-07-01",
    }, headers={"X-CSRFToken": "gate4-csrf"})
    assert original.status_code == 201
    request_id = original.get_json()["request_id"]
    identity(client, 1, "super_admin")
    changed = client.patch(f"/api/admin/pricing/maintenance-services/{service['service_id']}", json={
        "minimum_price_jod": "20.000", "maximum_price_jod": "30.000",
    }, headers={"X-CSRFToken": "gate4-csrf"})
    assert changed.status_code == 200
    identity(client)
    new_quote = client.post("/api/maintenance/quote", json={"catalog_service_id": service["service_id"], "quantity": 2}, headers={"X-CSRFToken": "gate4-csrf"}).get_json()["data"]
    assert (new_quote["minimum_jod"], new_quote["maximum_jod"]) == ("41.000", "61.000")
    history = client.get("/api/maintenance/requests").get_json()
    old = next(item for item in history if item["request_id"] == request_id)
    assert old["price_semantics"] == "estimated_range_request_snapshot"
    assert (old["total_minimum_jod"], old["total_maximum_jod"]) == ("21.000", "31.000")
    inspection = client.post("/api/maintenance/requests", json={
        "service_type": "other", "service_details": "Needs diagnosis", "location": "Irbid", "preferred_date": "2030-07-02",
    }, headers={"X-CSRFToken": "gate4-csrf"})
    assert inspection.status_code == 201
    history = client.get("/api/maintenance/requests").get_json()
    inspection_row = next(item for item in history if item["request_id"] == inspection.get_json()["request_id"])
    assert inspection_row["price_semantics"] == "inspection_required"
    assert inspection_row["total_minimum_jod"] is None


def test_existing_style_unpriced_catalog_is_truthful_inspection_not_a_server_error(client):
    from database.db import get_db_connection
    identity(client, 1, "super_admin")
    conn = get_db_connection()
    try:
        service_id = conn.execute(
            """INSERT INTO maintenance_service_catalog
               (service_key,name_en,name_ar,pricing_type,unit_price_fils,is_active,quantity_enabled)
               VALUES ('battery','Battery assessment','فحص البطارية','fixed',NULL,1,1)"""
        ).lastrowid
        conn.commit()
    finally:
        conn.close()
    identity(client)
    quote = client.post("/api/maintenance/quote", json={"catalog_service_id": service_id, "quantity": 1}, headers={"X-CSRFToken": "gate4-csrf"})
    assert quote.status_code == 200
    assert quote.get_json()["data"]["pricing_available"] is False
    created = client.post("/api/maintenance/requests", json={
        "service_type": "battery", "catalog_service_id": service_id, "location": "Amman", "preferred_date": "2030-07-01",
    }, headers={"X-CSRFToken": "gate4-csrf"})
    assert created.status_code == 201
    request = next(item for item in client.get("/api/maintenance/requests").get_json() if item["request_id"] == created.get_json()["request_id"])
    assert request["price_semantics"] == "inspection_required"


def test_invalid_date_has_no_write_and_history_is_owner_scoped_and_reloadable(client):
    service = create_catalog(client)
    identity(client)
    csrf_denied = client.post("/api/maintenance/requests", json={
        "service_type": "oil_change", "catalog_service_id": service["service_id"], "location": "Amman", "preferred_date": "2030-07-01",
    })
    assert csrf_denied.status_code == 400  # existing CSRF handler's safe rejection contract
    invalid = client.post("/api/maintenance/requests", json={
        "service_type": "oil_change", "catalog_service_id": service["service_id"], "location": "Amman", "preferred_date": "not-a-date",
    }, headers={"X-CSRFToken": "gate4-csrf"})
    assert invalid.status_code == 400 and invalid.get_json()["code"] == "invalid_date"
    before = client.get("/api/maintenance/requests").get_json()
    assert all(item["service_type"] != "oil_change" or item["catalog_service_id"] != service["service_id"] for item in before)
    made = client.post("/api/maintenance/requests", json={
        "service_type": "oil_change", "catalog_service_id": service["service_id"], "location": "Amman", "preferred_date": "2030-07-01",
    }, headers={"X-CSRFToken": "gate4-csrf"})
    assert made.status_code == 201
    request_id = made.get_json()["request_id"]
    # A fresh same-customer session models Chat/Home navigation, refresh, and re-login.
    identity(client, 2, "customer", "gate4-relogin")
    refreshed = client.get("/api/maintenance/requests").get_json()
    assert request_id in [item["request_id"] for item in refreshed]
    identity(client, 3, "customer", "gate4-other-user")
    assert request_id not in [item["request_id"] for item in client.get("/api/maintenance/requests").get_json()]
    with client.session_transaction() as session:
        session.clear()
    assert client.get("/api/maintenance/requests").status_code in {302, 401, 403}


def test_chat_fixed_price_confirmation_is_single_real_write_and_maintenance_specific(client):
    service = create_catalog(client, unit="8.000", fee="1.000")
    identity(client)
    from database.db import get_db_connection
    conn = get_db_connection()
    try:
        before = conn.execute("SELECT COUNT(*) FROM maintenance_requests WHERE user_id=2").fetchone()[0]
    finally:
        conn.close()
    for message in ("بدي صيانة", "تغيير زيت", "تغيير زيت", "عمان", "2030-07-01"):
        reply = chat(client, message)
    assert "9.000" in reply and "طلب الصيانة" in reply
    assert "طلب الرحلة" not in reply
    assert "تم استلام طلب الصيانة" in chat(client, "نعم")
    assert "لا توجد نتيجة سابقة" not in chat(client, "نعم")
    conn = get_db_connection()
    try:
        rows = conn.execute("SELECT user_id,catalog_service_id,total_minimum_fils_snapshot FROM maintenance_requests WHERE user_id=2").fetchall()
        assert len(rows) == before + 1
        assert tuple(rows[-1]) == (2, service["service_id"], 9000)
    finally:
        conn.close()
