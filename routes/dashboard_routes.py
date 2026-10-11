"""Phase 8 dashboard APIs. Existing analytics routes remain backward compatible."""

from flask import Blueprint, current_app, jsonify, request

from backend.dashboard.contracts import DashboardValidationError, parse_date_range, parse_pagination
from backend.dashboard.control_center import AdminControlCenterRepository
from backend.dashboard.scope import DashboardScopeError, reject_client_identity_selectors, resolve_dashboard_scope
from backend.dashboard.service import DashboardService
from routes.auth_helpers import login_required, super_admin_required


dashboard_bp = Blueprint("dashboard", __name__)
@dashboard_bp.route("/api/dashboard/overview")
@login_required
def dashboard_overview():
    """Return minimal real KPIs scoped solely from server-side authenticated identity."""
    try:
        reject_client_identity_selectors(request.args)
        scope = resolve_dashboard_scope()
        date_range = parse_date_range(request.args)
        return jsonify(DashboardService().overview(scope, date_range))
    except DashboardValidationError as exc:
        return jsonify({"error": {"code": "invalid_query", "message": str(exc)}}), 400
    except DashboardScopeError as exc:
        return jsonify({"error": {"code": "scope_unavailable", "message": str(exc)}}), 403
    except Exception:
        current_app.logger.exception("Dashboard overview failed")
        return jsonify({"error": {"code": "dashboard_unavailable", "message": "Dashboard data is unavailable."}}), 500


@dashboard_bp.route("/api/dashboard/home")
@login_required
def customer_home_dashboard():
    """One bounded, authenticated-customer payload for the Step 2 home page."""
    try:
        reject_client_identity_selectors(request.args)
        scope = resolve_dashboard_scope()
        if scope.kind != "user":
            return jsonify({"error": {"code": "customer_dashboard_only", "message": "Customer dashboard access is required."}}), 403
        return jsonify(DashboardService().user_home(scope))
    except DashboardValidationError as exc:
        return jsonify({"error": {"code": "invalid_query", "message": str(exc)}}), 400
    except DashboardScopeError as exc:
        return jsonify({"error": {"code": "scope_unavailable", "message": str(exc)}}), 403
    except Exception:
        current_app.logger.exception("Customer home dashboard failed")
        return jsonify({"error": {"code": "dashboard_unavailable", "message": "Dashboard data is unavailable."}}), 500


@dashboard_bp.route("/api/dashboard/admin")
@login_required
def admin_dashboard_data():
    try:
        reject_client_identity_selectors(request.args)
        scope = resolve_dashboard_scope()
        if scope.kind not in {"platform", "company"}:
            return jsonify({"error": {"code": "admin_dashboard_only", "message": "Admin dashboard access is required."}}), 403
        return jsonify(DashboardService().admin(scope, parse_date_range(request.args)))
    except DashboardValidationError as exc:
        return jsonify({"error": {"code": "invalid_query", "message": str(exc)}}), 400
    except DashboardScopeError as exc:
        return jsonify({"error": {"code": "scope_unavailable", "message": str(exc)}}), 403
    except Exception:
        current_app.logger.exception("Admin dashboard failed")
        return jsonify({"error": {"code": "dashboard_unavailable", "message": "Dashboard data is unavailable."}}), 500


@dashboard_bp.route("/api/admin/control-center/overview")
@super_admin_required
def control_center_overview():
    """Platform-only aggregated facts for the initial Control Center tab."""
    try:
        reject_client_identity_selectors(request.args)
        return jsonify({"data": AdminControlCenterRepository().overview(parse_date_range(request.args))})
    except DashboardValidationError as exc:
        return jsonify({"error": {"code": "invalid_query", "message": str(exc)}}), 400
    except Exception:
        current_app.logger.exception("Control Center overview failed")
        return jsonify({"error": {"code": "control_center_unavailable", "message": "Admin overview data is unavailable."}}), 500


@dashboard_bp.route("/api/admin/control-center/<string:section>")
@super_admin_required
def control_center_section(section):
    """Lazy, bounded section data. Never accepts a client-controlled scope."""
    try:
        reject_client_identity_selectors(request.args)
        if section not in {"users", "companies", "operations", "activity"}:
            return jsonify({"error": {"code": "unknown_section", "message": "Unknown admin section."}}), 404
        search = (request.args.get("search") or "").strip()
        status = (request.args.get("status") or "").strip()
        role = (request.args.get("filter_role") or "").strip()
        company_type = (request.args.get("filter_company_type") or "").strip()
        company_value = (request.args.get("filter_company_id") or "").strip()
        if company_value and (not company_value.isdecimal() or int(company_value) <= 0):
            raise DashboardValidationError("filter_company_id must be a positive integer.")
        return jsonify({"data": AdminControlCenterRepository().section(
            section,
            parse_pagination(request.args),
            search,
            status,
            role,
            int(company_value) if company_value else None,
            company_type,
        )})
    except DashboardValidationError as exc:
        return jsonify({"error": {"code": "invalid_query", "message": str(exc)}}), 400
    except ValueError as exc:
        return jsonify({"error": {"code": "invalid_section", "message": str(exc)}}), 400
    except Exception:
        current_app.logger.exception("Control Center section failed")
        return jsonify({"error": {"code": "control_center_unavailable", "message": "Admin section data is unavailable."}}), 500
