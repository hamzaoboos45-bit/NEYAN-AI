"""Regression coverage for server-owned pricing and private demand safety."""
from datetime import date, timedelta
import os
import tempfile

import config
import pytest


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    original = config.DATABASE_PATH
    config.DATABASE_PATH = path
    try:
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as test_client:
            yield test_client
    finally:
        config.DATABASE_PATH = original
        if os.path.exists(path):
            os.remove(path)


def identity(client, user_id, role):
    with client.session_transaction() as session:
        session.update(user_id=user_id, user_name="Pricing Test", role=role,
                       company_id=None, _csrf_token="pricing-test-token")


HEADERS = {"X-CSRFToken": "pricing-test-token"}


def request_payload(**changes):
    payload = {"from_city": "Amman", "to_city": "Aqaba", "sharing_mode": "shared",
               "requested_date": (date.today() + timedelta(days=30)).isoformat(),
               "requested_time_start": "10:00", "requested_time_end": "12:00",
               "passenger_quantity": 2, "desired_vehicle_type": "bus",
               "desired_trip_class": "economy"}
    payload.update(changes)
    return payload


def test_transport_policy_price_is_server_snapshot_and_private_is_not_joinable(client):
    identity(client, 1, "super_admin")
    created = client.post("/api/admin/pricing/transport-policies", json={
        "from_city": "Amman", "to_city": "Aqaba", "vehicle_type": "bus",
        "trip_class": "economy", "base_trip_price_jod": "12.500"}, headers=HEADERS)
    assert created.status_code == 201
    policy = created.get_json()["data"]
    assert policy["base_trip_price_jod"] == "12.500"

    identity(client, 2, "customer")
    shared = client.post("/api/trip-requests", json=request_payload(), headers=HEADERS)
    assert shared.status_code == 201
    card = shared.get_json()["data"]
    assert card["pricing_available"] and card["base_trip_price_jod"] == "12.500"

    private_payload = request_payload(requested_time_start="14:00", requested_time_end="15:00")
    private_payload.pop("sharing_mode")
    private = client.post("/api/trip-requests", json=private_payload, headers=HEADERS)
    private_id = private.get_json()["data"]["request_id"]
    identity(client, 3, "customer")
    assert client.post(f"/api/trip-requests/{private_id}/join", json={"passenger_quantity": 1}, headers=HEADERS).status_code == 403
    visible = client.get("/api/trip-requests").get_json()["data"]
    assert private_id not in [item["request_id"] for item in visible]


def test_maintenance_catalog_quote_and_request_snapshot(client):
    identity(client, 1, "super_admin")
    service = client.post("/api/admin/pricing/maintenance-services", json={
        "service_key": "inspection", "name_en": "Inspection", "name_ar": "فحص",
        "pricing_type": "range", "minimum_price_jod": "4.000", "maximum_price_jod": "7.000",
        "service_fee_jod": "1.000"}, headers=HEADERS)
    assert service.status_code == 201
    service_id = service.get_json()["data"]["service_id"]
    identity(client, 2, "customer")
    quote = client.post("/api/maintenance/quote", json={"catalog_service_id": service_id, "quantity": 2}, headers=HEADERS)
    assert quote.status_code == 200
    assert quote.get_json()["data"]["minimum_jod"] == "9.000"
    request = client.post("/api/maintenance/requests", json={"catalog_service_id": service_id,
        "quantity": 2, "service_type": "inspection", "location": "Amman", "preferred_date": "2031-01-01"}, headers=HEADERS)
    assert request.status_code == 201
    history = client.get("/api/maintenance/requests").get_json()
    assert history[0]["total_minimum_fils_snapshot"] == 9000
