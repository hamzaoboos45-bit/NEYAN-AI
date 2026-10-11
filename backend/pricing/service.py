"""Deterministic, server-owned pricing for transport and maintenance.

All monetary values are stored in fils (1 JOD = 1000 fils).  Browser values
are never accepted as authoritative prices; request and booking records retain
the server calculation that applied when they were created.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


FILS_PER_JOD = 1000


class PricingError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def money_to_fils(value: Any, field: str = "price", *, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or value is None:
        raise PricingError("invalid_price", f"{field} must be a valid JOD amount.")
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise PricingError("invalid_price", f"{field} must be a valid JOD amount.") from exc
    if not amount.is_finite() or amount < 0 or (not allow_zero and amount == 0):
        raise PricingError("invalid_price", f"{field} must be a positive JOD amount.")
    fils = int(amount * FILS_PER_JOD)
    if fils < 0 or (not allow_zero and fils == 0):
        raise PricingError("invalid_price", f"{field} must be a positive JOD amount.")
    return fils


def fils_to_jod(fils: int | None) -> str | None:
    if fils is None:
        return None
    return format(Decimal(int(fils)) / FILS_PER_JOD, ".3f")


def per_passenger_quote(base_fils: int, passenger_quantity: int) -> int:
    if passenger_quantity <= 0:
        raise PricingError("invalid_quantity", "Passenger quantity must be positive.")
    return int((Decimal(base_fils) / Decimal(passenger_quantity)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class TransportationPricingService:
    """Platform policy lookup and immutable shared-trip booking snapshots."""

    @staticmethod
    def active_policy(conn, *, from_city: str, to_city: str, vehicle_type: str | None, trip_class: str | None):
        return conn.execute(
            """SELECT * FROM transport_pricing_policies
               WHERE is_active=1 AND from_city=? AND to_city=?
                 AND vehicle_type IS ? AND trip_class IS ?
               ORDER BY policy_id DESC LIMIT 1""",
            (from_city, to_city, vehicle_type, trip_class),
        ).fetchone()

    @staticmethod
    def request_quote(conn, intent: dict[str, Any]) -> dict[str, Any]:
        policy = TransportationPricingService.active_policy(
            conn, from_city=intent["from_city"], to_city=intent["to_city"],
            vehicle_type=intent.get("desired_vehicle_type"), trip_class=intent.get("desired_trip_class"),
        )
        if not policy:
            return {"pricing_available": False, "policy_id": None, "base_trip_price_fils": None, "base_trip_price_jod": None,
                    "per_passenger_estimate_jod": None}
        base = int(policy["base_trip_price_fils"])
        return {"pricing_available": True, "policy_id": int(policy["policy_id"]),
                "base_trip_price_fils": base, "base_trip_price_jod": fils_to_jod(base),
                "per_passenger_estimate_fils": per_passenger_quote(base, intent["passenger_quantity"]),
                "per_passenger_estimate_jod": fils_to_jod(per_passenger_quote(base, intent["passenger_quantity"]))}

    @staticmethod
    def booking_snapshot(conn, trip, seats: int) -> tuple[int, float]:
        """Return immutable total fils/JOD for one booking commitment.

        Legacy operational trips retain their historical per-seat ``price_jod``
        meaning. Shared converted trips instead use the base-policy snapshot
        captured on the original forming request.
        """
        base = trip["shared_base_price_fils"] if "shared_base_price_fils" in trip.keys() else None
        request_id = trip["forming_request_id"] if "forming_request_id" in trip.keys() else None
        if base is None or request_id is None:
            total_fils = money_to_fils(trip["price_jod"], "legacy_trip_price", allow_zero=True) * seats
            return total_fils, float(Decimal(total_fils) / FILS_PER_JOD)
        quantity = conn.execute(
            """SELECT COALESCE(SUM(passenger_quantity), 0) AS total
               FROM trip_request_members WHERE request_id=? AND member_status='active'""", (request_id,)
        ).fetchone()["total"]
        if not quantity:
            raise PricingError("pricing_unavailable", "Shared-trip passenger quantity is unavailable.", 409)
        total_fils = per_passenger_quote(int(base), int(quantity)) * seats
        return total_fils, float(Decimal(total_fils) / FILS_PER_JOD)


class MaintenancePricingService:
    @staticmethod
    def quote(service, quantity: int) -> dict[str, Any]:
        if quantity <= 0:
            raise PricingError("invalid_quantity", "Quantity must be positive.")
        fee = int(service["service_fee_fils"] or 0)
        if service["pricing_type"] == "fixed":
            if service["unit_price_fils"] is None:
                return {"pricing_available": False, "minimum_fils": None, "maximum_fils": None,
                        "minimum_jod": None, "maximum_jod": None}
            total = int(service["unit_price_fils"]) * quantity + fee
            return {"pricing_available": True, "minimum_fils": total, "maximum_fils": total,
                    "minimum_jod": fils_to_jod(total), "maximum_jod": fils_to_jod(total)}
        if service["minimum_price_fils"] is None or service["maximum_price_fils"] is None:
            return {"pricing_available": False, "minimum_fils": None, "maximum_fils": None,
                    "minimum_jod": None, "maximum_jod": None}
        minimum = int(service["minimum_price_fils"]) * quantity + fee
        maximum = int(service["maximum_price_fils"]) * quantity + fee
        return {"pricing_available": True, "minimum_fils": minimum, "maximum_fils": maximum,
                "minimum_jod": fils_to_jod(minimum), "maximum_jod": fils_to_jod(maximum)}
