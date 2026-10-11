"""Transactional domain service for Phase 5 forming-trip demand.

This module deliberately never creates a ``trips`` row, booking, or price.
Step 4 records the super-admin assignment and company decision, while a later
phase remains responsible for the separately authorized operational conversion.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import json
import sqlite3
from typing import Any

import config
from backend.nlp.normalizer import normalize_city
from backend.notifications.service import NotificationService
from backend.pricing.service import TransportationPricingService, fils_to_jod, per_passenger_quote
from database.db import get_db_connection


OPEN_STATUSES = ("collecting", "minimum_reached")
AUTHORITY_FIELDS = {
    "creator_user_id", "user_id", "assigned_company_id", "company_id",
    "converted_trip_id", "status", "minimum_passengers", "maximum_passengers",
    "minimum", "maximum",
    "base_trip_price_fils", "base_trip_price_jod", "transport_pricing_policy_id",
}


class TripRequestError(Exception):
    """A safe, structured domain error suitable for an API boundary."""

    def __init__(self, code: str, message: str, status: int = 400, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}


def _utc_now() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def _require_object(payload: Any) -> dict:
    if not isinstance(payload, dict):
        raise TripRequestError("invalid_json", "A JSON object is required.")
    return payload


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TripRequestError("invalid_field", f"{field} must be a positive integer.", details={"field": field})
    return value


def _optional_preference(value: Any, valid: list[str], field: str) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or value.strip().lower() not in valid:
        raise TripRequestError("invalid_field", f"{field} is invalid.", details={"field": field})
    return value.strip().lower()


def _parse_time(value: Any, field: str) -> time | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise TripRequestError("invalid_field", f"{field} must use HH:MM.", details={"field": field})
    try:
        return time.fromisoformat(value.strip())
    except ValueError as exc:
        raise TripRequestError("invalid_field", f"{field} must use HH:MM.", details={"field": field}) from exc


def _time_text(value: time | None) -> str | None:
    return value.strftime("%H:%M") if value else None


def _validate_intent(payload: Any, *, for_search: bool = False) -> dict[str, Any]:
    data = _require_object(payload)
    if not for_search:
        attempted = sorted(AUTHORITY_FIELDS.intersection(data))
        if attempted:
            raise TripRequestError(
                "forbidden_field", "Client authority fields are not accepted.", 400,
                {"fields": attempted},
            )

    def city(field: str) -> str:
        raw = data.get(field)
        canonical = normalize_city(raw.strip()) if isinstance(raw, str) else None
        if not canonical:
            raise TripRequestError("invalid_field", f"{field} must be a supported city.", details={"field": field})
        return canonical

    from_city, to_city = city("from_city"), city("to_city")
    if from_city == to_city:
        raise TripRequestError("invalid_route", "Origin and destination must be different.")

    raw_date = data.get("requested_date")
    if not isinstance(raw_date, str):
        raise TripRequestError("invalid_field", "requested_date must use YYYY-MM-DD.", details={"field": "requested_date"})
    try:
        requested_date = date.fromisoformat(raw_date.strip())
    except ValueError as exc:
        raise TripRequestError("invalid_field", "requested_date must use YYYY-MM-DD.", details={"field": "requested_date"}) from exc
    if requested_date <= _utc_now().date():
        raise TripRequestError("ineligible_date", "requested_date must be in the future.", details={"field": "requested_date"})

    start = _parse_time(data.get("requested_time_start"), "requested_time_start")
    end = _parse_time(data.get("requested_time_end"), "requested_time_end")
    if end and not start:
        raise TripRequestError("invalid_time_window", "A time window end requires a start time.")
    if start and not end:
        end = start
    if start and end and start > end:
        raise TripRequestError("invalid_time_window", "requested_time_start must not be after requested_time_end.")

    intent = {
        "from_city": from_city,
        "to_city": to_city,
        "requested_date": requested_date.isoformat(),
        "requested_time_start": _time_text(start),
        "requested_time_end": _time_text(end),
        "desired_vehicle_type": _optional_preference(data.get("desired_vehicle_type"), config.VEHICLE_TYPES, "desired_vehicle_type"),
        "desired_trip_class": _optional_preference(data.get("desired_trip_class"), config.TRIP_CLASSES, "desired_trip_class"),
    }
    if not for_search:
        sharing_mode = data.get("sharing_mode", "private")
        if sharing_mode not in {"private", "shared"}:
            raise TripRequestError("invalid_field", "sharing_mode must be private or shared.", details={"field": "sharing_mode"})
        intent["sharing_mode"] = sharing_mode
        intent["passenger_quantity"] = _positive_int(data.get("passenger_quantity"), "passenger_quantity")
        departure = datetime.combine(requested_date, start or time(23, 59))
        expires = departure - timedelta(hours=config.TRIP_REQUEST_EXPIRY_LEAD_HOURS)
        if expires <= _utc_now():
            raise TripRequestError("expiration_not_feasible", "The request must allow the configured collection lead time.")
        vehicle = intent["desired_vehicle_type"] or "bus"
        policy = config.TRIP_REQUEST_VEHICLE_POLICY[vehicle]
        if intent["passenger_quantity"] > policy["maximum_passengers"]:
            raise TripRequestError("capacity_exceeded", "passenger_quantity exceeds the forming-trip capacity.")
        intent["minimum_passengers"] = policy["minimum_passengers"]
        intent["maximum_passengers"] = policy["maximum_passengers"]
        intent["expires_at"] = expires.strftime("%Y-%m-%d %H:%M:%S")
    return intent


def _expire_open_requests(conn: sqlite3.Connection) -> None:
    conn.execute(
        """UPDATE trip_requests
           SET status='expired', resolved_at=datetime('now'), updated_at=datetime('now')
           WHERE status IN ('collecting', 'minimum_reached')
             AND datetime(expires_at) <= datetime('now')"""
    )


def _aggregate(conn: sqlite3.Connection, request_id: int) -> int:
    return int(conn.execute(
        """SELECT COALESCE(SUM(passenger_quantity), 0) AS total
           FROM trip_request_members
           WHERE request_id=? AND member_status='active'""", (request_id,)
    ).fetchone()["total"])


def _recalculate_state(conn: sqlite3.Connection, request_id: int) -> None:
    row = conn.execute("SELECT minimum_passengers, status FROM trip_requests WHERE request_id=?", (request_id,)).fetchone()
    if row and row["status"] in OPEN_STATUSES:
        status = "minimum_reached" if _aggregate(conn, request_id) >= row["minimum_passengers"] else "collecting"
        conn.execute("UPDATE trip_requests SET status=?, updated_at=datetime('now') WHERE request_id=?", (status, request_id))


def _forming_metadata(row: sqlite3.Row, **extra: Any) -> dict[str, Any]:
    metadata = {"from_city": row["from_city"], "to_city": row["to_city"], "requested_date": row["requested_date"]}
    metadata.update(extra)
    return metadata


def _notify_forming(conn: sqlite3.Connection, row: sqlite3.Row, event_type: str,
                    recipients: list[int], *, action_target: str, transition_key: str, **extra: Any) -> None:
    NotificationService.create_for_recipients(
        conn, recipients, event_type=event_type, source_type="trip_request",
        source_id=int(row["request_id"]), metadata=_forming_metadata(row, **extra),
        action_target=action_target, transition_key=transition_key,
    )


def _notify_minimum_reached(conn: sqlite3.Connection, row: sqlite3.Row) -> None:
    # The dedupe key is lifecycle-scoped: later recalculation/retry cannot
    # spam participants, and no passenger threshold is duplicated here.
    recipients = NotificationService.participant_user_ids(conn, int(row["request_id"]))
    _notify_forming(conn, row, "forming_minimum_reached", recipients,
                    action_target="/trips#my-transportation", transition_key="minimum_reached")
    _notify_forming(conn, row, "forming_ready_for_assignment", NotificationService.super_admin_user_ids(conn),
                    action_target="/admin", transition_key="minimum_reached")


def _row_to_card(row: sqlite3.Row) -> dict[str, Any]:
    current = int(row["current_passengers"])
    minimum, maximum = int(row["minimum_passengers"]), int(row["maximum_passengers"])
    decision = row["company_decision"] if "company_decision" in row.keys() else "pending"
    workflow_state = "converted" if row["status"] == "converted" else "accepted" if decision == "accepted" else "rejected" if decision == "rejected" else "company_review" if row["assigned_company_id"] else row["status"]
    return {
        "request_id": row["request_id"], "from_city": row["from_city"], "to_city": row["to_city"],
        "requested_date": row["requested_date"], "requested_time_start": row["requested_time_start"],
        "requested_time_end": row["requested_time_end"], "desired_vehicle_type": row["desired_vehicle_type"],
        "desired_trip_class": row["desired_trip_class"], "status": row["status"], "expires_at": row["expires_at"],
        "minimum_passengers": minimum, "maximum_passengers": maximum, "current_passengers": current,
        "remaining_to_minimum": max(0, minimum - current), "remaining_capacity": max(0, maximum - current),
        "is_member": bool(row["is_member"]), "my_passenger_quantity": row["my_passenger_quantity"],
        "is_creator": bool(row["is_creator"]),
        "company_decision": decision,
        "workflow_state": workflow_state,
        "converted_trip_id": row["converted_trip_id"],
        "sharing_mode": row["sharing_mode"] if "sharing_mode" in row.keys() else "private",
        "pricing_available": bool(row["base_trip_price_fils"]) if "base_trip_price_fils" in row.keys() else False,
        "base_trip_price_jod": (fils_to_jod(int(row["base_trip_price_fils"])) if "base_trip_price_fils" in row.keys() and row["base_trip_price_fils"] is not None else None),
        "per_passenger_estimate_jod": (fils_to_jod(per_passenger_quote(int(row["base_trip_price_fils"]), max(current, 1))) if "base_trip_price_fils" in row.keys() and row["base_trip_price_fils"] is not None else None),
    }


def _cards(conn: sqlite3.Connection, user_id: int, where: str, params: tuple = ()) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""SELECT r.*, COALESCE(SUM(CASE WHEN m.member_status='active' THEN m.passenger_quantity ELSE 0 END),0) AS current_passengers,
                  MAX(CASE WHEN m.user_id=? AND m.member_status='active' THEN 1 ELSE 0 END) AS is_member,
                  MAX(CASE WHEN m.user_id=? AND m.member_status='active' THEN m.passenger_quantity END) AS my_passenger_quantity,
                  CASE WHEN r.creator_user_id=? THEN 1 ELSE 0 END AS is_creator
             FROM trip_requests r LEFT JOIN trip_request_members m ON m.request_id=r.request_id
             WHERE {where}
             GROUP BY r.request_id ORDER BY r.requested_date, r.requested_time_start, r.request_id""",
        (user_id, user_id, user_id, *params),
    ).fetchall()
    return [_row_to_card(row) for row in rows]


