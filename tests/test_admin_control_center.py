"""Super Admin Control Center contracts: real data, bounds, and scope."""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd); os.remove(path)
    original = config.DATABASE_PATH; config.DATABASE_PATH = path
    try:
        from app import create_app
        app = create_app(); app.config["TESTING"] = True
        with app.test_client() as value: yield value
    finally:
        config.DATABASE_PATH = original
        if os.path.exists(path): os.remove(path)


def _identity(client, role="super_admin", user_id=1, company_id=None):
    with client.session_transaction() as session:
        session["user_id"] = user_id; session["role"] = role; session["company_id"] = company_id


def _clear_business_data():
    """Create an honest no-data state without adding browser-only fixtures."""
    from database.db import get_db_connection
    conn = get_db_connection()
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        for table in (
            "activity_logs", "notifications", "reviews", "bookings", "trips",
            "trip_request_members", "trip_requests", "maintenance_requests",
            "transport_pricing_policies", "maintenance_service_catalog", "companies", "users",
        ):
            conn.execute("DELETE FROM " + table)
        conn.commit()
    finally:
        conn.close()


def test_control_center_overview_uses_real_status_aggregates_without_loading_company_or_activity_previews(client):
    from database.db import get_db_connection
    conn = get_db_connection()
    try:
        before = conn.execute("""SELECT COALESCE(SUM(status='confirmed'),0), COALESCE(SUM(status='pending'),0),
            COALESCE(SUM(CASE WHEN status='confirmed' AND payment_status='paid' THEN total_price ELSE 0 END),0) FROM bookings""").fetchone()
        company = conn.execute("INSERT INTO companies(name,name_ar,company_type,status) VALUES ('Real Transport','نقل حقيقي','transport','active')").lastrowid
        trip = conn.execute("""INSERT INTO trips(company_id,from_city,to_city,departure_time,arrival_time,vehicle_type,trip_class,total_seats,available_seats,price_jod,status)
            VALUES (?, 'عمان','العقبة','2030-01-01 10:00:00','2030-01-01 12:00:00','bus','economy',20,18,10,'active')""",(company,)).lastrowid
        conn.execute("INSERT INTO bookings(user_id,trip_id,seats_booked,total_price,status,payment_status) VALUES (1,?,2,20,'confirmed','paid')",(trip,))
        conn.execute("INSERT INTO bookings(user_id,trip_id,seats_booked,total_price,status,payment_status) VALUES (1,?,1,10,'pending','unpaid')",(trip,))
        conn.commit()
    finally: conn.close()
    _identity(client)
    body = client.get("/api/admin/control-center/overview?timezone=UTC").get_json()["data"]
    assert body["kpis"]["confirmed_bookings"] == before[0] + 1
    assert body["kpis"]["pending_bookings"] == before[1] + 1
    assert body["kpis"]["qualified_revenue_jod"] == before[2] + 20.0
    assert "companies" not in body
    assert "activity" not in body
    assert {item["label"] for item in body["charts"]["vehicle_distribution"]} == {"bus"}


def test_control_center_sections_are_paged_safe_and_super_admin_only(client):
    _identity(client, "customer", 2)
    assert client.get("/api/admin/control-center/overview").status_code == 403
    assert client.get("/api/admin/control-center/users").status_code == 403
    _identity(client, "company_admin", 3, 1)
    assert client.get("/api/admin/control-center/users").status_code == 403
    _identity(client)
    users = client.get("/api/admin/control-center/users?page=1&page_size=2").get_json()["data"]
    assert users["pagination"]["page_size"] == 2
    assert users["items"] and "password_hash" not in users["items"][0]
    assert users["summary"]["total_users"] >= len(users["items"])
    assert client.get("/api/admin/control-center/users?filter_role=user").status_code == 200
    assert client.get("/api/admin/control-center/users?filter_company_id=1").status_code == 200
    assert client.get("/api/admin/control-center/users?filter_company_id=not-an-id").status_code == 400
    companies = client.get("/api/admin/control-center/companies?page=1&page_size=2").get_json()["data"]
    assert companies["pagination"]["page_size"] == 2
    assert client.get("/api/admin/control-center/operations").status_code == 200
    assert client.get("/api/admin/control-center/activity").status_code == 200


