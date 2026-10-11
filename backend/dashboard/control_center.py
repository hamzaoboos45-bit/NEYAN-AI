"""Read-only, platform-scoped data contracts for the Admin Control Center."""

from __future__ import annotations

from backend.dashboard.contracts import DashboardDateRange, Pagination
from database.db import get_db_connection


def _time(column: str, window: DashboardDateRange, params: list) -> str:
    clause = ""
    if window.start:
        clause += f" AND date({column}) >= ?"; params.append(window.start)
    if window.end_exclusive:
        clause += f" AND date({column}) < ?"; params.append(window.end_exclusive)
    return clause


def _page(conn, sql: str, count_sql: str, params: list, pagination: Pagination):
    total = int(conn.execute(count_sql, params).fetchone()[0])
    rows = conn.execute(sql + " LIMIT ? OFFSET ?", [*params, pagination.page_size, (pagination.page - 1) * pagination.page_size]).fetchall()
    return {"items": [dict(row) for row in rows], "pagination": pagination.as_response(total)}


class AdminControlCenterRepository:
    """Aggregates existing persisted facts; never owns an operational mutation."""

    def overview(self, window: DashboardDateRange):
        conn = get_db_connection()
        try:
            booking_params: list = []; booking_where = "1=1" + _time("b.booked_at", window, booking_params)
            maintenance_params: list = []; maintenance_where = "1=1" + _time("m.created_at", window, maintenance_params)
            forming_params: list = []; forming_where = "1=1" + _time("r.created_at", window, forming_params)
            booking = conn.execute(f"""SELECT COUNT(*) total, SUM(b.status='confirmed') confirmed, SUM(b.status='pending') pending,
                SUM(b.status='cancelled') cancelled, COALESCE(SUM(CASE WHEN b.status='confirmed' AND b.payment_status='paid' THEN b.total_price ELSE 0 END),0) revenue
                FROM bookings b WHERE {booking_where}""", booking_params).fetchone()
            forming = conn.execute(f"SELECT status label, COUNT(*) count FROM trip_requests r WHERE {forming_where} GROUP BY status ORDER BY status", forming_params).fetchall()
            maintenance = conn.execute(f"SELECT status label, COUNT(*) count FROM maintenance_requests m WHERE {maintenance_where} GROUP BY status ORDER BY status", maintenance_params).fetchall()
            vehicle = conn.execute("SELECT vehicle_type label, COUNT(*) count FROM trips WHERE status='active' AND datetime(departure_time)>=datetime('now') GROUP BY vehicle_type ORDER BY vehicle_type").fetchall()
            attention = conn.execute("""SELECT r.request_id,r.from_city,r.to_city,r.status,r.company_decision,r.current_passengers,r.minimum_passengers
                FROM (SELECT tr.*,COALESCE(SUM(CASE WHEN m.member_status='active' THEN m.passenger_quantity ELSE 0 END),0) current_passengers
                      FROM trip_requests tr LEFT JOIN trip_request_members m ON m.request_id=tr.request_id GROUP BY tr.request_id) r
                WHERE (r.status='minimum_reached' AND r.assigned_company_id IS NULL) OR (r.assigned_company_id IS NOT NULL AND r.company_decision='pending')
                ORDER BY r.updated_at DESC,r.request_id DESC LIMIT 12""").fetchall()
            return {"kpis": {"total_users": int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]), "active_companies": int(conn.execute("SELECT COUNT(*) FROM companies WHERE status='active'").fetchone()[0]), "active_trips": int(conn.execute("SELECT COUNT(*) FROM trips WHERE status='active' AND datetime(departure_time)>=datetime('now')").fetchone()[0]), "total_bookings": int(booking["total"] or 0), "confirmed_bookings": int(booking["confirmed"] or 0), "pending_bookings": int(booking["pending"] or 0), "active_maintenance": int(conn.execute("SELECT COUNT(*) FROM maintenance_requests WHERE status IN ('pending','assigned','in_progress')").fetchone()[0]), "open_forming": int(conn.execute("SELECT COUNT(*) FROM trip_requests WHERE status='collecting'").fetchone()[0]), "minimum_reached": int(conn.execute("SELECT COUNT(*) FROM trip_requests WHERE status='minimum_reached'").fetchone()[0]), "converted_forming": int(conn.execute("SELECT COUNT(*) FROM trip_requests WHERE status='converted'").fetchone()[0]), "qualified_revenue_jod": float(booking["revenue"] or 0)}, "charts": {"booking_status":[dict(x) for x in conn.execute(f"SELECT status label,COUNT(*) count FROM bookings b WHERE {booking_where} GROUP BY status ORDER BY status",booking_params)], "forming_lifecycle":[dict(x) for x in forming], "maintenance_status":[dict(x) for x in maintenance], "vehicle_distribution":[dict(x) for x in vehicle]}, "attention":[dict(x) for x in attention], "date_range":window.as_response()}
        finally: conn.close()

    def section(
        self,
        name: str,
        pagination: Pagination,
        search: str = "",
        status: str = "",
        role: str = "",
        company_id: int | None = None,
        company_type: str = "",
    ):
        conn=get_db_connection(); like=f"%{search.strip()}%"
        try:
            if name == "users":
                params=[]; where="1=1"; 
                if search: where+=" AND (u.full_name LIKE ? OR u.email LIKE ?)"; params += [like,like]
                if status: where+=" AND u.status=?"; params.append(status)
                if role in {"user", "customer"}:
                    where += " AND u.role IN ('user','customer')"
                elif role == "company_admin":
                    where += " AND u.role IN ('admin','company_admin') AND u.company_id IS NOT NULL"
                elif role in {"admin", "super_admin", "platform_admin"}:
                    where += " AND u.role='admin' AND u.company_id IS NULL"
                elif role:
                    raise ValueError("Unknown user role filter.")
                if company_id is not None: where+=" AND u.company_id=?"; params.append(company_id)
                result = _page(conn,f"SELECT u.user_id,u.full_name,u.email,u.role,u.status,u.company_id,u.last_login,u.created_at,c.name company_name,c.name_ar company_name_ar FROM users u LEFT JOIN companies c ON c.company_id=u.company_id WHERE {where} ORDER BY u.user_id DESC",f"SELECT COUNT(*) FROM users u WHERE {where}",params,pagination)
                summary = conn.execute("SELECT COUNT(*) total_users, SUM(role IN ('user','customer')) customers, SUM(role IN ('admin','company_admin') AND company_id IS NOT NULL) company_admins, SUM(role='admin' AND company_id IS NULL) platform_admins, SUM(status='active') active_users FROM users").fetchone()
                result["summary"] = {key: int(summary[key] or 0) for key in summary.keys()}
                return result
            if name == "companies":
                params=[]; where="1=1"; 
                if search: where+=" AND (c.name LIKE ? OR c.name_ar LIKE ?)"; params += [like,like]
                if status: where+=" AND c.status=?"; params.append(status)
                if company_type: where+=" AND c.company_type=?"; params.append(company_type)
                sql=f"""SELECT c.company_id,c.name,c.name_ar,c.company_type,c.city,c.status,COUNT(DISTINCT t.trip_id) trip_count,COUNT(DISTINCT b.booking_id) booking_count,
                 COUNT(DISTINCT CASE WHEN t.status='active' AND datetime(t.departure_time)>=datetime('now') THEN t.trip_id END) active_trip_count,
                 ROUND(AVG(rv.rating),1) average_rating,COUNT(DISTINCT rv.review_id) review_count FROM companies c LEFT JOIN trips t ON t.company_id=c.company_id LEFT JOIN bookings b ON b.trip_id=t.trip_id LEFT JOIN reviews rv ON rv.company_id=c.company_id WHERE {where} GROUP BY c.company_id ORDER BY c.company_id DESC"""
                return _page(conn,sql,f"SELECT COUNT(*) FROM companies c WHERE {where}",params,pagination)
            if name == "operations":
                return {"trips":[dict(x) for x in conn.execute("SELECT t.trip_id,t.from_city,t.to_city,t.departure_time,t.vehicle_type,t.trip_class,t.available_seats,t.total_seats,t.price_jod,t.status,c.name company_name,c.name_ar company_name_ar FROM trips t JOIN companies c ON c.company_id=t.company_id WHERE t.status='active' AND datetime(t.departure_time)>=datetime('now') ORDER BY datetime(t.departure_time) LIMIT 50")],"bookings":[dict(x) for x in conn.execute("SELECT b.booking_id,b.status,b.payment_status,b.seats_booked,b.total_price,b.booked_at,t.from_city,t.to_city FROM bookings b JOIN trips t ON t.trip_id=b.trip_id WHERE b.status IN ('pending','confirmed') ORDER BY datetime(b.booked_at) DESC LIMIT 50")],"maintenance":[dict(x) for x in conn.execute("SELECT m.request_id,m.service_type,m.status,m.preferred_date,m.pricing_type_snapshot,m.total_minimum_fils_snapshot,m.total_maximum_fils_snapshot,c.name company_name,c.name_ar company_name_ar FROM maintenance_requests m LEFT JOIN companies c ON c.company_id=m.company_id WHERE m.status IN ('pending','assigned','in_progress') ORDER BY datetime(m.created_at) DESC LIMIT 50")]}
            if name == "activity": return {"items":[dict(x) for x in conn.execute("SELECT action_type,logged_at FROM activity_logs ORDER BY datetime(logged_at) DESC,log_id DESC LIMIT 100")],"unread_notifications":int(conn.execute("SELECT COUNT(*) FROM notifications WHERE recipient_user_id IN (SELECT user_id FROM users WHERE role='admin' AND company_id IS NULL) AND read_at IS NULL").fetchone()[0])}
            raise ValueError("Unknown control-center section.")
        finally: conn.close()
