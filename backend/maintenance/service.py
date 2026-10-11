"""One server-owned creation path for maintenance requests.

HTTP routes and Chat both call this service.  Client and conversational input
may describe a service, but never provide a price, fee, total, owner, or
status.  Catalog prices are copied to request snapshots at creation time.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import config
from backend.pricing.service import MaintenancePricingService, PricingError
from database.db import get_db_connection


class MaintenanceRequestError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class MaintenanceRequestService:
    """Catalog lookup and request persistence with immutable price snapshots."""

    @staticmethod
    def normalize_preferred_date(value: Any) -> str:
        """Return the one ISO date representation accepted by request storage.

        The chatbot's existing NLP layer intentionally represents supported
        relative phrases as small canonical tokens.  Resolving them here keeps
        the write boundary authoritative for both Chat and HTTP callers rather
        than letting a conversational token leak into the database contract.
        """
        if not isinstance(value, str) or not value.strip():
            raise MaintenanceRequestError("invalid_date", "A preferred date is required.")
        relative = {
            "today": date.today(),
            "tomorrow": date.today() + timedelta(days=1),
            "day_after_tomorrow": date.today() + timedelta(days=2),
        }
        candidate = relative.get(value.strip(), value.strip())
        if isinstance(candidate, date):
            return candidate.isoformat()
        try:
            return date.fromisoformat(candidate).isoformat()
        except ValueError as error:
            raise MaintenanceRequestError("invalid_date", "Preferred date must use YYYY-MM-DD.") from error

    @staticmethod
    def catalog_quote_for_service(service_key: str, quantity: int = 1) -> dict[str, Any] | None:
        conn = get_db_connection()
        try:
            service = conn.execute(
                "SELECT * FROM maintenance_service_catalog WHERE service_key=? AND is_active=1 ORDER BY service_id DESC LIMIT 1",
                (service_key,),
            ).fetchone()
            if not service:
                return None
            if not service["quantity_enabled"] and quantity != 1:
                raise MaintenanceRequestError("invalid_quantity", "This service does not support multiple units.")
            try:
                quote = MaintenancePricingService.quote(service, quantity)
            except PricingError as error:
                raise MaintenanceRequestError(error.code, error.message, error.status) from error
            return {
                "catalog_service_id": int(service["service_id"]),
                "service_key": service["service_key"],
                "name_en": service["name_en"],
                "name_ar": service["name_ar"],
                "pricing_type": service["pricing_type"],
                "quantity": quantity,
                **quote,
            }
        finally:
            conn.close()

    @staticmethod
    def create(user_id: int, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise MaintenanceRequestError("invalid_json", "Request body must be an object.")
        allowed = {"service_type", "service_details", "location", "preferred_date", "customer_name", "customer_phone", "catalog_service_id", "quantity", "notes"}
        unexpected = sorted(set(payload) - allowed)
        if unexpected:
            raise MaintenanceRequestError("forbidden_field", "Client pricing, status, and ownership fields are not accepted.")
        service_type = payload.get("service_type")
        location = payload.get("location")
        preferred_date = payload.get("preferred_date")
        if not isinstance(service_type, str) or not service_type.strip():
            raise MaintenanceRequestError("invalid_service", "Select a supported maintenance service.")
        if not isinstance(location, str) or not location.strip():
            raise MaintenanceRequestError("invalid_location", "A location is required.")
        preferred_date = MaintenanceRequestService.normalize_preferred_date(preferred_date)

        catalog_id = payload.get("catalog_service_id")
        quantity = payload.get("quantity", 1)
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise MaintenanceRequestError("invalid_quantity", "Quantity must be a positive integer.")
        if catalog_id is not None and (isinstance(catalog_id, bool) or not isinstance(catalog_id, int) or catalog_id <= 0):
            raise MaintenanceRequestError("invalid_service", "Catalog service is invalid.")
        if service_type not in {*config.MAINTENANCE_SERVICES, "other"} and catalog_id is None:
            raise MaintenanceRequestError("invalid_service", "Select a supported maintenance service.")

        conn = get_db_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            company = conn.execute("SELECT company_id FROM companies WHERE company_type='maintenance' AND status='active' LIMIT 1").fetchone()
            catalog = None
            quote = None
            if catalog_id is not None:
                catalog = conn.execute("SELECT * FROM maintenance_service_catalog WHERE service_id=? AND is_active=1", (catalog_id,)).fetchone()
                if not catalog:
                    raise MaintenanceRequestError("service_unavailable", "Selected maintenance service is unavailable.", 409)
                if catalog["service_key"] != service_type:
                    raise MaintenanceRequestError("service_mismatch", "Selected service does not match the catalog item.")
                if not catalog["quantity_enabled"] and quantity != 1:
                    raise MaintenanceRequestError("invalid_quantity", "This service does not support multiple units.")
                try:
                    quote = MaintenancePricingService.quote(catalog, quantity)
                except PricingError as error:
                    raise MaintenanceRequestError(error.code, error.message, error.status) from error
            stored_service_type = service_type if service_type in {*config.MAINTENANCE_SERVICES, "other"} else "other"
            cursor = conn.execute(
                """INSERT INTO maintenance_requests
                   (user_id, company_id, service_type, service_details, location, preferred_date,
                    customer_name, customer_phone, notes, catalog_service_id, service_name_en_snapshot,
                    service_name_ar_snapshot, pricing_type_snapshot, quantity, unit_price_fils_snapshot,
                    minimum_price_fils_snapshot, maximum_price_fils_snapshot, service_fee_fils_snapshot,
                    total_minimum_fils_snapshot, total_maximum_fils_snapshot)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (user_id, company["company_id"] if company else None, stored_service_type,
                 payload.get("service_details", ""), location.strip(), preferred_date,
                 payload.get("customer_name", ""), payload.get("customer_phone", ""), payload.get("notes", ""),
                 catalog_id, catalog["name_en"] if catalog else None, catalog["name_ar"] if catalog else None,
                 catalog["pricing_type"] if catalog and quote and quote["pricing_available"] else None, quantity if catalog else None,
                 catalog["unit_price_fils"] if catalog else None, catalog["minimum_price_fils"] if catalog else None,
                 catalog["maximum_price_fils"] if catalog else None, catalog["service_fee_fils"] if catalog else None,
                 quote["minimum_fils"] if quote else None, quote["maximum_fils"] if quote else None),
            )
            conn.commit()
            return {"request_id": cursor.lastrowid, "status": "pending", "pricing_available": quote is not None,
                    "minimum_jod": quote["minimum_jod"] if quote else None,
                    "maximum_jod": quote["maximum_jod"] if quote else None}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
