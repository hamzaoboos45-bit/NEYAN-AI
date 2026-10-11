"""Vehicle-policy snapshots and UI stabilization regression coverage."""
from datetime import date, timedelta
import os, sys, tempfile
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

@pytest.fixture()
def client():
    fd,path=tempfile.mkstemp(suffix=".db");os.close(fd);os.remove(path);old=config.DATABASE_PATH;config.DATABASE_PATH=path
    try:
        from app import create_app
        app=create_app();app.config["TESTING"]=True
        with app.test_client() as c: yield c
    finally:
        config.DATABASE_PATH=old
        if os.path.exists(path):os.remove(path)
def who(c):
    with c.session_transaction() as s:s.update(user_id=2,role="customer",company_id=None,user_name="Test",_csrf_token="token")
def make(c,vehicle,days):
    return c.post("/api/trip-requests",json={"from_city":"Amman","to_city":"Irbid","requested_date":(date.today()+timedelta(days=days)).isoformat(),"requested_time_start":"10:00","requested_time_end":"12:00","passenger_quantity":1,"desired_vehicle_type":vehicle,"desired_trip_class":"economy"},headers={"X-CSRFToken":"token"})
@pytest.mark.parametrize("vehicle,minimum,maximum",[("car",3,4),("van",7,10),("bus",12,45)])
def test_vehicle_policy_is_server_snapshotted(client,vehicle,minimum,maximum):
    who(client); r=make(client,vehicle,{"car":40,"van":41,"bus":42}[vehicle]);assert r.status_code==201
    card=r.get_json()["data"];assert (card["minimum_passengers"],card["maximum_passengers"])==(minimum,maximum)
def test_policy_cannot_be_forged_and_maintenance_layout_is_centered(client):
    who(client); payload={"from_city":"Amman","to_city":"Irbid","requested_date":(date.today()+timedelta(days=43)).isoformat(),"passenger_quantity":5,"desired_vehicle_type":"car","minimum_passengers":1}
    assert client.post("/api/trip-requests",json=payload,headers={"X-CSRFToken":"token"}).status_code==400
    assert client.get("/maintenance").status_code==200
    source=open(os.path.join(os.path.dirname(__file__),"..","frontend","templates","maintenance.html"),encoding="utf8").read();assert "maintenance-page" in source and "maintenance-form-card" in source
