"""Platform-admin pricing APIs and the customer maintenance catalog."""
from flask import Blueprint, jsonify, render_template, request, session

import config
from backend.nlp.normalizer import normalize_city
from backend.pricing.service import MaintenancePricingService, PricingError, fils_to_jod, money_to_fils
from database.db import get_db_connection
from routes.auth_helpers import customer_required, super_admin_required


pricing_bp = Blueprint("pricing", __name__)


def _error(error):
    return jsonify({"error": {"code": error.code, "message": error.message}}), error.status


def _object():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise PricingError("invalid_json", "A JSON object is required.")
    return data


def _positive_int(value, field="quantity"):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise PricingError("invalid_quantity", f"{field} must be a positive integer.")
    return value


def _transport_payload(data):
    required = {"from_city", "to_city", "vehicle_type", "trip_class", "base_trip_price_jod"}
    if not required.issubset(data):
        raise PricingError("missing_fields", "Route, vehicle, class, and base price are required.")
    origin, destination = normalize_city(data["from_city"]), normalize_city(data["to_city"])
    if not origin or not destination or origin == destination:
        raise PricingError("invalid_route", "A supported directional route is required.")
    if data["vehicle_type"] not in config.VEHICLE_TYPES or data["trip_class"] not in config.TRIP_CLASSES:
        raise PricingError("invalid_configuration", "Vehicle type or class is unsupported.")
    return origin, destination, data["vehicle_type"], data["trip_class"], money_to_fils(data["base_trip_price_jod"], "base_trip_price_jod")


def _policy(row):
    result = dict(row)
    result["base_trip_price_jod"] = fils_to_jod(result.pop("base_trip_price_fils"))
    result["is_active"] = bool(result["is_active"])
    return result


@pricing_bp.route("/admin/pricing")
@super_admin_required
def pricing_page():
    return render_template("pricing_admin.html")


@pricing_bp.route("/api/admin/pricing/transport-policies", methods=["GET", "POST"])
@super_admin_required
def transport_policies():
    conn = get_db_connection()
    try:
        if request.method == "GET":
            rows = conn.execute("SELECT * FROM transport_pricing_policies ORDER BY is_active DESC, updated_at DESC, policy_id DESC LIMIT 100").fetchall()
            return jsonify({"data": [_policy(row) for row in rows]})
        origin, destination, vehicle, trip_class, fils = _transport_payload(_object())
        conflict = conn.execute("""SELECT policy_id FROM transport_pricing_policies WHERE is_active=1 AND from_city=? AND to_city=? AND vehicle_type=? AND trip_class=?""", (origin, destination, vehicle, trip_class)).fetchone()
        if conflict:
            raise PricingError("active_policy_conflict", "An active policy already exists for this route and configuration.", 409)
        cursor = conn.execute("""INSERT INTO transport_pricing_policies (from_city,to_city,vehicle_type,trip_class,base_trip_price_fils,created_by_user_id) VALUES (?,?,?,?,?,?)""", (origin, destination, vehicle, trip_class, fils, session["user_id"]))
        conn.execute("INSERT INTO activity_logs(user_id,action_type,details_json) VALUES (?, 'admin_action', ?)", (session["user_id"], '{"pricing":"transport_policy_created"}'))
        conn.commit()
        return jsonify({"data": _policy(conn.execute("SELECT * FROM transport_pricing_policies WHERE policy_id=?", (cursor.lastrowid,)).fetchone())}), 201
    except PricingError as error:
        conn.rollback()
        return _error(error)
    finally:
        conn.close()


