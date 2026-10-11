
from flask import Blueprint, jsonify, render_template, session
from database.db import get_db_connection
from routes.auth_helpers import company_admin_required, current_company_id, super_admin_required

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin")
@company_admin_required
def admin_dashboard():
    return render_template("admin.html")


@admin_bp.route("/api/analytics/summary")
@company_admin_required
def analytics_summary():
    """
    RBAC: company_admin gets stats scoped to their own company only.
    super_admin gets the whole platform.
    """
    scope_company_id = current_company_id() if session.get("role") == "company_admin" else None

    conn = get_db_connection()
    try:
        if scope_company_id:
            total_bookings = conn.execute(
                """SELECT COUNT(*) FROM bookings b JOIN trips t ON b.trip_id = t.trip_id
                   WHERE t.company_id = ?""",
                (scope_company_id,),
            ).fetchone()[0]
            total_maintenance = conn.execute(
                "SELECT COUNT(*) FROM maintenance_requests WHERE company_id = ?",
                (scope_company_id,),
            ).fetchone()[0]
            popular_route = conn.execute(
                """
                SELECT t.from_city || ' - ' || t.to_city AS route, COUNT(*) AS count
                FROM bookings b JOIN trips t ON b.trip_id = t.trip_id
                WHERE t.company_id = ?
                GROUP BY route ORDER BY count DESC LIMIT 1
                """,
                (scope_company_id,),
            ).fetchone()
            top_service = conn.execute(
                """SELECT service_type, COUNT(*) AS count FROM maintenance_requests
                   WHERE company_id = ? GROUP BY service_type ORDER BY count DESC LIMIT 1""",
                (scope_company_id,),
            ).fetchone()
            active_companies = 1
            pending_bookings = conn.execute(
                """SELECT COUNT(*) FROM bookings b JOIN trips t ON b.trip_id = t.trip_id
                   WHERE t.company_id = ? AND b.status = 'pending'""",
                (scope_company_id,),
            ).fetchone()[0]
        else:
            total_bookings    = conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
            total_maintenance = conn.execute("SELECT COUNT(*) FROM maintenance_requests").fetchone()[0]

            popular_route = conn.execute("""
                SELECT t.from_city || ' - ' || t.to_city AS route, COUNT(*) AS count
                FROM bookings b JOIN trips t ON b.trip_id = t.trip_id
                GROUP BY route ORDER BY count DESC LIMIT 1
            """).fetchone()

            top_service = conn.execute("""
                SELECT service_type, COUNT(*) AS count
                FROM maintenance_requests
                GROUP BY service_type ORDER BY count DESC LIMIT 1
            """).fetchone()

            active_companies = conn.execute(
                "SELECT COUNT(*) FROM companies WHERE status='active'"
            ).fetchone()[0]

            pending_bookings = conn.execute(
                "SELECT COUNT(*) FROM bookings WHERE status='pending'"
            ).fetchone()[0]

        return jsonify({
            "total_bookings":     total_bookings,
            "total_maintenance":  total_maintenance,
            "most_popular_route": dict(popular_route) if popular_route else {},
            "top_service":        dict(top_service) if top_service else {},
            "active_companies":   active_companies,
            "pending_bookings":   pending_bookings,
            "scope":              "company" if scope_company_id else "platform",
        })
    finally:
        conn.close()


@admin_bp.route("/api/analytics/bookings-per-company")
@super_admin_required
def bookings_per_company():
    """Cross-company comparison — inherently platform-wide, super_admin only."""
    conn = get_db_connection()
    try:
        rows = conn.execute("""
            SELECT c.name_ar AS company, COUNT(b.booking_id) AS bookings
            FROM bookings b
            JOIN trips t ON b.trip_id = t.trip_id
            JOIN companies c ON t.company_id = c.company_id
            GROUP BY c.company_id ORDER BY bookings DESC
        """).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@admin_bp.route("/api/analytics/maintenance-per-company")
@super_admin_required
def maintenance_per_company():
    """Cross-company comparison — inherently platform-wide, super_admin only."""
    conn = get_db_connection()
    try:
        rows = conn.execute("""
            SELECT c.name_ar AS company, COUNT(r.request_id) AS requests
            FROM maintenance_requests r
            JOIN companies c ON r.company_id = c.company_id
            GROUP BY c.company_id ORDER BY requests DESC
        """).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@admin_bp.route("/api/analytics/companies")
@super_admin_required
def companies_list():
    """Returns real-review aggregates for the platform company directory."""
    conn = get_db_connection()
    try:
        rows = conn.execute("""
            SELECT c.company_id, c.name_ar, c.company_type, c.city, c.status,
                   ra.average_rating, COALESCE(ra.review_count, 0) AS review_count
            FROM companies c
            LEFT JOIN (
                SELECT company_id, ROUND(AVG(rating), 1) AS average_rating, COUNT(*) AS review_count
                FROM reviews GROUP BY company_id
            ) ra ON ra.company_id = c.company_id
            ORDER BY c.company_type, c.name_ar
        """).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@admin_bp.route("/api/analytics/activity")
@super_admin_required
def activity_log():
    """Returns 50 most recent activity log entries — platform-wide, super_admin only."""
    conn = get_db_connection()
    try:
        rows = conn.execute("""
            SELECT action_type, logged_at, details_json AS details
            FROM activity_logs
            ORDER BY logged_at DESC
            LIMIT 50
        """).fetchall()
        return jsonify([dict(r) for r in rows])
    except Exception:
        return jsonify([])   # return empty list if table doesn't exist yet
    finally:
        conn.close()


@admin_bp.route("/api/analytics/my-trips")
@company_admin_required
def my_trips():
    """
    RBAC — 'Companies: manage only their own trips'.
    company_admin: trips run by their own company.
    super_admin: every trip on the platform.
    """
    scope_company_id = current_company_id() if session.get("role") == "company_admin" else None

    conn = get_db_connection()
    try:
        query = """
            SELECT t.trip_id, t.from_city, t.to_city, t.departure_time,
                   t.arrival_time, t.vehicle_type, t.trip_class,
                   t.available_seats, t.price_jod, t.status,
                   c.name_ar AS company_name
            FROM trips t
            JOIN companies c ON t.company_id = c.company_id
        """
        params = []
        if scope_company_id:
            query += " WHERE t.company_id = ?"
            params.append(scope_company_id)
        query += " ORDER BY t.departure_time DESC"

        rows = conn.execute(query, params).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()
