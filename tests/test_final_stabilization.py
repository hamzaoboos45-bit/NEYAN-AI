"""Focused contracts for the Final Stabilization fixes."""

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


def _customer(client):
    with client.session_transaction() as session:
        session.update(user_id=2, user_name="Stabilization customer", role="customer", company_id=None, _csrf_token="stabilization-token")


def test_maintenance_page_has_complete_bilingual_static_and_dynamic_contract(client):
    _customer(client)
    html = client.get("/maintenance").get_data(as_text=True)
    source = open("frontend/templates/maintenance.html", encoding="utf-8").read() + open("frontend/static/js/maintenance-pricing.js", encoding="utf-8").read()

    assert "Request Maintenance Service" in html
    for required_key in (
        "maintenanceSubtitle", "requestDetails", "serviceType", "required",
        "sent", "requestError", "loadError", "noRequests", "inProgress",
    ):
        assert required_key in source
    assert "neyan:languagechange" in source
    assert "loadedRequests" in source
    assert "innerHTML" not in source
    assert "textContent" in source


def test_maintenance_history_and_empty_customer_contract_remain_valid(client):
    _customer(client)
    response = client.get("/api/maintenance/requests")
    assert response.status_code == 200
    assert isinstance(response.get_json(), list)


@pytest.mark.parametrize("payload", [None, [], {}, {"service_type": "invalid", "location": "Amman", "preferred_date": "2030-01-01"}, {"service_type": "engine", "location": "Amman", "preferred_date": "not-a-date"}])
def test_maintenance_request_invalid_input_is_a_safe_validation_error(client, payload):
    _customer(client)
    response = client.post(
        "/api/maintenance/requests",
        json=payload,
        headers={"X-CSRFToken": "stabilization-token"},
    )
    assert response.status_code == 400


def test_theme_tokens_cover_native_select_values_and_option_popup_in_both_modes():
    tokens = open("frontend/static/css/tokens.css", encoding="utf-8").read()
    css = open("frontend/static/css/main.css", encoding="utf-8").read()

    assert tokens.count("--select-option-bg:") == 2
    assert tokens.count("--select-option-text:") == 2
    assert 'select option, select optgroup' in css
    assert 'select option[value=""]' in css
    assert "select option:disabled" in css
    assert 'select { color-scheme: dark;' in css
    assert '[data-theme="light"] select { color-scheme: light;' in css


def test_catalog_maintenance_ui_relocalizes_existing_options_quotes_and_results():
    """A later English/Arabic switch updates injected catalog UI without refetching."""
    source = open("frontend/static/js/maintenance-pricing.js", encoding="utf-8").read()

    assert 'document.addEventListener("neyan:languagechange"' in source
    assert "function renderCatalog()" in source
    assert "option.dataset.catalogServiceId" in source
    assert "function renderQuote()" in source
    assert "function setResult(" in source
    assert "sent" in source and "requestError" in source
    assert 'fetch("/api/maintenance/catalog")' in source
    assert source.count('fetch("/api/maintenance/catalog")') == 1