@pricing_bp.route("/api/admin/pricing/transport-policies/<int:policy_id>", methods=["PATCH"])
@super_admin_required
def update_transport_policy(policy_id):
    try:
        data = _object()
        if set(data) - {"is_active", "base_trip_price_jod"} or not data:
            raise PricingError("invalid_fields", "Only active state or base price may be updated.")
        conn = get_db_connection()
        try:
            row = conn.execute("SELECT * FROM transport_pricing_policies WHERE policy_id=?", (policy_id,)).fetchone()
            if not row:
                raise PricingError("not_found", "Pricing policy was not found.", 404)
            if "is_active" in data:
                if not isinstance(data["is_active"], bool):
                    raise PricingError("invalid_field", "is_active must be boolean.")
                if data["is_active"]:
                    conflict = conn.execute("SELECT policy_id FROM transport_pricing_policies WHERE policy_id<>? AND is_active=1 AND from_city=? AND to_city=? AND vehicle_type=? AND trip_class=?", (policy_id, row["from_city"], row["to_city"], row["vehicle_type"], row["trip_class"])).fetchone()
                    if conflict:
                        raise PricingError("active_policy_conflict", "Deactivate the conflicting active policy first.", 409)
                conn.execute("UPDATE transport_pricing_policies SET is_active=?,updated_at=datetime('now') WHERE policy_id=?", (int(data["is_active"]), policy_id))
            if "base_trip_price_jod" in data:
                conn.execute("UPDATE transport_pricing_policies SET base_trip_price_fils=?,updated_at=datetime('now') WHERE policy_id=?", (money_to_fils(data["base_trip_price_jod"], "base_trip_price_jod"), policy_id))
            conn.commit()
            return jsonify({"data": _policy(conn.execute("SELECT * FROM transport_pricing_policies WHERE policy_id=?", (policy_id,)).fetchone())})
        finally:
            conn.close()
    except PricingError as error:
        return _error(error)


def _catalog_row(row):
    value = dict(row)
    for key in ("unit_price_fils", "minimum_price_fils", "maximum_price_fils", "service_fee_fils"):
        value[key.replace("_fils", "_jod")] = fils_to_jod(value[key])
    value["quantity_enabled"] = bool(value["quantity_enabled"])
    value["is_active"] = bool(value["is_active"])
    return value


def _catalog_payload(data):
    required = {"service_key", "name_en", "name_ar", "pricing_type"}
    if not required.issubset(data) or not all(isinstance(data[key], str) and data[key].strip() for key in required):
        raise PricingError("missing_fields", "Service key, bilingual names, and pricing type are required.")
    if data["pricing_type"] not in {"fixed", "range"}:
        raise PricingError("invalid_pricing_type", "Pricing type must be fixed or range.")
    fee = money_to_fils(data.get("service_fee_jod", 0), "service_fee_jod", allow_zero=True)
    if data["pricing_type"] == "fixed":
        unit = money_to_fils(data.get("unit_price_jod"), "unit_price_jod")
        return data["service_key"].strip(), data["name_en"].strip(), data["name_ar"].strip(), "fixed", unit, None, None, fee, int(bool(data.get("quantity_enabled", True)))
    minimum, maximum = money_to_fils(data.get("minimum_price_jod"), "minimum_price_jod"), money_to_fils(data.get("maximum_price_jod"), "maximum_price_jod")
    if minimum > maximum:
        raise PricingError("invalid_range", "Minimum price cannot exceed maximum price.")
    return data["service_key"].strip(), data["name_en"].strip(), data["name_ar"].strip(), "range", None, minimum, maximum, fee, int(bool(data.get("quantity_enabled", True)))


@pricing_bp.route("/api/admin/pricing/maintenance-services", methods=["GET", "POST"])
@super_admin_required
def maintenance_services_admin():
    conn = get_db_connection()
    try:
        if request.method == "GET":
            return jsonify({"data": [_catalog_row(row) for row in conn.execute("SELECT * FROM maintenance_service_catalog ORDER BY is_active DESC, service_key, service_id DESC LIMIT 100").fetchall()]})
        values = _catalog_payload(_object())
        conflict = conn.execute("SELECT service_id FROM maintenance_service_catalog WHERE service_key=? AND is_active=1", (values[0],)).fetchone()
        if conflict:
            raise PricingError("active_service_conflict", "An active service with this key already exists.", 409)
        cursor = conn.execute("""INSERT INTO maintenance_service_catalog(service_key,name_en,name_ar,pricing_type,unit_price_fils,minimum_price_fils,maximum_price_fils,service_fee_fils,quantity_enabled,created_by_user_id) VALUES (?,?,?,?,?,?,?,?,?,?)""", (*values, session["user_id"]))
        conn.commit()
        return jsonify({"data": _catalog_row(conn.execute("SELECT * FROM maintenance_service_catalog WHERE service_id=?", (cursor.lastrowid,)).fetchone())}), 201
    except PricingError as error:
        conn.rollback()
        return _error(error)
    finally:
        conn.close()


