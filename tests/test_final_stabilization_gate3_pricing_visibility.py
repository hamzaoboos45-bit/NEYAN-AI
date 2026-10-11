"""Gate 3 pricing visibility: real server values, snapshots, and chat copy."""
import os, sys, tempfile
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd); os.remove(path)
    old = config.DATABASE_PATH; config.DATABASE_PATH = path
    try:
        from app import create_app
        app = create_app(); app.config["TESTING"] = True
        with app.test_client() as value: yield value
    finally:
        config.DATABASE_PATH = old
        if os.path.exists(path): os.remove(path)


def identity(client, user=1, role="customer"):
    from backend.security.csrf import SESSION_KEY
    with client.session_transaction() as s:
        s.update(user_id=user, role=role, session_id="gate3", **{SESSION_KEY:"gate3-csrf"})
    return {"X-CSRFToken":"gate3-csrf"}


def future_trip(price=7.5):
    from database.db import get_db_connection
    c=get_db_connection()
    try:
        tid=c.execute("INSERT INTO trips(company_id,from_city,to_city,departure_time,arrival_time,vehicle_type,trip_class,total_seats,available_seats,price_jod,status) VALUES(1,'عمان','إربد','2099-07-01 10:00','2099-07-01 12:00','bus','economy',10,10,?,'active')",(price,)).lastrowid;c.commit();return tid
    finally:c.close()


def test_search_preview_booking_snapshot_and_history_are_server_authoritative(client):
    tid=future_trip(); headers=identity(client)
    trip=[x for x in client.get('/api/trips?from=عمان&to=إربد&date=2099-07-01&class=economy').get_json() if x['trip_id']==tid][0]
    assert trip['price_jod']==7.5
    from backend.transportation.booking_service import BookingService
    quote=BookingService.preview(trip_id=tid,seats=2)
    assert quote=={'price_semantics':'current_booking_total','seats':2,'unit_price_jod':'7.500','total_price_jod':'15.000'}
    made=BookingService.create(user_id=1,trip_id=tid,seats=2)
    assert made['committed_total_price_jod']=='15.000'
    from database.db import get_db_connection
    c=get_db_connection();c.execute('UPDATE trips SET price_jod=99 WHERE trip_id=?',(tid,));c.commit();c.close()
    history=client.get('/api/bookings',headers=headers).get_json()
    row=[x for x in history if x['trip_id']==tid][0] if 'trip_id' in history[0] else history[-1]
    assert row['committed_total_price_jod']=='15.000'


def test_shared_estimate_is_server_derived_and_private_has_no_shared_price(client):
    from backend.transportation.trip_request_service import TripRequestService
    from database.db import get_db_connection
    c=get_db_connection();c.execute("INSERT INTO transport_pricing_policies(from_city,to_city,vehicle_type,trip_class,base_trip_price_fils,is_active) VALUES('عمان','العقبة','bus','economy',12000,1)");c.commit();c.close()
    payload={'from_city':'عمان','to_city':'العقبة','requested_date':'2099-07-01','requested_time_start':'','requested_time_end':'','desired_vehicle_type':'bus','desired_trip_class':'economy','passenger_quantity':3,'sharing_mode':'shared'}
    shared=TripRequestService.create(2,payload); private=TripRequestService.create(3,{**payload,'requested_time_start':'13:00','requested_time_end':'13:00','sharing_mode':'private'})
    assert shared['pricing_available'] and shared['base_trip_price_jod']=='12.000' and shared['per_passenger_estimate_jod']=='4.000'
    assert not private['pricing_available'] and private['per_passenger_estimate_jod'] is None


def test_chat_confirmation_shows_current_total_and_ignores_price_text(client):
    tid=future_trip(8.0); headers=identity(client)
    def chat(text): return client.post('/api/chat',json={'message':text,'csrf_token':'gate3-csrf'},headers=headers).get_json()['reply']
    assert 'الرحلات المتاحة' in chat('اريد حجز رحلة من عمان الى اربد بتاريخ 2099-07-01 لشخصين اقتصادي')
    summary=chat('1'); assert 'الإجمالي الحالي' in summary and '16.000' in summary
    done=chat('السعر 1 دينار نعم'); assert 'هل تريد تأكيد الحجز' in done
    from database.db import get_db_connection
    c=get_db_connection(); assert c.execute('SELECT COUNT(*) FROM bookings WHERE trip_id=?',(tid,)).fetchone()[0] == 0; c.close()
    assert 'المبلغ النهائي المحفوظ: 16.000' in chat('نعم')