def _windows_overlap(a: dict, b: dict) -> bool:
    # Requests without a time are intentionally only compatible with another
    # untimed request: a broad unknown-time match would cause false merging.
    if not a["requested_time_start"] or not b["requested_time_start"]:
        return not a["requested_time_start"] and not b["requested_time_start"]
    return a["requested_time_start"] <= b["requested_time_end"] and b["requested_time_start"] <= a["requested_time_end"]


def _compatible(card: dict, intent: dict) -> bool:
    if any(card[key] != intent[key] for key in ("from_city", "to_city", "requested_date")):
        return False
    if not _windows_overlap(card, intent):
        return False
    for key in ("desired_vehicle_type", "desired_trip_class"):
        if card[key] is not None and intent[key] is not None and card[key] != intent[key]:
            return False
    return True


def _admin_card(row: sqlite3.Row) -> dict[str, Any]:
    """Aggregate-only queue contract for both admin roles; never expose members."""
    current = int(row["current_passengers"])
    minimum, maximum = int(row["minimum_passengers"]), int(row["maximum_passengers"])
    return {
        "request_id": row["request_id"], "from_city": row["from_city"], "to_city": row["to_city"],
        "requested_date": row["requested_date"], "requested_time_start": row["requested_time_start"],
        "requested_time_end": row["requested_time_end"], "desired_vehicle_type": row["desired_vehicle_type"],
        "desired_trip_class": row["desired_trip_class"], "status": row["status"],
        "company_decision": row["company_decision"], "expires_at": row["expires_at"],
        "assigned_at": row["assigned_at"], "company_decision_at": row["company_decision_at"],
        "assigned_company_id": row["assigned_company_id"], "assigned_company_name": row["assigned_company_name"],
        "converted_trip_id": row["converted_trip_id"],
        "current_passengers": current, "minimum_passengers": minimum, "maximum_passengers": maximum,
        "remaining_to_minimum": max(0, minimum - current), "remaining_capacity": max(0, maximum - current),
    }


