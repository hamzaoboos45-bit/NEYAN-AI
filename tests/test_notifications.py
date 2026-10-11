"""Persistent, scoped notification lifecycle and shell contract tests."""
from datetime import date, timedelta
import os, sys, tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config
from database.db import get_db_connection


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd); os.remove(path)
    old = config.DATABASE_PATH; config.DATABASE_PATH = path
    try:
        from app import create_app
        app = create_app(); app.config["TESTING"] = True
        with app.test_client() as c: yield c
    finally:
        config.DATABASE_PATH = old
        if os.path.exists(path): os.remove(path)


def identity(client, user_id, role, company_id=None):
    with client.session_transaction() as s:
        s.update(user_id=user_id, role=role, company_id=company_id, user_name="Notification Test", _csrf_token="notification-token")


def headers(): return {"X-CSRFToken": "notification-token"}
def future(days=40): return (date.today() + timedelta(days=days)).isoformat()


def create_request(client, user_id=2, passengers=12, vehicle="bus", shared=False):
    identity(client, user_id, "customer")
    r = client.post("/api/trip-requests", json={"from_city":"Amman","to_city":"Aqaba","requested_date":future(),"requested_time_start":"10:00","requested_time_end":"12:00","passenger_quantity":passengers,"desired_vehicle_type":vehicle,"desired_trip_class":"economy","sharing_mode":"shared" if shared else "private"}, headers=headers())
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()["data"]["request_id"]


def test_schema_indexes_and_notification_dedupe(client):
    conn = get_db_connection()
    try:
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='notifications'").fetchone()[0]
        assert "recipient_user_id" in sql and "dedupe_key" in sql and "read_at" in sql
        indexes = {row["name"] for row in conn.execute("PRAGMA index_list(notifications)")}
        assert "idx_notifications_recipient_created" in indexes and "idx_notifications_recipient_unread" in indexes
    finally: conn.close()


def test_minimum_reached_notifies_only_participants_and_is_idempotent(client):
    rid = create_request(client, passengers=2, vehicle="car", shared=True)
    identity(client, 3, "customer")
    assert client.post(f"/api/trip-requests/{rid}/join", json={"passenger_quantity":1}, headers=headers()).status_code == 200
    conn = get_db_connection()
    try:
        rows = conn.execute("SELECT recipient_user_id,event_type,metadata_json FROM notifications WHERE source_type='trip_request' AND source_id=?", (rid,)).fetchall()
        assert {(row["recipient_user_id"], row["event_type"]) for row in rows} >= {(2,"forming_minimum_reached"),(3,"forming_minimum_reached")}
        assert all("confirmed" not in row["metadata_json"] for row in rows)
    finally: conn.close()
    # Repeated recomputation through an already-active membership is rejected;
    # the unique lifecycle key remains the authoritative duplicate guard.
    assert client.post(f"/api/trip-requests/{rid}/join", json={"passenger_quantity":1}, headers=headers()).status_code == 409
    conn = get_db_connection()
    try: assert conn.execute("SELECT COUNT(*) FROM notifications WHERE source_id=? AND event_type='forming_minimum_reached'", (rid,)).fetchone()[0] == 2
    finally: conn.close()


def test_assignment_acceptance_conversion_and_no_booking_notification_side_effect(client):
    rid = create_request(client)
    identity(client, 1, "super_admin")
    assert client.post(f"/api/admin/trip-requests/{rid}/assign", json={"company_id":1}, headers=headers()).status_code == 200
    identity(client, 4, "company_admin", 1)
    assert client.post(f"/api/company/trip-requests/{rid}/accept", json={}, headers=headers()).status_code == 200
    payload={"departure_time":future()+"T10:30:00","arrival_time":future()+"T14:00:00","vehicle_type":"bus","trip_class":"economy","price_jod":12.5,"total_seats":12}
    converted=client.post(f"/api/company/trip-requests/{rid}/convert",json=payload,headers=headers())
    assert converted.status_code == 200
    trip_id=converted.get_json()["data"]["trip_id"]
    conn=get_db_connection()
    try:
        events={r["event_type"] for r in conn.execute("SELECT event_type FROM notifications WHERE recipient_user_id=2 AND source_id=?",(rid,))}
        assert {"forming_company_assigned","forming_company_accepted","forming_converted"} <= events
        assert conn.execute("SELECT COUNT(*) FROM bookings WHERE trip_id=?",(trip_id,)).fetchone()[0] == 0
    finally: conn.close()