def test_control_center_empty_state_payloads_are_zero_or_empty_and_never_demo_records(client):
    _clear_business_data()
    _identity(client)
    overview = client.get("/api/admin/control-center/overview?timezone=UTC").get_json()["data"]
    assert all(value == 0 for value in overview["kpis"].values())
    assert all(rows == [] for rows in overview["charts"].values())
    assert overview["attention"] == []
    assert client.get("/api/admin/control-center/companies?page=1&page_size=20").get_json()["data"]["items"] == []
    assert client.get("/api/admin/control-center/users?page=1&page_size=20").get_json()["data"]["items"] == []
    assert client.get("/api/admin/control-center/operations").get_json()["data"] == {
        "trips": [], "bookings": [], "maintenance": [],
    }
    assert client.get("/api/admin/control-center/activity").get_json()["data"]["items"] == []
    assert client.get("/api/admin/pricing/transport-policies").get_json()["data"] == []
    assert client.get("/api/admin/pricing/maintenance-services").get_json()["data"] == []


def test_company_directory_and_assignment_choices_use_persisted_rows_only(client):
    _clear_business_data()
    from database.db import get_db_connection
    conn = get_db_connection()
    try:
        visible = conn.execute("INSERT INTO companies(name,name_ar,company_type,status) VALUES ('Persisted Transport','نقل محفوظ','transport','active')").lastrowid
        conn.execute("INSERT INTO companies(name,name_ar,company_type,status) VALUES ('Inactive Transport','نقل موقوف','transport','inactive')")
        conn.execute("INSERT INTO companies(name,name_ar,company_type,status) VALUES ('Real Maintenance','صيانة حقيقية','maintenance','active')")
        conn.commit()
    finally:
        conn.close()
    _identity(client)
    companies = client.get("/api/admin/control-center/companies?filter_company_type=transport").get_json()["data"]["items"]
    assert any(row["company_id"] == visible and row["review_count"] == 0 and row["average_rating"] is None for row in companies)
    choices = client.get("/api/admin/transport-companies").get_json()["data"]
    assert [row["company_id"] for row in choices] == [visible]


def test_control_center_ui_has_no_business_data_fallbacks_or_overview_activity():
    root = os.path.join(os.path.dirname(__file__), "..")
    template = open(os.path.join(root, "frontend", "templates", "admin.html"), encoding="utf-8").read()
    source = open(os.path.join(root, "frontend", "static", "js", "admin-control-center.js"), encoding="utf-8").read()
    assert 'id="overviewActivity"' not in template
    assert 'id="overviewCompanies"' not in template
    assert "Math.random" not in source
    assert "placeholderData" not in source
    assert "mock" not in source.lower()
    assert "loadOperations" in source and "loadForming" in source
    assert "catch(e){failure" in source


def test_control_center_kpis_follow_four_two_one_responsive_grid_contract():
    root = os.path.join(os.path.dirname(__file__), "..")
    css = open(os.path.join(root, "frontend", "static", "css", "main.css"), encoding="utf-8").read()
    assert ".control-kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));" in css
    assert ".control-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }" in css
    assert ".control-donuts, .control-kpis { grid-template-columns: 1fr; }" in css


def test_control_center_ui_contract_has_six_tabs_safe_dom_lazy_load_and_accessible_donuts():
    root = os.path.join(os.path.dirname(__file__), "..")
    template = open(os.path.join(root, "frontend", "templates", "admin.html"), encoding="utf-8").read()
    source = open(os.path.join(root, "frontend", "static", "js", "admin-control-center.js"), encoding="utf-8").read()
    for tab in ("overview", "operations", "pricing", "companies", "users", "activity"):
        assert 'data-tab="' + tab + '"' in template
    assert 'role="tablist"' in template and 'role="tabpanel"' in template
    assert "control-donut" in source and 'setAttribute("aria-label"' in source
    assert "textContent" in source and "innerHTML" not in source
    assert "activate(\"overview\")" in source and "cache" in source
    assert 'id="pricingFilter"' in template and 'id="formingFilter"' in template
    assert 'id="companyFilter"' in template and 'id="peopleRole"' in template
    assert "noPricingRules" in source and "noForming" in source and "localizeFilters" in source
    assert 'data-tab-target="operations"' in template
def test_company_admin_creation_control_is_present_in_new_control_center():
    import os
    root = os.path.join(os.path.dirname(__file__), "..")
    template = open(os.path.join(root, "frontend", "templates", "admin.html"), encoding="utf-8").read()
    script = open(os.path.join(root, "frontend", "static", "js", "admin-control-center.js"), encoding="utf-8").read()
    assert 'id="addAdminButton"' in template
    assert 'role="dialog"' in template and 'id="adminCreateCompany"' in template
    assert '"/api/admin/users"' in script
    assert "loadPeople(true)" in script
