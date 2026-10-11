"""Gate 7 static/template contracts for the shared UI shell and key surfaces."""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config


ROOT = os.path.join(os.path.dirname(__file__), "..")


def source(relative):
    with open(os.path.join(ROOT, relative), encoding="utf-8") as handle:
        return handle.read()


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
        app.config.update(TESTING=True, SECRET_KEY="gate7-ui-test-key")
        with app.test_client() as value:
            yield value
    finally:
        config.DATABASE_PATH = original
        if os.path.exists(path):
            os.remove(path)


def identity(client, role="customer", user_id=1, company_id=None):
    with client.session_transaction() as session:
        session.update(user_id=user_id, user_name="UI Contract", role=role, company_id=company_id)


def test_shared_tokens_selects_focus_motion_and_mobile_shell_contracts():
    tokens = source("frontend/static/css/tokens.css")
    css = source("frontend/static/css/main.css")
    for token in ("--primary:     var(--gold)", "--accent:      var(--gold)", "--select-option-bg", "--focus-ring"):
        assert token in tokens
    assert "@media (prefers-reduced-motion: reduce)" in tokens
    assert '[data-theme="light"] select { color-scheme: light; }' in css
    assert "select option, select optgroup" in css
    assert "overflow-x: clip" in css
    assert ".control-table-wrap { overflow-x: auto; }" in css


def test_shell_uses_localized_controls_role_navigation_and_keyboard_drawer_contracts(client):
    identity(client, "super_admin")
    html = client.get("/admin").get_data(as_text=True)
    shell = source("frontend/templates/base.html")
    i18n = source("frontend/static/js/theme-lang.js")
    assert 'data-i18n="navPricing"' in html
    assert 'data-i18n-label="languageControl"' in html
    assert 'data-i18n-label="themeControl"' in html
    assert "previousFocus = document.activeElement" in shell
    assert "closeBtn.focus()" in shell
    assert "trigger.focus()" in shell
    for key in ("navPricing", "brandSub", "languageControl", "themeControl"):
        assert key in i18n
    identity(client, "customer", 2)
    customer_html = client.get("/home").get_data(as_text=True)
    assert 'data-i18n="navTrips"' in customer_html
    assert 'data-i18n="navMaintenance"' in customer_html
    assert "Platform Dashboard" not in customer_html


def test_key_customer_surfaces_expose_localized_loading_labels_and_accessible_controls(client):
    identity(client)
    maintenance = client.get("/maintenance").get_data(as_text=True)
    chat = client.get("/chat").get_data(as_text=True)
    trips = client.get("/trips").get_data(as_text=True)
    assert 'data-i18n="historyLoading"' in maintenance
    assert 'data-i18n-label="voiceStart"' in chat
    assert 'role="log"' in chat and 'aria-live="polite"' in chat
    assert 'role="tablist"' in trips and '<dialog id="transportDialog"' in trips
    assert 'aria-label="Close"' in trips


def test_profile_localizes_role_status_and_mixed_direction_dates(client):
    identity(client)
    html = client.get("/profile").get_data(as_text=True)
    assert 'data-i18n="roleLabel"' in html
    assert 'data-i18n="statusLabel"' in html
    assert 'data-i18n="customer"' in html
    assert 'dir="ltr"' in html
    profile = source("frontend/templates/profile.html")
    for key in ("superAdmin", "companyAdmin", "active", "disabled", "unavailable"):
        assert key in profile


def test_admin_control_center_and_dynamic_ui_keep_accessibility_and_safe_dom_contracts(client):
    identity(client, "super_admin")
    html = client.get("/admin").get_data(as_text=True)
    admin_js = source("frontend/static/js/admin-control-center.js")
    transport_js = source("frontend/static/js/transportation.js")
    assert html.count('role="tab"') >= 6
    assert 'role="tabpanel"' in html
    assert 'role="status"' in html and 'role="alert"' in html
    assert "textContent" in admin_js and "innerHTML" not in admin_js
    assert "textContent" in transport_js
    assert 'current_passengers + " / " + card.minimum_passengers' in transport_js
    assert 'trip.from_city + " → " + trip.to_city' in transport_js


def test_shared_modern_layer_preserves_native_hidden_states_and_notification_empty_feedback(client):
    modern_css = source("frontend/static/css/modern.css")
    notifications = source("frontend/templates/notifications.html")
    notification_js = source("frontend/static/js/notification-center.js")
    assert "[hidden] { display: none !important; }" in modern_css
    assert 'aria-live="polite"' in notifications
    assert "notification-empty" in notification_js
    assert "emptyState" in notification_js


def test_login_keeps_rtl_brand_and_auth_card_in_a_single_grid_row():
    login = source("frontend/templates/login.html")
    assert '.tp-brand, [dir="rtl"] .tp-brand { grid-column: 1; grid-row: 1;' in login
    assert '.tp-card-wrap, [dir="rtl"] .tp-card-wrap { grid-column: 2; grid-row: 1;' in login
    assert '.tp-card-wrap, [dir="rtl"] .tp-card-wrap { grid-column: 1; grid-row: auto;' in login
    assert '[data-theme="light"] .tp-bg-scrim' in login


def test_login_uses_the_packaged_n_mark_with_responsive_logo_sizing():
    login = source("frontend/templates/login.html")
    n_mark = "brand/neyan-n-mark.svg"
    assert login.count(n_mark) >= 3  # favicon, header mark, and primary brand mark
    assert '<img class="tp-n-mark"' in login
    assert 'alt="NEYAN AI N mark"' in login
    assert "inline-size: clamp(68px, 7.25vw, 88px);" in login
    assert "object-fit: contain;" in login
    assert "brand/neyan-logo-full.png" not in login


def test_login_omits_the_removed_brand_message_and_keeps_trust_content_on_mobile():
    login = source("frontend/templates/login.html")
    for removed_message in (
        "Move smarter. Travel with confidence.",
        "Move master. Travel with confidance",
        "Move master",
        "Travel with confidance",
        "تنقّل بذكاء. انطلق بثقة.",
    ):
        assert removed_message not in login
    assert '<div class="tp-slogan" aria-hidden="true"></div>' in login
    assert "min-block-size: calc(1.45 * clamp(18px, 2vw, 24px));" in login
    assert "family=Tajawal" in login
    assert "[lang=\"ar\"] .tp-trust-label" in login
    assert ".tp-footer { display: block; padding: 4px 16px 18px; }" in login
    assert ".tp-trust { grid-template-columns: repeat(2, minmax(0, 1fr));" in login
