"""PII-minimized customer API for Phase 5 forming-trip demand."""

from flask import Blueprint, jsonify, request, session

from backend.transportation.trip_request_service import TripRequestError, TripRequestService
from routes.auth_helpers import customer_required


trip_request_bp = Blueprint("trip_request", __name__)


def _error(error: TripRequestError):
    body = {"error": {"code": error.code, "message": error.message}}
    if error.details:
        body["error"]["details"] = error.details
    return jsonify(body), error.status


def _call(operation, success=200):
    try:
        return jsonify({"data": operation()}), success
    except TripRequestError as error:
        return _error(error)


@trip_request_bp.route("/api/trip-requests", methods=["GET"])
@customer_required
def browse_trip_requests():
    return _call(lambda: TripRequestService.browse(session["user_id"]))


@trip_request_bp.route("/api/trip-requests/compatible", methods=["GET"])
@customer_required
def compatible_trip_requests():
    query = {
        "from_city": request.args.get("from_city", request.args.get("from", "")),
        "to_city": request.args.get("to_city", request.args.get("to", "")),
        "requested_date": request.args.get("requested_date", request.args.get("date", "")),
        "requested_time_start": request.args.get("requested_time_start", request.args.get("time_start", "")),
        "requested_time_end": request.args.get("requested_time_end", request.args.get("time_end", "")),
        "desired_vehicle_type": request.args.get("desired_vehicle_type", request.args.get("vehicle", "")),
        "desired_trip_class": request.args.get("desired_trip_class", request.args.get("class", "")),
    }
    return _call(lambda: TripRequestService.compatible(session["user_id"], query))


@trip_request_bp.route("/api/trip-requests/mine", methods=["GET"])
@customer_required
def my_trip_requests():
    return _call(lambda: TripRequestService.mine(session["user_id"]))


@trip_request_bp.route("/api/trip-requests", methods=["POST"])
@customer_required
def create_trip_request():
    return _call(lambda: TripRequestService.create(session["user_id"], request.get_json(silent=True)), 201)


@trip_request_bp.route("/api/trip-requests/<int:request_id>/join", methods=["POST"])
@customer_required
def join_trip_request(request_id):
    return _call(lambda: TripRequestService.join(session["user_id"], request_id, request.get_json(silent=True)))


@trip_request_bp.route("/api/trip-requests/<int:request_id>/leave", methods=["POST"])
@customer_required
def leave_trip_request(request_id):
    return _call(lambda: TripRequestService.leave(session["user_id"], request_id))


@trip_request_bp.route("/api/trip-requests/<int:request_id>/cancel", methods=["POST"])
@customer_required
def cancel_trip_request(request_id):
    return _call(lambda: TripRequestService.cancel(session["user_id"], request_id))
