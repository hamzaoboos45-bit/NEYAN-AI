"""Step 4 role-scoped administrative APIs for forming-trip demand only."""

from flask import Blueprint, jsonify, request, session

from backend.transportation.trip_request_service import TripRequestError, TripRequestService
from routes.auth_helpers import company_admin_required, current_company_id, super_admin_required


demand_admin_bp = Blueprint("demand_admin", __name__)


def _error(error):
    payload = {"error": {"code": error.code, "message": error.message}}
    if error.details:
        payload["error"]["details"] = error.details
    return jsonify(payload), error.status


def _call(operation, status=200):
    try:
        return jsonify({"data": operation()}), status
    except TripRequestError as error:
        return _error(error)


def _company_id(data):
    if not isinstance(data, dict) or set(data) != {"company_id"}:
        raise TripRequestError("invalid_assignment_payload", "Only company_id is accepted for assignment.")
    value = data["company_id"]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TripRequestError("invalid_company", "company_id must be a positive integer.")
    return value


def _empty_decision_payload(data):
    if data not in ({}, None):
        raise TripRequestError("invalid_decision_payload", "Company decisions do not accept client selectors.")


def _authenticated_company_scope():
    """Require a real company-admin session; never infer scope from input."""
    company_id = current_company_id()
    if session.get("role") != "company_admin" or company_id is None:
        raise TripRequestError("company_scope_required", "Company dashboard access is required.", 403)
    return company_id


@demand_admin_bp.route("/api/admin/trip-requests")
@super_admin_required
def admin_trip_request_queue():
    return _call(TripRequestService.admin_queue)


@demand_admin_bp.route("/api/admin/transport-companies")
@super_admin_required
def admin_transport_companies():
    return _call(TripRequestService.active_transport_companies)


@demand_admin_bp.route("/api/admin/trip-requests/<int:request_id>/assign", methods=["POST"])
@super_admin_required
def assign_trip_request(request_id):
    def operation():
        return TripRequestService.assign(session["user_id"], request_id, _company_id(request.get_json(silent=True)))
    return _call(operation)


@demand_admin_bp.route("/api/company/trip-requests")
@company_admin_required
def company_trip_request_queue():
    return _call(lambda: TripRequestService.company_queue(_authenticated_company_scope()))


@demand_admin_bp.route("/api/company/trip-requests/<int:request_id>/accept", methods=["POST"])
@company_admin_required
def accept_trip_request(request_id):
    def operation():
        _empty_decision_payload(request.get_json(silent=True))
        return TripRequestService.company_decide(session["user_id"], _authenticated_company_scope(), request_id, "accepted")
    return _call(operation)


@demand_admin_bp.route("/api/company/trip-requests/<int:request_id>/reject", methods=["POST"])
@company_admin_required
def reject_trip_request(request_id):
    def operation():
        _empty_decision_payload(request.get_json(silent=True))
        return TripRequestService.company_decide(session["user_id"], _authenticated_company_scope(), request_id, "rejected")
    return _call(operation)


@demand_admin_bp.route("/api/company/trip-requests/<int:request_id>/convert", methods=["POST"])
@company_admin_required
def convert_trip_request(request_id):
    def operation():
        return TripRequestService.convert(session["user_id"], _authenticated_company_scope(), request_id, request.get_json(silent=True))
    return _call(operation)
