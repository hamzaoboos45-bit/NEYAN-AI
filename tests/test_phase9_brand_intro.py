"""Phase 9 regression coverage for branded entry routing and static assets."""
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


def _intro_destination(client, role=None):
    with client.session_transaction() as session:
        session.clear()
        if role:
            session.update(user_id=1, user_name="Phase 9", role=role, company_id=None)
    response = client.get("/intro")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_root_enters_intro_and_destinations_are_server_selected(client):
    root = client.get("/")
    assert root.status_code == 302
    assert root.headers["Location"].endswith("/intro")

    assert 'NEYAN_INTRO_DESTINATION="/login"' in _intro_destination(client)
    assert 'NEYAN_INTRO_DESTINATION="/home"' in _intro_destination(client, "customer")
    assert 'NEYAN_INTRO_DESTINATION="/admin"' in _intro_destination(client, "company_admin")
    assert 'NEYAN_INTRO_DESTINATION="/admin"' in _intro_destination(client, "super_admin")


def test_pending_feedback_bypasses_intro_so_auth_messages_remain_visible(client):
    with client.session_transaction() as session:
        session.update(user_id=1, user_name="Phase 9", role="customer", company_id=None)
        session["_flashes"] = [("success", "Password reset complete")]
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/home")


def test_intro_assets_and_login_brand_are_available(client):
    for asset in ("brand/neyan-n-mark.svg", "brand/neyan-logo.svg"):
        response = client.get(f"/static/{asset}")
        assert response.status_code == 200
        assert b"<svg" in response.data

    full_logo = client.get("/static/brand/neyan-logo-full.png")
    assert full_logo.status_code == 200
    assert full_logo.data.startswith(b"\x89PNG")

    intro = client.get("/intro").get_data(as_text=True)
    login = client.get("/login").get_data(as_text=True)
    assert "brand/neyan-n-mark.svg" in intro
    assert "intro.js" in intro
    assert "intro-approved-logo" not in intro
    assert "brand/neyan-logo-full.png" not in intro
    assert "brand/neyan-n-mark.svg" in login
    assert "brand/neyan-logo-full.png" not in login
    assert 'class="tp-n-mark"' in login


def test_intro_does_not_relax_protected_routes(client):
    assert client.get("/home").status_code == 302
    assert client.get("/admin").status_code == 302


def test_branded_home_admin_and_chat_pages_still_render(client):
    with client.session_transaction() as session:
        session.update(user_id=1, user_name="Phase 9", role="customer", company_id=None)
    assert client.get("/home").status_code == 200
    assert client.get("/chat").status_code == 200

    with client.session_transaction() as session:
        session.update(user_id=1, user_name="Phase 9", role="super_admin", company_id=None)
    assert client.get("/admin").status_code == 200
