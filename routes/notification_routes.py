"""Recipient-scoped notification APIs and optional history page."""

from flask import Blueprint, jsonify, request, render_template, session

from backend.notifications.service import NotificationService, MAX_PAGE_SIZE
from database.db import get_db_connection
from routes.auth_helpers import login_required


notification_bp = Blueprint("notification", __name__)


def _page_value(name: str, default: int) -> int:
    raw = request.args.get(name, str(default))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value


@notification_bp.route("/notifications")
@login_required
def notification_page():
    return render_template("notifications.html")


@notification_bp.route("/api/notifications")
@login_required
def list_notifications():
    limit = _page_value("limit", 20)
    offset = _page_value("offset", 0)
    if limit < 1 or offset < 0:
        return jsonify({"error": "limit and offset must be non-negative bounded integers."}), 400
    conn = get_db_connection()
    try:
        items = NotificationService.list_for_user(conn, session["user_id"], limit=min(limit, MAX_PAGE_SIZE), offset=offset)
        return jsonify({"data": items, "limit": min(limit, MAX_PAGE_SIZE), "offset": offset})
    finally:
        conn.close()


@notification_bp.route("/api/notifications/unread-count")
@login_required
def unread_notification_count():
    conn = get_db_connection()
    try:
        return jsonify({"unread_count": NotificationService.unread_count(conn, session["user_id"])})
    finally:
        conn.close()


@notification_bp.route("/api/notifications/<int:notification_id>/read", methods=["POST"])
@login_required
def mark_notification_read(notification_id: int):
    conn = get_db_connection()
    try:
        if not NotificationService.mark_read(conn, session["user_id"], notification_id):
            return jsonify({"error": "Notification not found."}), 404
        conn.commit()
        return jsonify({"status": "read"})
    finally:
        conn.close()


@notification_bp.route("/api/notifications/mark-all-read", methods=["POST"])
@login_required
def mark_all_notifications_read():
    conn = get_db_connection()
    try:
        updated = NotificationService.mark_all_read(conn, session["user_id"])
        conn.commit()
        return jsonify({"status": "read", "updated": updated})
    finally:
        conn.close()
