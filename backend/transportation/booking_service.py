"""Authoritative transactional operations for operational-trip bookings.

The chat flow and any future booking boundary use this service rather than
issuing booking SQL themselves.  Forming-trip demand remains intentionally
outside this module: it is not an operational trip and never creates a
booking.
"""

from __future__ import annotations

from decimal import Decimal

from backend.pricing.service import PricingError, TransportationPricingService, fils_to_jod
from database.db import get_db_connection


class BookingError(Exception):
    """Safe, typed outcome returned by the booking domain boundary."""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class BookingService:
    """Search and commit real operational-trip bookings atomically."""

    @staticmethod
    def search_compatible(*, from_city: str, to_city: str, requested_date: str,
                          trip_class: str, seats: int, departure_time: str | None = None) -> list[dict]:
        """Return only bookable, future trips from active companies.

        This is deliberately a read-only discovery operation.  The exact
        ``trip_id`` returned here is retained by the caller and is revalidated
        again by :meth:`create` at confirmation time.
        """
        if not all(isinstance(value, str) and value for value in (from_city, to_city, requested_date, trip_class)):
            return []
        if isinstance(seats, bool) or not isinstance(seats, int) or seats <= 0:
            return []
        conn = get_db_connection()
        try:
            query = """SELECT t.trip_id, c.company_id, c.name_ar, t.price_jod,
                              t.departure_time, t.available_seats, t.vehicle_type,
                              t.trip_class
                       FROM trips t
                       JOIN companies c ON t.company_id=c.company_id
                       WHERE t.from_city=? AND t.to_city=?
                         AND t.trip_class=? AND t.available_seats>=?
                         AND t.status='active' AND c.status='active'
                         AND datetime(t.departure_time) > datetime('now')
                         AND t.departure_time LIKE ?"""
            params: list[object] = [from_city, to_city, trip_class, seats, f"{requested_date}%"]
            if departure_time:
                query += " AND substr(t.departure_time, 12, 5) = ?"
                params.append(departure_time)
            query += " ORDER BY t.departure_time, c.name_ar, t.trip_id"
            return [dict(row) for row in conn.execute(query, params).fetchall()]
        finally:
            conn.close()

    @staticmethod
    def create(*, user_id: int, trip_id: int, seats: int, passenger_name: str = "ضيف") -> dict:
        """Create exactly one booking and decrement capacity in one transaction.

        The conditional availability update is the final concurrency guard;
        SQLite's immediate write transaction makes the read/price/write
        sequence serializable for this application.
        """
        if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
            raise BookingError("owner_required", "A valid customer is required.", 403)
        if isinstance(trip_id, bool) or not isinstance(trip_id, int) or trip_id <= 0:
            raise BookingError("not_found", "The selected trip is unavailable.", 404)
        if isinstance(seats, bool) or not isinstance(seats, int) or seats <= 0:
            raise BookingError("invalid_seats", "Seat quantity must be positive.")

        conn = get_db_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            trip = conn.execute(
                """SELECT t.trip_id, t.price_jod, t.forming_request_id, t.shared_base_price_fils,
                          t.available_seats, t.departure_time, t.status, c.status AS company_status
                   FROM trips t JOIN companies c ON c.company_id=t.company_id
                   WHERE t.trip_id=?""",
                (trip_id,),
            ).fetchone()
            if not trip:
                raise BookingError("not_found", "The selected trip is unavailable.", 404)
            if trip["status"] != "active" or trip["company_status"] != "active" or conn.execute(
                "SELECT datetime(?) > datetime('now')", (trip["departure_time"],)
            ).fetchone()[0] != 1:
                raise BookingError("not_bookable", "The selected trip is no longer bookable.", 409)

            try:
                total_fils, total = TransportationPricingService.booking_snapshot(conn, trip, seats)
            except PricingError as error:
                raise BookingError("pricing_unavailable", "The current trip price is unavailable.", error.status) from error

            updated = conn.execute(
                """UPDATE trips SET available_seats = available_seats - ?
                   WHERE trip_id=? AND status='active' AND available_seats >= ?""",
                (seats, trip_id, seats),
            )
            if updated.rowcount != 1:
                raise BookingError("capacity_exceeded", "The selected trip no longer has enough seats.", 409)

            booking = conn.execute(
                """INSERT INTO bookings
                   (user_id, trip_id, seats_booked, total_price, passenger_name, pricing_snapshot_fils)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, trip_id, seats, total, passenger_name or "ضيف", total_fils),
            )
            conn.commit()
            return {
                "booking_id": booking.lastrowid,
                "trip_id": trip_id,
                "seats_booked": seats,
                "total_price": float(Decimal(str(total))),
                "pricing_snapshot_fils": total_fils,
                "committed_total_price_jod": fils_to_jod(total_fils),
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def preview(*, trip_id: int, seats: int) -> dict:
        """Return the current server-derived amount before confirmation.

        A preview is intentionally not a booking commitment.  It is evaluated
        again inside ``create`` so a changed shared-trip participant count can
        never cause a stale browser or Chat amount to become authoritative.
        """
        if isinstance(trip_id, bool) or not isinstance(trip_id, int) or trip_id <= 0:
            raise BookingError("not_found", "The selected trip is unavailable.", 404)
        if isinstance(seats, bool) or not isinstance(seats, int) or seats <= 0:
            raise BookingError("invalid_seats", "Seat quantity must be positive.")
        conn = get_db_connection()
        try:
            trip = conn.execute(
                """SELECT t.trip_id, t.price_jod, t.forming_request_id, t.shared_base_price_fils,
                          t.departure_time, t.status, c.status AS company_status
                   FROM trips t JOIN companies c ON c.company_id=t.company_id
                   WHERE t.trip_id=?""",
                (trip_id,),
            ).fetchone()
            if not trip:
                raise BookingError("not_found", "The selected trip is unavailable.", 404)
            if trip["status"] != "active" or trip["company_status"] != "active" or conn.execute(
                "SELECT datetime(?) > datetime('now')", (trip["departure_time"],)
            ).fetchone()[0] != 1:
                raise BookingError("not_bookable", "The selected trip is no longer bookable.", 409)
            try:
                total_fils, _total = TransportationPricingService.booking_snapshot(conn, trip, seats)
            except PricingError as error:
                raise BookingError("pricing_unavailable", "The current trip price is unavailable.", error.status) from error
            return {
                "price_semantics": "current_booking_total",
                "seats": seats,
                "unit_price_jod": fils_to_jod(total_fils // seats),
                "total_price_jod": fils_to_jod(total_fils),
            }
        finally:
            conn.close()