@pricing_bp.route("/api/admin/pricing/maintenance-services/<int:service_id>", methods=["PATCH"])
@super_admin_required
def maintenance_service_update(service_id):
    try:
        data = _object()
        allowed = {"is_active", "name_en", "name_ar", "pricing_type", "unit_price_jod", "minimum_price_jod", "maximum_price_jod", "service_fee_jod", "quantity_enabled"}
        if not data or set(data) - allowed:
            raise PricingError("invalid_fields", "Only catalog display, pricing, quantity, or active state may be updated.")
        conn = get_db_connection()
        try:
            row = conn.execute("SELECT * FROM maintenance_service_catalog WHERE service_id=?", (service_id,)).fetchone()
            if not row:
                raise PricingError("not_found", "Maintenance service was not found.", 404)
            if "is_active" in data and not isinstance(data["is_active"], bool):
                raise PricingError("invalid_field", "is_active must be boolean.")
            if "quantity_enabled" in data and not isinstance(data["quantity_enabled"], bool):
                raise PricingError("invalid_field", "quantity_enabled must be boolean.")
            updates, params = [], []
            if set(data) - {"is_active"}:
                merged = {
                    "service_key": row["service_key"], "name_en": row["name_en"], "name_ar": row["name_ar"],
                    "pricing_type": row["pricing_type"], "unit_price_jod": fils_to_jod(row["unit_price_fils"]),
                    "minimum_price_jod": fils_to_jod(row["minimum_price_fils"]), "maximum_price_jod": fils_to_jod(row["maximum_price_fils"]),
                    "service_fee_jod": fils_to_jod(row["service_fee_fils"]), "quantity_enabled": bool(row["quantity_enabled"]),
                }
                merged.update({key: value for key, value in data.items() if key != "is_active"})
                values = _catalog_payload(merged)
                updates.extend(["name_en=?", "name_ar=?", "pricing_type=?", "unit_price_fils=?", "minimum_price_fils=?", "maximum_price_fils=?", "service_fee_fils=?", "quantity_enabled=?"])
                params.extend(values[1:])
            if "is_active" in data:
                updates.append("is_active=?")
                params.append(int(data["is_active"]))
            conn.execute("UPDATE maintenance_service_catalog SET " + ", ".join(updates) + ", updated_at=datetime('now') WHERE service_id=?", (*params, service_id))
            conn.commit()
            return jsonify({"data": _catalog_row(conn.execute("SELECT * FROM maintenance_service_catalog WHERE service_id=?", (service_id,)).fetchone())})
        finally:
            conn.close()
    except PricingError as error:
        return _error(error)


@pricing_bp.route("/api/maintenance/catalog")
@customer_required
def maintenance_catalog():
    conn = get_db_connection()
    try:
        rows = conn.execute("SELECT * FROM maintenance_service_catalog WHERE is_active=1 ORDER BY service_key, service_id LIMIT 100").fetchall()
        return jsonify({"data": [_catalog_row(row) for row in rows]})
    finally:
        conn.close()


@pricing_bp.route("/api/maintenance/quote", methods=["POST"])
@customer_required
def maintenance_quote():
    try:
        data = _object()
        service_id, quantity = data.get("catalog_service_id"), _positive_int(data.get("quantity", 1))
        if isinstance(service_id, bool) or not isinstance(service_id, int) or service_id <= 0:
            raise PricingError("invalid_service", "A catalog service is required.")
        conn = get_db_connection()
        try:
            service = conn.execute("SELECT * FROM maintenance_service_catalog WHERE service_id=? AND is_active=1", (service_id,)).fetchone()
            if not service:
                raise PricingError("service_unavailable", "This service is no longer available.", 409)
            if not service["quantity_enabled"] and quantity != 1:
                raise PricingError("invalid_quantity", "This service does not support multiple units.")
            quote = MaintenancePricingService.quote(service, quantity)
            return jsonify({"data": {
                "catalog_service_id": service_id,
                "service_key": service["service_key"],
                "name_en": service["name_en"],
                "name_ar": service["name_ar"],
                "pricing_type": service["pricing_type"],
                "quantity": quantity,
                "quantity_enabled": bool(service["quantity_enabled"]),
                "unit_price_jod": fils_to_jod(service["unit_price_fils"]),
                "minimum_price_jod": fils_to_jod(service["minimum_price_fils"]),
                "maximum_price_jod": fils_to_jod(service["maximum_price_fils"]),
                "service_fee_jod": fils_to_jod(service["service_fee_fils"]),
                **quote,
            }})
        finally:
            conn.close()
    except PricingError as error:
        return _error(error)
