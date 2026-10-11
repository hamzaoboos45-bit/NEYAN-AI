from flask import Blueprint, request, jsonify, render_template, session
from database.db import get_db_connection
from routes.auth_helpers import company_admin_required, current_company_id, customer_required, login_required
from backend.notifications.service import NotificationService
from backend.maintenance.service import MaintenanceRequestError, MaintenanceRequestService
from backend.pricing.service import fils_to_jod
import config

maintenance_bp = Blueprint("maintenance", __name__)

VALID_REQUEST_STATUSES = {"pending", "assigned", "in_progress", "completed", "cancelled"}


@maintenance_bp.route("/maintenance")
@customer_required
def maintenance_page():
    return render_template("maintenance.html")


@maintenance_bp.route("/api/maintenance/services")
@login_required
def list_services():
    return jsonify(config.MAINTENANCE_SERVICES)


@maintenance_bp.route("/api/maintenance/requests", methods=["GET"])
@login_required
def list_requests():
    """
    Scoped by role (RBAC):
        customer      — only their own maintenance requests
        company_admin — only requests assigned to their own company
        super_admin   — every request on the platform
    """
    role = session.get("role")

    conn = get_db_connection()
    try:
        query = """
            SELECT r.request_id, r.service_type, r.service_details,
                   r.location, r.preferred_date, r.status, r.created_at,
                   r.customer_name, r.customer_phone,
                   c.name_ar AS company_name, r.catalog_service_id,
                   r.service_name_en_snapshot, r.service_name_ar_snapshot,
                   r.pricing_type_snapshot, r.quantity,
                   r.unit_price_fils_snapshot, r.service_fee_fils_snapshot,
                   r.total_minimum_fils_snapshot, r.total_maximum_fils_snapshot
            FROM maintenance_requests r
            LEFT JOIN companies c ON r.company_id = c.company_id
            WHERE 1 = 1
        """
        params = []
        if role == "customer":
            query += " AND r.user_id = ?"
            params.append(session["user_id"])
        elif role == "company_admin":
            query += " AND r.company_id = ?"
            params.append(current_company_id())
        # super_admin: no extra filter — sees everything

        query += " ORDER BY r.created_at DESC, r.request_id DESC LIMIT 50"

        rows = conn.execute(query, params).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            snapshot_jod_fields = {
                "unit_price_fils_snapshot": "unit_price_jod",
                "service_fee_fils_snapshot": "service_fee_jod",
                "total_minimum_fils_snapshot": "total_minimum_jod",
                "total_maximum_fils_snapshot": "total_maximum_jod",
            }
            for source, target in snapshot_jod_fields.items():
                item[target] = fils_to_jod(item[source])
            if item["pricing_type_snapshot"] == "fixed":
                item["price_semantics"] = "fixed_request_snapshot"
            elif item["pricing_type_snapshot"] == "range":
                item["price_semantics"] = "estimated_range_request_snapshot"
            else:
                item["price_semantics"] = "inspection_required"
            result.append(item)
        return jsonify(result)
    finally:
        conn.close()


@maintenance_bp.route("/api/maintenance/requests", methods=["POST"])
@customer_required
def create_request():
    try:
        created = MaintenanceRequestService.create(session["user_id"], request.get_json(silent=True))
        return jsonify(created), 201
    except MaintenanceRequestError as error:
        return jsonify({"error": error.message, "code": error.code}), error.status


@maintenance_bp.route("/api/maintenance/requests/<int:request_id>/status", methods=["PATCH"])
@company_admin_required
def update_request_status(request_id):
    """
    RBAC — 'Companies: manage only their own maintenance'. A company_admin
    may only update requests assigned to their own company; super_admin
    may update any request.
    """
    data = request.get_json(silent=True) or {}
    new_status = data.get("status")

    if new_status not in VALID_REQUEST_STATUSES:
        return jsonify({"error": "Invalid status value."}), 400

    conn = get_db_connection()
    try:
        req = conn.execute(
            "SELECT request_id, user_id, company_id, status FROM maintenance_requests WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        if not req:
            return jsonify({"error": "Request not found."}), 404
        if session.get("role") == "company_admin" and req["company_id"] != current_company_id():
            return jsonify({"error": "You are not allowed to manage this request."}), 403

        conn.execute(
            "UPDATE maintenance_requests SET status = ?, updated_at = datetime('now') WHERE request_id = ?",
            (new_status, request_id),
        )
        if new_status != req["status"] and req["user_id"] is not None:
            NotificationService.create(
                conn, recipient_user_id=req["user_id"], event_type="maintenance_status_changed",
                source_type="maintenance_request", source_id=request_id,
                metadata={"status": new_status}, action_target="/maintenance",
                transition_key=new_status,
            )
        conn.commit()
        return jsonify({"status": "updated"})
    finally:
        conn.close()
