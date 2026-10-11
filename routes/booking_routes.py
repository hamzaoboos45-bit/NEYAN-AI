from flask import Blueprint, request, jsonify, render_template, session
from database.db import get_db_connection
from routes.auth_helpers import company_admin_required, current_company_id, customer_required, login_required
from backend.notifications.service import NotificationService
from backend.nlp.normalizer import normalize_city
from backend.pricing.service import fils_to_jod, money_to_fils

booking_bp = Blueprint("booking", __name__)

VALID_BOOKING_STATUSES = {"pending", "confirmed", "cancelled"}
VALID_PAYMENT_STATUSES = {"unpaid", "paid", "refunded"}


@booking_bp.route("/trips")
@customer_required
def trips_page():
    return render_template("trips.html")


@booking_bp.route("/bookings")
@customer_required
def bookings_page():
    return render_template("bookings.html")


@booking_bp.route("/api/trips")
@customer_required
def search_trips():
    """Customer discovery: upcoming active-company trips with seats only."""
    raw_from_city = request.args.get("from", "").strip()
    raw_to_city = request.args.get("to", "").strip()
    from_city = normalize_city(raw_from_city) if raw_from_city else ""
    to_city = normalize_city(raw_to_city) if raw_to_city else ""
    if raw_from_city and not from_city:
        return jsonify({"error": "from must be a supported governorate.", "code": "invalid_governorate"}), 400
    if raw_to_city and not to_city:
        return jsonify({"error": "to must be a supported governorate.", "code": "invalid_governorate"}), 400
    date      = request.args.get("date", "")
    time_start = request.args.get("time_start", "")
    time_end = request.args.get("time_end", "")
    vehicle_type = request.args.get("vehicle_type", "")

    conn = get_db_connection()
    try:
        query ="""
            SELECT t.trip_id, t.from_city, t.to_city, t.departure_time,
                   t.arrival_time, t.vehicle_type, t.trip_class,
                   t.available_seats, t.price_jod,
                   c.name_ar AS company_name
            FROM trips t
            JOIN companies c ON t.company_id = c.company_id
            WHERE t.status = 'active'
              AND c.status = 'active'
              AND t.available_seats > 0
              AND datetime(t.departure_time) > datetime('now')"""

        params = []

        if from_city:
            query += " AND t.from_city = ?"
            params.append(from_city)
        if to_city:
            query += " AND t.to_city = ?"
            params.append(to_city)
        if date:
            query += " AND t.departure_time LIKE ?"
            params.append(f"{date}%")
        if request.args.get("class"):
            query += " AND t.trip_class = ?"
            params.append(request.args.get("class"))
        if vehicle_type:
            query += " AND t.vehicle_type = ?"
            params.append(vehicle_type)
        if time_start:
            query += " AND substr(t.departure_time, 12, 5) >= ?"
            params.append(time_start)
        if time_end:
            query += " AND substr(t.departure_time, 12, 5) <= ?"
            params.append(time_end)
        query += " ORDER BY t.departure_time ASC, t.trip_id ASC"

        rows = conn.execute(query, params).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@booking_bp.route("/api/bookings", methods=["GET"])
@login_required
def list_bookings():
    """
    Scoped by role (RBAC):
        customer      — only their own bookings
        company_admin — only bookings for trips run by their own company
        super_admin   — every booking on the platform
    """
    status = request.args.get("status", "")
    payment = request.args.get("payment", "")
    role = session.get("role")

    conn = get_db_connection()
    try:
        query = """
            SELECT b.booking_id, b.trip_id, b.passenger_name, b.seats_booked,
                   b.total_price, b.pricing_snapshot_fils, b.status, b.payment_status, b.booked_at,
                   t.from_city, t.to_city, t.departure_time,
                   c.name_ar AS company_name
            FROM bookings b
            JOIN trips t ON b.trip_id = t.trip_id
            JOIN companies c ON t.company_id = c.company_id
            WHERE 1 = 1
        """
        params = []
        if role == "customer":
            query += " AND b.user_id = ?"
            params.append(session["user_id"])
        elif role == "company_admin":
            query += " AND t.company_id = ?"
            params.append(current_company_id())
        # super_admin: no extra filter — sees everything

        if status:
            query += " AND b.status = ?"
            params.append(status)
        if payment:
            query += " AND b.payment_status = ?"
            params.append(payment)
        query += " ORDER BY b.booked_at DESC"

        rows = []
        for row in conn.execute(query, params).fetchall():
            item = dict(row)
            snapshot = item["pricing_snapshot_fils"]
            if snapshot is None:
                snapshot = money_to_fils(item["total_price"], "historical_total", allow_zero=True)
            item["committed_total_price_jod"] = fils_to_jod(snapshot)
            rows.append(item)
        return jsonify(rows)
    finally:
        conn.close()


@booking_bp.route("/api/bookings/<int:booking_id>/status", methods=["PATCH"])
@company_admin_required
def update_booking_status(booking_id):
    """
    RBAC — 'Companies: manage only their own bookings'. A company_admin
    may only update bookings that belong to their own company's trips;
    super_admin may update any booking.
    """
    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    new_payment = data.get("payment_status")

    if new_status is not None and new_status not in VALID_BOOKING_STATUSES:
        return jsonify({"error": "Invalid status value."}), 400
    if new_payment is not None and new_payment not in VALID_PAYMENT_STATUSES:
        return jsonify({"error": "Invalid payment_status value."}), 400
    if new_status is None and new_payment is None:
        return jsonify({"error": "Nothing to update."}), 400

    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        booking = conn.execute(
            """
            SELECT b.booking_id, b.user_id, b.status, b.seats_booked, b.trip_id, t.company_id, t.status AS trip_status,
                   t.from_city, t.to_city
            FROM bookings b JOIN trips t ON b.trip_id = t.trip_id
            WHERE b.booking_id = ?
            """,
            (booking_id,),
        ).fetchone()
        if not booking:
            return jsonify({"error": "Booking not found."}), 404
        if session.get("role") == "company_admin" and booking["company_id"] != current_company_id():
            return jsonify({"error": "You are not allowed to manage this booking."}), 403

        if new_status == "cancelled" and booking["status"] != "cancelled":
            # Cancellation restores the exact seats once, in the same write
            # transaction as the status change. A cancelled trip is not made
            # bookable again, but its historical capacity remains consistent.
            conn.execute("UPDATE trips SET available_seats = available_seats + ? WHERE trip_id = ?", (booking["seats_booked"], booking["trip_id"]))
        if new_status is not None:
            conn.execute(
                "UPDATE bookings SET status = ?, updated_at = datetime('now') WHERE booking_id = ?",
                (new_status, booking_id),
            )
            if new_status != booking["status"] and new_status in {"confirmed", "cancelled"}:
                NotificationService.create(
                    conn, recipient_user_id=booking["user_id"], event_type=f"booking_{new_status}",
                    source_type="booking", source_id=booking_id,
                    metadata={"from_city": booking["from_city"], "to_city": booking["to_city"]},
                    action_target="/trips#my-transportation", transition_key=new_status,
                )
        if new_payment is not None:
            conn.execute(
                "UPDATE bookings SET payment_status = ?, updated_at = datetime('now') WHERE booking_id = ?",
                (new_payment, booking_id),
            )
        conn.commit()
        return jsonify({"status": "updated"})
    finally:
        conn.close()
