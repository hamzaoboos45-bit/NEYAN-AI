"""SQL-backed aggregate queries for the minimal Phase 8 KPI foundation."""

from backend.dashboard.contracts import DashboardDateRange
from backend.dashboard.scope import DashboardScope
from database.db import get_db_connection


HOME_RECENT_BOOKING_LIMIT = 5
HOME_COMPANY_LIMIT = 6
HOME_TRIP_LIMIT = 6
ADMIN_PREVIEW_LIMIT = 5
ADMIN_CHART_LIMIT = 12


def _time_filter(column: str, date_range: DashboardDateRange, params: list):
    clauses = []
    if date_range.start:
        clauses.append(f"{column} >= ?")
        params.append(date_range.start)
    if date_range.end_exclusive:
        clauses.append(f"{column} < ?")
        params.append(date_range.end_exclusive)
    return (" AND " + " AND ".join(clauses)) if clauses else ""


def _count(conn, query: str, params: list) -> int:
    return int(conn.execute(query, params).fetchone()[0])


class DashboardRepository:
    """Keeps dashboard aggregate SQL out of Flask route handlers."""

    def initial_metrics(self, scope: DashboardScope, date_range: DashboardDateRange) -> dict:
        conn = get_db_connection()
        try:
            if scope.kind == "platform":
                return self._platform_metrics(conn, date_range)
            if scope.kind == "company":
                return self._company_metrics(conn, scope.company_id, date_range)
            if scope.kind == "user":
                return self._user_metrics(conn, scope.user_id, date_range)
            raise ValueError("Unsupported dashboard scope.")
        finally:
            conn.close()

    def _platform_metrics(self, conn, date_range):
        def count(table, column):
            params = []
            return _count(conn, f"SELECT COUNT(*) FROM {table} WHERE 1 = 1" + _time_filter(column, date_range, params), params)

        return {
            "total_companies": count("companies", "created_at"),
            "total_users": count("users", "created_at"),
            "total_trips": count("trips", "created_at"),
            "total_bookings": count("bookings", "booked_at"),
            "total_maintenance_requests": count("maintenance_requests", "created_at"),
        }

    def _company_metrics(self, conn, company_id, date_range):
        trip_params = [company_id]
        booking_params = [company_id]
        maintenance_params = [company_id]
        return {
            "total_trips": _count(
                conn,
                "SELECT COUNT(*) FROM trips t WHERE t.company_id = ?" + _time_filter("t.created_at", date_range, trip_params),
                trip_params,
            ),
            "total_bookings": _count(
                conn,
                """SELECT COUNT(*) FROM bookings b JOIN trips t ON b.trip_id = t.trip_id
                   WHERE t.company_id = ?""" + _time_filter("b.booked_at", date_range, booking_params),
                booking_params,
            ),
            "total_maintenance_requests": _count(
                conn,
                "SELECT COUNT(*) FROM maintenance_requests r WHERE r.company_id = ?" + _time_filter("r.created_at", date_range, maintenance_params),
                maintenance_params,
            ),
        }

    def _user_metrics(self, conn, user_id, date_range):
        booking_params = [user_id]
        maintenance_params = [user_id]
        return {
            "total_bookings": _count(
                conn,
                "SELECT COUNT(*) FROM bookings b WHERE b.user_id = ?" + _time_filter("b.booked_at", date_range, booking_params),
                booking_params,
            ),
            "total_maintenance_requests": _count(
                conn,
                "SELECT COUNT(*) FROM maintenance_requests r WHERE r.user_id = ?" + _time_filter("r.created_at", date_range, maintenance_params),
                maintenance_params,
            ),
        }

    def user_home_dashboard(self, user_id: int) -> dict:
        """Return one bounded, PII-minimized customer home-dashboard payload.

        The fixed number of queries intentionally replaces a page-load fan-out;
        company cards are aggregated in one grouped query rather than N+1 work.
        """
        conn = get_db_connection()
        try:
            summary = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_bookings,
                    COALESCE(SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END), 0) AS pending_bookings,
                    COALESCE(SUM(CASE WHEN status = 'confirmed' THEN 1 ELSE 0 END), 0) AS confirmed_bookings
                FROM bookings
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
            maintenance_total = _count(
                conn,
                "SELECT COUNT(*) FROM maintenance_requests WHERE user_id = ?",
                [user_id],
            )
            upcoming_total = _count(
                conn,
                """SELECT COUNT(*) FROM bookings b JOIN trips t ON b.trip_id = t.trip_id
                   WHERE b.user_id = ?
                     AND b.status IN ('pending', 'confirmed')
                     AND t.status = 'active'
                     AND datetime(t.departure_time) >= datetime('now')""",
                [user_id],
            )
            next_booking = conn.execute(
                """
                SELECT b.booking_id, b.seats_booked, b.total_price, b.status,
                       b.payment_status, t.from_city, t.to_city, t.departure_time,
                       c.name_ar AS company_name_ar, c.name AS company_name
                FROM bookings b
                JOIN trips t ON b.trip_id = t.trip_id
                JOIN companies c ON t.company_id = c.company_id
                WHERE b.user_id = ?
                  AND b.status IN ('pending', 'confirmed')
                  AND t.status = 'active'
                  AND datetime(t.departure_time) >= datetime('now')
                ORDER BY datetime(t.departure_time) ASC, b.booking_id ASC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
            recent_bookings = conn.execute(
                """
                SELECT b.booking_id, b.seats_booked, b.total_price, b.status,
                       b.payment_status, b.booked_at, t.from_city, t.to_city,
                       t.departure_time, c.name_ar AS company_name_ar, c.name AS company_name,
                       r.rating AS review_rating, r.review_text
                FROM bookings b
                JOIN trips t ON b.trip_id = t.trip_id
                JOIN companies c ON t.company_id = c.company_id
                LEFT JOIN reviews r ON r.booking_id = b.booking_id AND r.user_id = b.user_id
                WHERE b.user_id = ?
                ORDER BY datetime(b.booked_at) DESC, b.booking_id DESC
                LIMIT ?
                """,
                (user_id, HOME_RECENT_BOOKING_LIMIT),
            ).fetchall()
            latest_maintenance = conn.execute(
                """
                SELECT request_id, service_type, preferred_date, status, created_at
                FROM maintenance_requests
                WHERE user_id = ?
                ORDER BY datetime(created_at) DESC, request_id DESC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
            companies = conn.execute(
                """
                SELECT c.company_id, c.name_ar, c.name, c.city,
                       COUNT(DISTINCT t.trip_id) AS available_upcoming_trips,
                       COUNT(DISTINCT t.from_city || char(31) || t.to_city) AS available_upcoming_routes,
                       ra.average_rating, COALESCE(ra.review_count, 0) AS review_count
                FROM companies c
                LEFT JOIN trips t
                  ON t.company_id = c.company_id
                 AND t.status = 'active'
                 AND t.available_seats > 0
                 AND datetime(t.departure_time) >= datetime('now')
                LEFT JOIN (
                    SELECT company_id, ROUND(AVG(rating), 1) AS average_rating, COUNT(*) AS review_count
                    FROM reviews GROUP BY company_id
                ) ra ON ra.company_id = c.company_id
                WHERE c.company_type = 'transport'
                  AND c.status = 'active'
                GROUP BY c.company_id
                ORDER BY available_upcoming_trips DESC, available_upcoming_routes DESC, c.company_id ASC
                LIMIT ?
                """,
                (HOME_COMPANY_LIMIT,),
            ).fetchall()
            trips = conn.execute(
                """
                SELECT t.trip_id, t.from_city, t.to_city, t.departure_time,
                       t.available_seats, t.price_jod, t.trip_class,
                       c.name_ar AS company_name_ar, c.name AS company_name
                FROM trips t
                JOIN companies c ON t.company_id = c.company_id
                WHERE t.status = 'active'
                  AND t.available_seats > 0
                  AND datetime(t.departure_time) >= datetime('now')
                  AND c.company_type = 'transport'
                  AND c.status = 'active'
                ORDER BY datetime(t.departure_time) ASC, t.trip_id ASC
                LIMIT ?
                """,
                (HOME_TRIP_LIMIT,),
            ).fetchall()
            review_opportunities = conn.execute(
                """
                SELECT b.booking_id, t.from_city, t.to_city, t.departure_time,
                       c.name_ar AS company_name_ar, c.name AS company_name
                FROM bookings b
                JOIN trips t ON t.trip_id = b.trip_id
                JOIN companies c ON c.company_id = t.company_id
                LEFT JOIN reviews r ON r.booking_id = b.booking_id
                WHERE b.user_id = ?
                  AND b.status = 'confirmed'
                  AND c.company_type = 'transport'
                  AND t.status IN ('active', 'completed')
                  AND datetime(t.departure_time) < datetime('now')
                  AND r.review_id IS NULL
                ORDER BY datetime(t.departure_time) DESC, b.booking_id DESC
                LIMIT ?
                """,
                (user_id, HOME_RECENT_BOOKING_LIMIT),
            ).fetchall()

            return {
                "summary": {
                    "total_bookings": int(summary["total_bookings"]),
                    "pending_bookings": int(summary["pending_bookings"]),
                    "confirmed_bookings": int(summary["confirmed_bookings"]),
                    "total_maintenance_requests": maintenance_total,
                    "upcoming_bookings": upcoming_total,
                },
                "next_booking": dict(next_booking) if next_booking else None,
                "recent_bookings": [dict(row) for row in recent_bookings],
                "latest_maintenance": dict(latest_maintenance) if latest_maintenance else None,
                "companies": [dict(row) for row in companies],
                "upcoming_trips": [dict(row) for row in trips],
                "review_opportunities": [dict(row) for row in review_opportunities],
            }
        finally:
            conn.close()

    def admin_dashboard(self, scope: DashboardScope, date_range: DashboardDateRange) -> dict:
        """Return bounded real analytics for the authenticated admin scope."""
        conn = get_db_connection()
        try:
            if scope.kind == "platform":
                return self._platform_admin_dashboard(conn, date_range)
            if scope.kind == "company":
                return self._company_admin_dashboard(conn, scope.company_id, date_range)
            raise ValueError("Admin dashboard scope is required.")
        finally:
            conn.close()

    def _trend(self, conn, table_sql, timestamp_column, where_sql, params):
        rows = conn.execute(
            f"""SELECT date({timestamp_column}) AS date, COUNT(*) AS count
                 FROM {table_sql} WHERE {where_sql}
                 GROUP BY date({timestamp_column}) ORDER BY date ASC LIMIT ?""",
            [*params, ADMIN_CHART_LIMIT],
        ).fetchall()
        return [dict(row) for row in rows if row["date"]]

    def _platform_admin_dashboard(self, conn, date_range):
        def count(table, column, extra=""):
            params = []
            query = f"SELECT COUNT(*) FROM {table} WHERE 1 = 1 {extra}" + _time_filter(column, date_range, params)
            return _count(conn, query, params)

        booking_params = []
        booking_filter = "1 = 1" + _time_filter("b.booked_at", date_range, booking_params)
        review_params = []
        review_filter = "1 = 1" + _time_filter("r.created_at", date_range, review_params)
        review_stats = conn.execute(
            f"""SELECT COUNT(*) AS review_count, COUNT(DISTINCT r.company_id) AS reviewed_companies,
                       ROUND(AVG(r.rating), 1) AS average_customer_rating
                FROM reviews r WHERE {review_filter}""",
            review_params,
        ).fetchone()
        booking_stats = conn.execute(
            f"""SELECT COUNT(*) AS total,
                       COALESCE(SUM(CASE WHEN b.status = 'confirmed' THEN 1 ELSE 0 END), 0) AS confirmed,
                       COALESCE(SUM(CASE WHEN b.status = 'pending' THEN 1 ELSE 0 END), 0) AS pending,
                       COALESCE(SUM(CASE WHEN b.status = 'cancelled' THEN 1 ELSE 0 END), 0) AS cancelled,
                       COALESCE(SUM(CASE WHEN b.status = 'confirmed' AND b.payment_status = 'paid' THEN b.total_price ELSE 0 END), 0) AS paid_revenue_jod
                FROM bookings b WHERE {booking_filter}""",
            booking_params,
        ).fetchone()
        status_rows = conn.execute(
            f"SELECT b.status AS label, COUNT(*) AS count FROM bookings b WHERE {booking_filter} GROUP BY b.status ORDER BY b.status",
            booking_params,
        ).fetchall()
        company_rows = conn.execute(
            f"""SELECT c.name_ar AS label, COUNT(b.booking_id) AS count
                 FROM companies c
                 LEFT JOIN trips t ON t.company_id = c.company_id
                 LEFT JOIN bookings b ON b.trip_id = t.trip_id AND {booking_filter}
                 WHERE c.company_type = 'transport'
                 GROUP BY c.company_id ORDER BY count DESC, c.company_id ASC LIMIT ?""",
            [*booking_params, ADMIN_CHART_LIMIT],
        ).fetchall()
        preview_booking_params = []
        preview_booking_filter = "1 = 1" + _time_filter("b.booked_at", date_range, preview_booking_params)
        recent_bookings = conn.execute(
            f"""SELECT b.booking_id, b.status, b.payment_status, b.total_price, b.booked_at,
                      t.from_city, t.to_city, c.name_ar AS company_name
                 FROM bookings b JOIN trips t ON b.trip_id = t.trip_id JOIN companies c ON t.company_id = c.company_id
                 WHERE {preview_booking_filter}
                 ORDER BY datetime(b.booked_at) DESC, b.booking_id DESC LIMIT ?""",
            [*preview_booking_params, ADMIN_PREVIEW_LIMIT],
        ).fetchall()
        preview_maintenance_params = []
        preview_maintenance_filter = "1 = 1" + _time_filter("r.created_at", date_range, preview_maintenance_params)
        recent_maintenance = conn.execute(
            f"""SELECT r.request_id, r.service_type, r.status, r.created_at, c.name_ar AS company_name
                 FROM maintenance_requests r LEFT JOIN companies c ON r.company_id = c.company_id
                 WHERE {preview_maintenance_filter}
                 ORDER BY datetime(r.created_at) DESC, r.request_id DESC LIMIT ?""",
            [*preview_maintenance_params, ADMIN_PREVIEW_LIMIT],
        ).fetchall()
        trip_trend_params = []
        trip_trend_filter = "1 = 1" + _time_filter("t.created_at", date_range, trip_trend_params)
        maintenance_trend_params = []
        maintenance_trend_filter = "1 = 1" + _time_filter("r.created_at", date_range, maintenance_trend_params)
        return {
            "kpis": {
                "total_companies": count("companies", "created_at"),
                "active_companies": count("companies", "created_at", "AND status = 'active'"),
                "total_users": count("users", "created_at"),
                "total_trips": count("trips", "created_at"),
                "upcoming_active_trips": count("trips", "created_at", "AND status = 'active' AND datetime(departure_time) >= datetime('now')"),
                "total_bookings": int(booking_stats["total"]), "confirmed_bookings": int(booking_stats["confirmed"]),
                "pending_bookings": int(booking_stats["pending"]), "cancelled_bookings": int(booking_stats["cancelled"]),
                "total_maintenance_requests": count("maintenance_requests", "created_at"),
                "paid_revenue_jod": float(booking_stats["paid_revenue_jod"]),
                "real_review_count": int(review_stats["review_count"]),
                "reviewed_companies": int(review_stats["reviewed_companies"]),
                "average_customer_rating": float(review_stats["average_customer_rating"]) if review_stats["average_customer_rating"] is not None else None,
            },
            "trends": {
                "bookings": self._trend(conn, "bookings b", "b.booked_at", booking_filter, booking_params),
                "trips": self._trend(conn, "trips t", "t.created_at", trip_trend_filter, trip_trend_params),
                "maintenance": self._trend(conn, "maintenance_requests r", "r.created_at", maintenance_trend_filter, maintenance_trend_params),
            },
            "charts": {"booking_status": [dict(row) for row in status_rows], "bookings_by_company": [dict(row) for row in company_rows]},
            "previews": {"bookings": [dict(row) for row in recent_bookings], "maintenance": [dict(row) for row in recent_maintenance]},
        }

    def _company_admin_dashboard(self, conn, company_id, date_range):
        trip_params = [company_id]
        booking_params = [company_id]
        maintenance_params = [company_id]
        review_params = [company_id]
        trip_filter = "t.company_id = ?" + _time_filter("t.created_at", date_range, trip_params)
        booking_filter = "t.company_id = ?" + _time_filter("b.booked_at", date_range, booking_params)
        maintenance_filter = "r.company_id = ?" + _time_filter("r.created_at", date_range, maintenance_params)
        review_filter = "r.company_id = ?" + _time_filter("r.created_at", date_range, review_params)
        review_stats = conn.execute(
            f"SELECT COUNT(*) AS review_count, ROUND(AVG(r.rating), 1) AS average_customer_rating FROM reviews r WHERE {review_filter}",
            review_params,
        ).fetchone()
        booking_stats = conn.execute(
            f"""SELECT COUNT(*) AS total,
                       COALESCE(SUM(CASE WHEN b.status = 'confirmed' THEN 1 ELSE 0 END), 0) AS confirmed,
                       COALESCE(SUM(CASE WHEN b.status = 'pending' THEN 1 ELSE 0 END), 0) AS pending,
                       COALESCE(SUM(CASE WHEN b.status = 'cancelled' THEN 1 ELSE 0 END), 0) AS cancelled,
                       COALESCE(SUM(CASE WHEN b.status = 'confirmed' AND b.payment_status = 'paid' THEN b.total_price ELSE 0 END), 0) AS paid_revenue_jod
                FROM bookings b JOIN trips t ON b.trip_id = t.trip_id WHERE {booking_filter}""",
            booking_params,
        ).fetchone()
        status_rows = conn.execute(f"SELECT b.status AS label, COUNT(*) AS count FROM bookings b JOIN trips t ON b.trip_id = t.trip_id WHERE {booking_filter} GROUP BY b.status ORDER BY b.status", booking_params).fetchall()
        route_rows = conn.execute(f"SELECT t.from_city || ' → ' || t.to_city AS label, COUNT(*) AS count FROM bookings b JOIN trips t ON b.trip_id = t.trip_id WHERE {booking_filter} GROUP BY t.from_city, t.to_city ORDER BY count DESC, label ASC LIMIT ?", [*booking_params, ADMIN_CHART_LIMIT]).fetchall()
        previews = conn.execute(
            f"""SELECT b.booking_id, b.status, b.payment_status, b.total_price, b.booked_at, t.from_city, t.to_city
                 FROM bookings b JOIN trips t ON b.trip_id = t.trip_id WHERE {booking_filter}
                 ORDER BY datetime(b.booked_at) DESC, b.booking_id DESC LIMIT ?""",
            [*booking_params, ADMIN_PREVIEW_LIMIT],
        ).fetchall()
        trips = conn.execute(f"SELECT trip_id, from_city, to_city, departure_time, available_seats, status FROM trips t WHERE {trip_filter} ORDER BY datetime(departure_time) ASC, trip_id ASC LIMIT ?", [*trip_params, ADMIN_PREVIEW_LIMIT]).fetchall()
        maintenance = conn.execute(f"SELECT request_id, service_type, status, created_at FROM maintenance_requests r WHERE {maintenance_filter} ORDER BY datetime(created_at) DESC, request_id DESC LIMIT ?", [*maintenance_params, ADMIN_PREVIEW_LIMIT]).fetchall()
        return {
            "kpis": {
                "total_trips": _count(conn, f"SELECT COUNT(*) FROM trips t WHERE {trip_filter}", trip_params),
                "upcoming_active_trips": _count(conn, f"SELECT COUNT(*) FROM trips t WHERE {trip_filter} AND t.status = 'active' AND datetime(t.departure_time) >= datetime('now')", trip_params),
                "total_bookings": int(booking_stats["total"]), "confirmed_bookings": int(booking_stats["confirmed"]),
                "pending_bookings": int(booking_stats["pending"]), "cancelled_bookings": int(booking_stats["cancelled"]),
                "total_maintenance_requests": _count(conn, f"SELECT COUNT(*) FROM maintenance_requests r WHERE {maintenance_filter}", maintenance_params),
                "paid_revenue_jod": float(booking_stats["paid_revenue_jod"]),
                "real_review_count": int(review_stats["review_count"]),
                "average_customer_rating": float(review_stats["average_customer_rating"]) if review_stats["average_customer_rating"] is not None else None,
            },
            "trends": {
                "bookings": self._trend(conn, "bookings b JOIN trips t ON b.trip_id = t.trip_id", "b.booked_at", booking_filter, booking_params),
                "trips": self._trend(conn, "trips t", "t.created_at", trip_filter, trip_params),
                "maintenance": self._trend(conn, "maintenance_requests r", "r.created_at", maintenance_filter, maintenance_params),
            },
            "charts": {"booking_status": [dict(row) for row in status_rows], "popular_routes": [dict(row) for row in route_rows]},
            "previews": {"bookings": [dict(row) for row in previews], "trips": [dict(row) for row in trips], "maintenance": [dict(row) for row in maintenance]},
        }
