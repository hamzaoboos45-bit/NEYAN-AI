"""
backend/security/csrf.py — Cross-Site Request Forgery protection.

Design (no new dependency — stdlib only):
    - Every session gets one random token, stored server-side in the
      Flask session (signed + httponly cookie already, see app.py).
    - Server-rendered forms embed it as a hidden <input>.
    - AJAX calls (fetch) send it back as an 'X-CSRFToken' header —
      frontend/static/js/csrf.js attaches this automatically to every
      non-GET request, so existing fetch() calls in chat.js/voice.js/
      admin.js did not need to be touched individually.
    - A single app.before_request hook validates state-changing
      requests (POST/PUT/PATCH/DELETE) before any view code runs.

Safe by default: every mutating request is protected unless its
endpoint is explicitly exempted (kept to an absolute minimum).
"""

import hmac
import secrets

from flask import jsonify, request, session

SESSION_KEY = "_csrf_token"
FORM_FIELD = "csrf_token"
HEADER_NAME = "X-CSRFToken"

# Endpoints that legitimately cannot carry a CSRF token (none right now —
# kept as an explicit, auditable allow-list rather than a broad bypass).
EXEMPT_ENDPOINTS = set()


def generate_csrf_token() -> str:
    """Return this session's CSRF token, creating one on first use."""
    token = session.get(SESSION_KEY)
    if not token:
        token = secrets.token_hex(32)
        session[SESSION_KEY] = token
    return token


def _submitted_token() -> str:
    if request.is_json:
        body = request.get_json(silent=True) or {}
        if body.get(FORM_FIELD):
            return body.get(FORM_FIELD)
    return (
        request.form.get(FORM_FIELD)
        or request.headers.get(HEADER_NAME)
        or ""
    )


def validate_csrf() -> bool:
    expected = session.get(SESSION_KEY)
    if not expected:
        return False
    submitted = _submitted_token()
    if not submitted:
        return False
    return hmac.compare_digest(expected, submitted)


def init_csrf(app):
    """Register the Jinja global + the before_request guard."""

    app.jinja_env.globals["csrf_token"] = generate_csrf_token

    @app.before_request
    def _csrf_protect():
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return None
        if request.endpoint in EXEMPT_ENDPOINTS:
            return None
        if not validate_csrf():
            if request.path.startswith("/api/"):
                return jsonify({"error": "Invalid or missing security token. Please refresh and try again."}), 400
            from flask import flash, redirect, url_for
            flash("Your session security token expired. Please try again.", "error")
            return redirect(request.referrer or url_for("auth.login_page"))
        return None
