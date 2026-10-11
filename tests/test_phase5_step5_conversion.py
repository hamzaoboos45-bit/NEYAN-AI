"""Phase 5 Step 5 conversion and seat-integrity coverage."""
from datetime import date, timedelta
import os, sys, tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config
from database.db import get_db_connection

@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd); os.remove(path)
    original = config.DATABASE_PATH; config.DATABASE_PATH = path
    try:
        from app import create_app
        app = create_app(); app.config["TESTING"] = True
        with app.test_client() as value: yield value
    finally:
        config.DATABASE_PATH = original
        if os.path.exists(path): os.remove(path)

def identity(client, user, role, company=None):
    with client.session_transaction() as s: s.update(user_id=user, role=role, company_id=company, user_name="Test", _csrf_token="token")
def headers(): return {"X-CSRFToken":"token"}
def accepted(client, days=40):
    identity(client, 2, "customer")
    r=client.post("/api/trip-requests",json={"from_city":"Amman","to_city":"Aqaba","requested_date":(date.today()+timedelta(days=days)).isoformat(),"requested_time_start":"10:00","requested_time_end":"12:00","passenger_quantity":12,"desired_vehicle_type":"bus","desired_trip_class":"economy"},headers=headers()); rid=r.get_json()["data"]["request_id"]
    identity(client,1,"super_admin"); assert client.post(f"/api/admin/trip-requests/{rid}/assign",json={"company_id":1},headers=headers()).status_code==200
    identity(client,4,"company_admin",1); assert client.post(f"/api/company/trip-requests/{rid}/accept",json={},headers=headers()).status_code==200
    return rid
def payload(days=40, seats=12):
    d=(date.today()+timedelta(days=days)).isoformat()
    return {"departure_time":d+"T10:30:00","arrival_time":d+"T14:00:00","vehicle_type":"bus","trip_class":"economy","price_jod":12.5,"total_seats":seats}

def test_accepted_company_converts_once_with_server_route_and_no_booking(client):
    rid=accepted(client); identity(client,4,"company_admin",1)
    result=client.post(f"/api/company/trip-requests/{rid}/convert",json=payload(),headers=headers())
    assert result.status_code==200; trip=result.get_json()["data"]["trip_id"]
    assert client.post(f"/api/company/trip-requests/{rid}/convert",json=payload(),headers=headers()).status_code==409
    conn=get_db_connection()
    try:
        row=conn.execute("SELECT status, converted_trip_id FROM trip_requests WHERE request_id=?",(rid,)).fetchone(); actual=conn.execute("SELECT from_city,to_city,company_id,available_seats FROM trips WHERE trip_id=?",(trip,)).fetchone()
        assert (row["status"],row["converted_trip_id"]) == ("converted",trip)
        assert (actual["from_city"],actual["to_city"],actual["company_id"],actual["available_seats"]) == ("عمان","العقبة",1,12)
        assert conn.execute("SELECT COUNT(*) FROM bookings WHERE trip_id=?",(trip,)).fetchone()[0]==0
    finally: conn.close()

def test_conversion_rbac_schedule_capacity_and_forgery_protected(client):
    rid=accepted(client,41)
    identity(client,3,"company_admin",2); assert client.post(f"/api/company/trip-requests/{rid}/convert",json=payload(41),headers=headers()).status_code==403
    identity(client,1,"super_admin"); assert client.post(f"/api/company/trip-requests/{rid}/convert",json=payload(41),headers=headers()).status_code==403
    identity(client,4,"company_admin",1)
    assert client.post(f"/api/company/trip-requests/{rid}/convert",json=payload(42),headers=headers()).status_code==409
    assert client.post(f"/api/company/trip-requests/{rid}/convert",json=payload(41,9),headers=headers()).status_code==409
    bad=payload(41); bad["from_city"]="Irbid"; assert client.post(f"/api/company/trip-requests/{rid}/convert",json=bad,headers=headers()).status_code==400

def test_cancellation_restores_seats_exactly_once(client):
    conn=get_db_connection()
    try:
        trip=conn.execute("INSERT INTO trips(company_id,from_city,to_city,departure_time,arrival_time,vehicle_type,trip_class,total_seats,available_seats,price_jod) VALUES(1,'Amman','Aqaba','2030-01-01 10:00:00','2030-01-01 14:00:00','bus','economy',10,7,10)").lastrowid
        booking=conn.execute("INSERT INTO bookings(user_id,trip_id,seats_booked,total_price) VALUES(2,?,?,20)",(trip,3)).lastrowid; conn.commit()
    finally: conn.close()
    identity(client,4,"company_admin",1)
    assert client.patch(f"/api/bookings/{booking}/status",json={"status":"cancelled"},headers=headers()).status_code==200
    assert client.patch(f"/api/bookings/{booking}/status",json={"status":"cancelled"},headers=headers()).status_code==200
    conn=get_db_connection()
    try: assert conn.execute("SELECT available_seats FROM trips WHERE trip_id=?",(trip,)).fetchone()[0]==10
    finally: conn.close()