def _admin_cards(conn: sqlite3.Connection, where: str, params: tuple = ()) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""SELECT r.*, c.name_ar AS assigned_company_name,
                   COALESCE(SUM(CASE WHEN m.member_status='active' THEN m.passenger_quantity ELSE 0 END), 0) AS current_passengers
              FROM trip_requests r
              LEFT JOIN companies c ON c.company_id=r.assigned_company_id
              LEFT JOIN trip_request_members m ON m.request_id=r.request_id
             WHERE {where}
             GROUP BY r.request_id
             ORDER BY r.requested_date ASC, r.request_id ASC
             LIMIT 100""",
        params,
    ).fetchall()
    return [_admin_card(row) for row in rows]


def _conversion_value(payload: Any) -> dict[str, Any]:
    """Validate only company-controlled facts needed by the existing trips schema."""
    data = _require_object(payload)
    allowed = {"departure_time", "arrival_time", "vehicle_type", "trip_class", "price_jod", "total_seats"}
    if set(data) != allowed:
        raise TripRequestError("invalid_conversion_payload", "Provide only the complete operational configuration.")
    try:
        departure = datetime.fromisoformat(data["departure_time"])
        arrival = datetime.fromisoformat(data["arrival_time"])
    except (TypeError, ValueError) as exc:
        raise TripRequestError("invalid_schedule", "Departure and arrival must be ISO date-times.") from exc
    if arrival <= departure:
        raise TripRequestError("invalid_schedule", "Arrival must be after departure.")
    if data["vehicle_type"] not in config.VEHICLE_TYPES or data["trip_class"] not in config.TRIP_CLASSES:
        raise TripRequestError("invalid_configuration", "Vehicle type or class is unsupported.")
    if isinstance(data["total_seats"], bool) or not isinstance(data["total_seats"], int) or data["total_seats"] <= 0:
        raise TripRequestError("invalid_capacity", "Operational capacity must be a positive whole number.")
    if isinstance(data["price_jod"], bool) or not isinstance(data["price_jod"], (int, float)) or data["price_jod"] < 0:
        raise TripRequestError("invalid_price", "Final price must be a non-negative number.")
    return {"departure": departure, "arrival": arrival, "vehicle_type": data["vehicle_type"], "trip_class": data["trip_class"], "price": float(data["price_jod"]), "seats": data["total_seats"]}


def _log_decision(conn: sqlite3.Connection, actor_user_id: int, action: str, request_id: int, company_id: int | None) -> None:
    conn.execute(
        """INSERT INTO activity_logs (user_id, action_type, details_json)
           VALUES (?, 'admin_action', ?)""",
        (actor_user_id, json.dumps({"forming_trip_action": action, "request_id": request_id, "company_id": company_id})),
    )


def _ensure_minimum_reached(conn: sqlite3.Connection, row: sqlite3.Row) -> None:
    if row["status"] != "minimum_reached" or _aggregate(conn, row["request_id"]) < row["minimum_passengers"]:
        if row["status"] in OPEN_STATUSES:
            _recalculate_state(conn, row["request_id"])
        raise TripRequestError("not_eligible", "The request has not reached the required passenger demand.", 409)


class TripRequestService:
    """One authoritative API/chat-ready service for forming-trip demand."""

    @staticmethod
    def create(user_id: int, payload: Any) -> dict[str, Any]:
        intent = _validate_intent(payload)
        conn = get_db_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            _expire_open_requests(conn)
            matches = [card for card in _cards(conn, user_id, "r.status IN ('collecting', 'minimum_reached') AND r.sharing_mode='shared'") if _compatible(card, intent)] if intent["sharing_mode"] == "shared" else []
            if matches:
                raise TripRequestError("compatible_request_exists", "Compatible forming trips already exist; join one explicitly instead.", 409, {"compatible_requests": matches})
            quote = TransportationPricingService.request_quote(conn, intent) if intent["sharing_mode"] == "shared" else {"policy_id": None, "base_trip_price_fils": None}
            cur = conn.execute(
                """INSERT INTO trip_requests
                   (creator_user_id, from_city, to_city, requested_date, requested_time_start, requested_time_end,
                    desired_vehicle_type, desired_trip_class, minimum_passengers, maximum_passengers, expires_at,
                    sharing_mode, transport_pricing_policy_id, base_trip_price_fils)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, intent["from_city"], intent["to_city"], intent["requested_date"], intent["requested_time_start"], intent["requested_time_end"],
                 intent["desired_vehicle_type"], intent["desired_trip_class"], intent["minimum_passengers"],
                 intent["maximum_passengers"], intent["expires_at"], intent["sharing_mode"], quote["policy_id"], quote["base_trip_price_fils"]),
            )
            request_id = cur.lastrowid
            conn.execute("INSERT INTO trip_request_members (request_id, user_id, passenger_quantity) VALUES (?, ?, ?)", (request_id, user_id, intent["passenger_quantity"]))
            _recalculate_state(conn, request_id)
            request_row = conn.execute("SELECT * FROM trip_requests WHERE request_id=?", (request_id,)).fetchone()
            if request_row["status"] == "minimum_reached":
                _notify_minimum_reached(conn, request_row)
            card = _cards(conn, user_id, "r.request_id=?", (request_id,))[0]
            conn.commit()
            return card
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def browse(user_id: int) -> list[dict[str, Any]]:
        conn = get_db_connection()
        try:
            _expire_open_requests(conn)
            cards = _cards(conn, user_id, "r.status IN ('collecting', 'minimum_reached') AND (r.sharing_mode='shared' OR r.creator_user_id=? OR EXISTS (SELECT 1 FROM trip_request_members own WHERE own.request_id=r.request_id AND own.user_id=?))", (user_id, user_id))
            conn.commit()
            return cards
        finally:
            conn.close()

    @staticmethod
    def compatible(user_id: int, query: Any) -> list[dict[str, Any]]:
        intent = _validate_intent(query, for_search=True)
        conn = get_db_connection()
        try:
            _expire_open_requests(conn)
            cards = _cards(conn, user_id, "r.status IN ('collecting', 'minimum_reached') AND r.sharing_mode='shared'")
            conn.commit()
            return [card for card in cards if _compatible(card, intent)]
        finally:
            conn.close()

    @staticmethod
    def preview_shared_pricing(query: Any) -> dict[str, Any]:
        """Return the active shared-demand estimate without creating demand.

        This is deliberately a read-only service operation.  Chat and the
        Transportation UI can therefore describe an estimate before an
        explicit creation confirmation without copying pricing policy logic
        into either client.
        """
        if not isinstance(query, dict):
            raise TripRequestError("invalid_json", "Request body must be an object.")
        candidate = dict(query)
        candidate["sharing_mode"] = "shared"
        intent = _validate_intent(candidate)
        conn = get_db_connection()
        try:
            return TransportationPricingService.request_quote(conn, intent)
        finally:
            conn.close()

    @staticmethod
    def mine(user_id: int) -> list[dict[str, Any]]:
        conn = get_db_connection()
        try:
            _expire_open_requests(conn)
            cards = _cards(conn, user_id, "r.creator_user_id=? OR EXISTS (SELECT 1 FROM trip_request_members own WHERE own.request_id=r.request_id AND own.user_id=?)", (user_id, user_id))
            conn.commit()
            return cards
        finally:
            conn.close()

    @staticmethod
    def join(user_id: int, request_id: int, payload: Any) -> dict[str, Any]:
        data = _require_object(payload)
        rejected = sorted(AUTHORITY_FIELDS.intersection(data))
        if rejected:
            raise TripRequestError("forbidden_field", "Client authority fields are not accepted.", details={"fields": rejected})
        quantity = _positive_int(data.get("passenger_quantity"), "passenger_quantity")
        conn = get_db_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            _expire_open_requests(conn)
            request_row = conn.execute("SELECT * FROM trip_requests WHERE request_id=?", (request_id,)).fetchone()
            if not request_row:
                raise TripRequestError("not_found", "Forming trip request was not found.", 404)
            if request_row["company_decision"] == "accepted":
                raise TripRequestError("request_frozen", "Accepted demand is frozen pending operational preparation.", 409)
            if request_row["sharing_mode"] != "shared":
                raise TripRequestError("private_request", "Private forming trips cannot be joined.", 403)
            if request_row["status"] not in OPEN_STATUSES:
                # _expire_open_requests() may have just transitioned this
                # exact request.  Preserve that authoritative lifecycle
                # transition before reporting that it cannot be joined; an
                # exception path must not roll the expiry back to collecting.
                conn.commit()
                raise TripRequestError("not_joinable", "This forming trip is no longer joinable.", 409)
            membership = conn.execute("SELECT member_status FROM trip_request_members WHERE request_id=? AND user_id=?", (request_id, user_id)).fetchone()
            if membership and membership["member_status"] == "active":
                raise TripRequestError("already_member", "You are already a member of this forming trip.", 409)
            if _aggregate(conn, request_id) + quantity > request_row["maximum_passengers"]:
                raise TripRequestError("capacity_exceeded", "The requested passenger quantity exceeds remaining capacity.", 409)
            if membership:
                conn.execute("UPDATE trip_request_members SET passenger_quantity=?, member_status='active', joined_at=datetime('now'), updated_at=datetime('now') WHERE request_id=? AND user_id=?", (quantity, request_id, user_id))
            else:
                conn.execute("INSERT INTO trip_request_members (request_id, user_id, passenger_quantity) VALUES (?, ?, ?)", (request_id, user_id, quantity))
            _recalculate_state(conn, request_id)
            request_row = conn.execute("SELECT * FROM trip_requests WHERE request_id=?", (request_id,)).fetchone()
            if request_row["status"] == "minimum_reached":
                _notify_minimum_reached(conn, request_row)
            card = _cards(conn, user_id, "r.request_id=?", (request_id,))[0]
            conn.commit()
            return card
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def leave(user_id: int, request_id: int) -> dict[str, Any]:
        conn = get_db_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            _expire_open_requests(conn)
            request_row = conn.execute("SELECT * FROM trip_requests WHERE request_id=?", (request_id,)).fetchone()
            if not request_row:
                raise TripRequestError("not_found", "Forming trip request was not found.", 404)
            if request_row["company_decision"] == "accepted":
                raise TripRequestError("request_frozen", "Accepted demand is frozen pending operational preparation.", 409)
            if request_row["creator_user_id"] == user_id:
                raise TripRequestError("creator_must_cancel", "The creator must cancel the unresolved request instead of leaving it.", 409)
            if request_row["status"] not in OPEN_STATUSES:
                raise TripRequestError("not_mutable", "This forming trip can no longer be changed.", 409)
            membership = conn.execute("SELECT member_status FROM trip_request_members WHERE request_id=? AND user_id=?", (request_id, user_id)).fetchone()
            if not membership or membership["member_status"] != "active":
                raise TripRequestError("not_member", "You are not an active member of this forming trip.", 409)
            conn.execute("UPDATE trip_request_members SET member_status='withdrawn', updated_at=datetime('now') WHERE request_id=? AND user_id=?", (request_id, user_id))
            _recalculate_state(conn, request_id)
            card = _cards(conn, user_id, "r.request_id=?", (request_id,))[0]
            conn.commit()
            return card
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def cancel(user_id: int, request_id: int) -> dict[str, Any]:
        conn = get_db_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            _expire_open_requests(conn)
            row = conn.execute("SELECT * FROM trip_requests WHERE request_id=?", (request_id,)).fetchone()
            if not row:
                raise TripRequestError("not_found", "Forming trip request was not found.", 404)
            if row["company_decision"] == "accepted":
                raise TripRequestError("request_frozen", "Accepted demand is frozen pending operational preparation.", 409)
            if row["creator_user_id"] != user_id:
                raise TripRequestError("not_owner", "Only the request creator may cancel it.", 403)
            if row["status"] not in OPEN_STATUSES:
                raise TripRequestError("not_mutable", "This forming trip can no longer be cancelled.", 409)
            conn.execute("UPDATE trip_requests SET status='cancelled', resolved_at=datetime('now'), updated_at=datetime('now') WHERE request_id=?", (request_id,))
            recipients = [uid for uid in NotificationService.participant_user_ids(conn, request_id) if uid != user_id]
            _notify_forming(conn, row, "forming_cancelled", recipients,
                            action_target="/trips#my-transportation", transition_key="cancelled")
            card = _cards(conn, user_id, "r.request_id=?", (request_id,))[0]
            conn.commit()
            return card
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def admin_queue() -> list[dict[str, Any]]:
        conn = get_db_connection()
        try:
            _expire_open_requests(conn)
            cards = _admin_cards(conn, "r.status IN ('minimum_reached', 'converted')")
            conn.commit()
            return cards
        finally:
            conn.close()

    @staticmethod
    def active_transport_companies() -> list[dict[str, Any]]:
        conn = get_db_connection()
        try:
            rows = conn.execute(
                """SELECT company_id, name, name_ar, city, status
                   FROM companies
                   WHERE company_type='transport' AND status='active'
                   ORDER BY name_ar, company_id"""
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    @staticmethod
    def assign(admin_user_id: int, request_id: int, company_id: int) -> dict[str, Any]:
        conn = get_db_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            _expire_open_requests(conn)
            row = conn.execute("SELECT * FROM trip_requests WHERE request_id=?", (request_id,)).fetchone()
            if not row:
                raise TripRequestError("not_found", "Forming trip request was not found.", 404)
            _ensure_minimum_reached(conn, row)
            if row["sharing_mode"] == "shared" and row["base_trip_price_fils"] is None:
                raise TripRequestError("pricing_unavailable", "A shared demand requires an active platform price before conversion.", 409)
            if row["company_decision"] == "accepted":
                raise TripRequestError("assignment_locked", "Accepted demand cannot be reassigned.", 409)
            company = conn.execute(
                """SELECT company_id FROM companies
                   WHERE company_id=? AND company_type='transport' AND status='active'""", (company_id,)
            ).fetchone()
            if not company:
                raise TripRequestError("invalid_company", "Choose an active transportation company.", 400)
            action = "forming_trip_reassigned" if row["assigned_company_id"] and row["assigned_company_id"] != company_id else "forming_trip_assigned"
            conn.execute(
                """UPDATE trip_requests
                   SET assigned_company_id=?, assigned_at=datetime('now'), assigned_by_user_id=?,
                       company_decision='pending', company_decision_at=NULL, company_decided_by_user_id=NULL,
                       updated_at=datetime('now')
                   WHERE request_id=?""",
                (company_id, admin_user_id, request_id),
            )
            _log_decision(conn, admin_user_id, action, request_id, company_id)
            _notify_forming(conn, row, "forming_company_assigned", NotificationService.participant_user_ids(conn, request_id),
                            action_target="/trips#my-transportation", transition_key=f"assignment:{company_id}")
            _notify_forming(conn, row, "forming_assigned_for_review", NotificationService.company_admin_user_ids(conn, company_id),
                            action_target="/admin", transition_key=f"assignment:{company_id}")
            card = _admin_cards(conn, "r.request_id=?", (request_id,))[0]
            conn.commit()
            return card
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def company_queue(company_id: int) -> list[dict[str, Any]]:
        conn = get_db_connection()
        try:
            _expire_open_requests(conn)
            cards = _admin_cards(conn, "r.assigned_company_id=? AND r.status IN ('minimum_reached', 'converted')", (company_id,))
            conn.commit()
            return cards
        finally:
            conn.close()

    @staticmethod
    def company_decide(company_admin_user_id: int, company_id: int, request_id: int, decision: str) -> dict[str, Any]:
        if decision not in {"accepted", "rejected"}:
            raise TripRequestError("invalid_decision", "Company decision is invalid.")
        conn = get_db_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            _expire_open_requests(conn)
            row = conn.execute("SELECT * FROM trip_requests WHERE request_id=?", (request_id,)).fetchone()
            if not row:
                raise TripRequestError("not_found", "Forming trip request was not found.", 404)
            if row["assigned_company_id"] != company_id:
                raise TripRequestError("not_assigned_to_company", "This request is not assigned to your company.", 403)
            _ensure_minimum_reached(conn, row)
            if row["company_decision"] != "pending":
                raise TripRequestError("decision_already_recorded", "A company decision has already been recorded.", 409)
            if decision == "accepted":
                conn.execute(
                    """UPDATE trip_requests SET company_decision='accepted', company_decision_at=datetime('now'),
                       company_decided_by_user_id=?, updated_at=datetime('now') WHERE request_id=?""",
                    (company_admin_user_id, request_id),
                )
            else:
                # Rejection returns the still-minimum-reached demand to the
                # super-admin queue. The activity log retains the company/audit event.
                conn.execute(
                    """UPDATE trip_requests SET assigned_company_id=NULL, assigned_at=NULL, assigned_by_user_id=NULL,
                       company_decision='rejected', company_decision_at=datetime('now'),
                       company_decided_by_user_id=?, updated_at=datetime('now') WHERE request_id=?""",
                    (company_admin_user_id, request_id),
                )
            _log_decision(conn, company_admin_user_id, "forming_trip_" + decision, request_id, company_id)
            event_type = "forming_company_accepted" if decision == "accepted" else "forming_company_rejected"
            _notify_forming(conn, row, event_type, NotificationService.participant_user_ids(conn, request_id),
                            action_target="/trips#my-transportation", transition_key=f"company_{decision}")
            card = _admin_cards(conn, "r.request_id=?", (request_id,))[0]
            conn.commit()
            return card
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def convert(company_admin_user_id: int, company_id: int, request_id: int, payload: Any) -> dict[str, Any]:
        configuration = _conversion_value(payload)
        conn = get_db_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            _expire_open_requests(conn)
            row = conn.execute("SELECT * FROM trip_requests WHERE request_id=?", (request_id,)).fetchone()
            if not row:
                raise TripRequestError("not_found", "Forming trip request was not found.", 404)
            if row["assigned_company_id"] != company_id:
                raise TripRequestError("not_assigned_to_company", "This request is not assigned to your company.", 403)
            if row["company_decision"] != "accepted":
                raise TripRequestError("not_accepted", "Only accepted demand may become an operational trip.", 409)
            if row["converted_trip_id"] is not None or row["status"] == "converted":
                raise TripRequestError("already_converted", "This demand already has an operational trip.", 409)
            _ensure_minimum_reached(conn, row)
            if configuration["departure"].date().isoformat() != row["requested_date"]:
                raise TripRequestError("incompatible_schedule", "Departure date must match the accepted demand date.", 409)
            departure_clock = configuration["departure"].time()
            if row["requested_time_start"] and departure_clock < time.fromisoformat(row["requested_time_start"]):
                raise TripRequestError("incompatible_schedule", "Departure is before the accepted time window.", 409)
            if row["requested_time_end"] and departure_clock > time.fromisoformat(row["requested_time_end"]):
                raise TripRequestError("incompatible_schedule", "Departure is after the accepted time window.", 409)
            current = _aggregate(conn, request_id)
            if configuration["seats"] < current:
                raise TripRequestError("capacity_below_demand", "Operational capacity cannot be below active accepted demand.", 409)
            cur = conn.execute(
                """INSERT INTO trips (company_id, from_city, to_city, departure_time, arrival_time, vehicle_type, trip_class, total_seats, available_seats, price_jod, forming_request_id, shared_base_price_fils, transport_pricing_policy_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (company_id, row["from_city"], row["to_city"], configuration["departure"].strftime("%Y-%m-%d %H:%M:%S"), configuration["arrival"].strftime("%Y-%m-%d %H:%M:%S"), configuration["vehicle_type"], configuration["trip_class"], configuration["seats"], configuration["seats"], configuration["price"], request_id, row["base_trip_price_fils"] if row["sharing_mode"] == "shared" else None, row["transport_pricing_policy_id"] if row["sharing_mode"] == "shared" else None),
            )
            trip_id = cur.lastrowid
            updated = conn.execute("""UPDATE trip_requests SET converted_trip_id=?, status='converted', resolved_at=datetime('now'), updated_at=datetime('now')
                                      WHERE request_id=? AND converted_trip_id IS NULL AND status='minimum_reached' AND company_decision='accepted'""", (trip_id, request_id))
            if updated.rowcount != 1:
                raise TripRequestError("conversion_conflict", "Demand changed before conversion; retry safely.", 409)
            _log_decision(conn, company_admin_user_id, "forming_trip_converted", request_id, company_id)
            _notify_forming(conn, row, "forming_converted", NotificationService.participant_user_ids(conn, request_id),
                            action_target="/trips", transition_key="converted", trip_id=trip_id)
            conn.commit()
            return {"request_id": request_id, "trip_id": trip_id, "from_city": row["from_city"], "to_city": row["to_city"], "departure_time": configuration["departure"].strftime("%Y-%m-%d %H:%M:%S"), "price_jod": configuration["price"], "total_seats": configuration["seats"]}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
