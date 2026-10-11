"""Regression contract for Jordan governorate-level route controls."""

from datetime import date, timedelta
import html as html_module
import json
import os
import re
import tempfile

import pytest

import config
from backend.nlp.normalizer import normalize_city
from backend.transportation.trip_request_service import _validate_intent


EXPECTED_ENGLISH = [
    "Amman", "Irbid", "Zarqa", "Balqa", "Mafraq", "Jerash",
    "Ajloun", "Madaba", "Karak", "Tafilah", "Ma'an", "Aqaba",
]
EXPECTED_ARABIC = [
    "عمّان", "إربد", "الزرقاء", "البلقاء", "المفرق", "جرش",
    "عجلون", "مادبا", "الكرك", "الطفيلة", "معان", "العقبة",
]


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


def _identity(client, role="customer"):
    with client.session_transaction() as session:
        session.update(user_id=1, role=role, user_name="Governorate Test", company_id=None)


def test_canonical_dataset_is_exactly_the_ordered_twelve_governorates():
    assert len(config.JORDAN_GOVERNORATES) == 12
    assert [item["key"] for item in config.JORDAN_GOVERNORATES] == [
        "amman", "irbid", "zarqa", "balqa", "mafraq", "jerash",
        "ajloun", "madaba", "karak", "tafilah", "maan", "aqaba",
    ]
    assert [item["en"] for item in config.JORDAN_GOVERNORATES] == EXPECTED_ENGLISH
    assert [item["ar"] for item in config.JORDAN_GOVERNORATES] == EXPECTED_ARABIC
    assert len({item["key"] for item in config.JORDAN_GOVERNORATES}) == 12
    assert len(set(config.GOVERNORATE_STORAGE_VALUES)) == 12
    assert config.SUPPORTED_CITIES == list(config.GOVERNORATE_STORAGE_VALUES)


def test_nlp_and_forming_validation_accept_both_language_labels_for_all_governorates():
    future = (date.today() + timedelta(days=30)).isoformat()
    for item in config.JORDAN_GOVERNORATES:
        assert normalize_city(item["en"]) == item["storage"]
        assert normalize_city(item["ar"]) == item["storage"]
        validated = _validate_intent({
            "from_city": item["en"], "to_city": "Aqaba" if item["key"] != "aqaba" else "Amman",
            "requested_date": future, "requested_time_start": "09:00", "requested_time_end": "10:00",
            "desired_vehicle_type": "bus", "desired_trip_class": "economy",
        }, for_search=True)
        assert validated["from_city"] == item["storage"]


def test_transportation_and_admin_governorate_selectors_render_complete_bilingual_contract(client):
    _identity(client)
    trips = client.get("/trips")
    assert trips.status_code == 200
    trip_html = trips.get_data(as_text=True)
    assert trip_html.count("data-governorate-option") == 24
    rendered_contract = json.loads(re.search(r"window.NEYAN_GOVERNORATES=(.*?);</script>", trip_html).group(1))
    assert rendered_contract == list(config.JORDAN_GOVERNORATES)
    for item in config.JORDAN_GOVERNORATES:
        assert item["storage"] in trip_html
        assert item["ar"] in trip_html
    assert "NEYAN_GOVERNORATES" in trip_html

    _identity(client, "super_admin")
    admin_html = client.get("/admin").get_data(as_text=True)
    legacy_html = client.get("/admin/pricing").get_data(as_text=True)
    for html in (admin_html, legacy_html):
        decoded_html = html_module.unescape(html)
        for item in config.JORDAN_GOVERNORATES:
            assert item["storage"] in decoded_html
            assert item["en"] in decoded_html
            assert item["ar"] in decoded_html
    assert '<input id="policyFrom"' not in admin_html
    assert '<input id="policyTo"' not in admin_html


def test_search_normalizes_english_and_rejects_unknown_governorates(client):
    _identity(client)
    response = client.get("/api/trips?from=Amman&to=Aqaba")
    assert response.status_code == 200
    assert response.get_json() == []
    invalid = client.get("/api/trips?from=Not-A-Governorate")
    assert invalid.status_code == 400
    assert invalid.get_json()["code"] == "invalid_governorate"


def test_active_governorate_surfaces_do_not_reintroduce_partial_hardcoded_lists():
    root = os.path.dirname(os.path.dirname(__file__))
    transportation = open(os.path.join(root, "frontend", "static", "js", "transportation.js"), encoding="utf-8").read()
    trips = open(os.path.join(root, "frontend", "templates", "trips.html"), encoding="utf-8").read()
    admin = open(os.path.join(root, "frontend", "templates", "admin.html"), encoding="utf-8").read()
    assert "var CITIES" not in transportation
    assert "GOVERNORATES.map" in transportation
    assert "jordan_governorates" in trips
    assert "jordan_governorates" in admin