def test_notification_api_ownership_read_and_mark_all(client):
    rid=create_request(client)
    identity(client,2,"customer")
    listed=client.get("/api/notifications?limit=999"); assert listed.status_code==200
    items=listed.get_json()["data"]; assert items and listed.get_json()["limit"] == 50
    notification_id=items[0]["notification_id"]
    assert client.get("/api/notifications/unread-count").get_json()["unread_count"] >= 1
    identity(client,3,"customer")
    assert client.post(f"/api/notifications/{notification_id}/read",headers=headers()).status_code == 404
    identity(client,2,"customer")
    assert client.post(f"/api/notifications/{notification_id}/read",headers=headers()).status_code == 200
    assert client.post(f"/api/notifications/{notification_id}/read",headers=headers()).status_code == 200
    assert client.post("/api/notifications/mark-all-read",headers=headers()).status_code == 200
    assert client.get("/api/notifications/unread-count").get_json()["unread_count"] == 0


def test_booking_cancellation_and_maintenance_status_notify_only_owner(client):
    conn=get_db_connection()
    try:
        trip=conn.execute("INSERT INTO trips(company_id,from_city,to_city,departure_time,arrival_time,vehicle_type,trip_class,total_seats,available_seats,price_jod) VALUES(1,'عمان','العقبة','2030-01-01 10:00:00','2030-01-01 14:00:00','bus','economy',10,7,10)").lastrowid
        booking=conn.execute("INSERT INTO bookings(user_id,trip_id,seats_booked,total_price) VALUES(2,?,?,20)",(trip,3)).lastrowid
        maint=conn.execute("INSERT INTO maintenance_requests(user_id,company_id,service_type,location,preferred_date) VALUES(2,1,'engine','x','2030-01-01')").lastrowid
        conn.commit()
    finally: conn.close()
    identity(client,4,"company_admin",1)
    assert client.patch(f"/api/bookings/{booking}/status",json={"status":"cancelled"},headers=headers()).status_code==200
    assert client.patch(f"/api/maintenance/requests/{maint}/status",json={"status":"in_progress"},headers=headers()).status_code==200
    conn=get_db_connection()
    try:
        assert conn.execute("SELECT available_seats FROM trips WHERE trip_id=?",(trip,)).fetchone()[0] == 10
        assert conn.execute("SELECT COUNT(*) FROM notifications WHERE recipient_user_id=2 AND event_type IN ('booking_cancelled','maintenance_status_changed')").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM notifications WHERE recipient_user_id=3 AND source_id IN (?,?)",(booking,maint)).fetchone()[0] == 0
    finally: conn.close()


def test_shell_contract_uses_safe_dom_and_shared_tokens():
    root=os.path.join(os.path.dirname(__file__),"..")
    base=open(os.path.join(root,"frontend","templates","base.html"),encoding="utf-8").read()
    js=open(os.path.join(root,"frontend","static","js","notifications.js"),encoding="utf-8").read()
    css=open(os.path.join(root,"frontend","static","css","main.css"),encoding="utf-8").read()
    assert 'id="notificationBell"' in base and 'id="notificationBadge"' in base and "notifications.js" in base
    assert "textContent" in js and "innerHTML" not in js
    assert "var(--card-bg)" in css and "@media (max-width: 640px)" in css
