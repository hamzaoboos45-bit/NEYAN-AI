"""Customer review creation backed by eligible, owned transport bookings."""

import sqlite3

from flask import Blueprint, current_app, jsonify, request, session

from database.db import get_db_connection
from routes.auth_helpers import customer_required


review_bp = Blueprint("review", __name__)
MAX_REVIEW_TEXT_LENGTH = 1000


def _error(code, message, status):
    return jsonify({"error": {"code": code, "message": message}}), status


def _valid_positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


@review_bp.route("/api/reviews", methods=["POST"])
@customer_required
def create_review():
    """Create exactly one review for an owned, completed-experience booking.

    Completion is not reliably written by the existing booking lifecycle, so
    eligibility deliberately uses a conservative proxy: confirmed booking,
    non-cancelled trip, and a departure timestamp in the past. The company is
    selected only through the booking -> trip relationship, never from input.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("invalid_json", "Request body must be a JSON object.", 400)
    if "company_id" in data:
        return _error("client_company_not_allowed", "Company is derived from the booking.", 400)

    booking_id = data.get("booking_id")
    rating = data.get("rating")
    review_text = data.get("review_text", "")
    if not _valid_positive_int(booking_id):
        return _error("invalid_booking_id", "booking_id must be a positive integer.", 400)
    if not isinstance(rating, int) or isinstance(rating, bool) or not 1 <= rating <= 5:
        return _error("invalid_rating", "rating must be an integer from 1 to 5.", 400)
    if not isinstance(review_text, str):
        return _error("invalid_review_text", "review_text must be a string.", 400)
    review_text = review_text.strip()
    if len(review_text) > MAX_REVIEW_TEXT_LENGTH:
        return _error("review_text_too_long", f"review_text must be at most {MAX_REVIEW_TEXT_LENGTH} characters.", 400)

    conn = get_db_connection()
    try:
        # SQLite's write transaction and reviews.booking_id UNIQUE constraint
        # jointly protect against concurrent duplicate submissions.
        conn.execute("BEGIN IMMEDIATE")
        booking = conn.execute(
            """
            SELECT b.booking_id, t.company_id
            FROM bookings b
            JOIN trips t ON t.trip_id = b.trip_id
            JOIN companies c ON c.company_id = t.company_id
            WHERE b.booking_id = ?
              AND b.user_id = ?
              AND b.status = 'confirmed'
              AND c.company_type = 'transport'
              AND t.status IN ('active', 'completed')
              AND datetime(t.departure_time) < datetime('now')
            """,
            (booking_id, session["user_id"]),
        ).fetchone()
        if not booking:
            conn.rollback()
            return _error("review_not_eligible", "This booking is not eligible for a review.", 403)

        cursor = conn.execute(
            """INSERT INTO reviews (user_id, booking_id, company_id, rating, review_text)
               VALUES (?, ?, ?, ?, ?)""",
            (session["user_id"], booking["booking_id"], booking["company_id"], rating, review_text or None),
        )
        conn.commit()
        return jsonify({
            "data": {
                "review_id": cursor.lastrowid,
                "booking_id": booking["booking_id"],
                "company_id": booking["company_id"],
                "rating": rating,
                "review_text": review_text or None,
            }
        }), 201
    except sqlite3.IntegrityError:
        conn.rollback()
        return _error("duplicate_review", "A review already exists for this booking.", 409)
    except Exception:
        conn.rollback()
        current_app.logger.exception("Review creation failed")
        return _error("review_unavailable", "Review submission is unavailable. Please try again.", 500)
    finally:
        conn.close()
