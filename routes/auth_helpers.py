"""
routes/auth_helpers.py — Authentication + Role-Based Access Control.

Phase One roles (three, completely separate permissions):

    super_admin    — platform owner. Sees/manages everything.
    company_admin  — manages only their own company's trips,
                     bookings, maintenance requests, and analytics.
    customer       — books trips, chats with the assistant, files
                     maintenance requests, views their own history.

Storage note: the `users` table itself is untouched (no schema
change — see database/init_db.py). We deliberately reuse the two
existing DB role values ('admin' / 'user') plus the existing
company_id column to derive the three-way split:

    DB role='admin', company_id IS NULL      → super_admin
    DB role='admin', company_id IS NOT NULL  → company_admin
    DB role='user'                           → customer

`effective_role()` is the single place that mapping happens, so every
decorator, template, and API response agrees on the same three names.
"""

from functools import wraps

from flask import flash, jsonify, redirect, request, session, url_for


# ─────────────────────────────────────────────────────────────────────────────
# Role mapping
# ─────────────────────────────────────────────────────────────────────────────

def effective_role(db_role: str, company_id) -> str:
    """Map the raw DB (role, company_id) pair to one of the three Phase One roles."""
    if db_role == "admin":
        return "company_admin" if company_id is not None else "super_admin"
    return "customer"


def current_user():
    if "user_id" not in session:
        return None
    return {
        "user_id": session.get("user_id"),
        "name": session.get("user_name"),
        "role": session.get("role"),
        "company_id": session.get("company_id"),
    }


def current_company_id():
    """Company scope for the logged-in user. None means 'no company scope'
    (either not logged in, a customer, or a super_admin who can see all)."""
    return session.get("company_id")


def is_super_admin() -> bool:
    return session.get("role") == "super_admin"


def is_company_admin() -> bool:
    return session.get("role") == "company_admin"


def is_customer() -> bool:
    return session.get("role") == "customer"


# ─────────────────────────────────────────────────────────────────────────────
# Decorators
# ─────────────────────────────────────────────────────────────────────────────

def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required"}), 401
            flash("Please login to continue.", "warning")
            return redirect(url_for("auth.login_page"))
        return view(*args, **kwargs)

    return wrapped_view


def roles_required(*roles):
    """Generic decorator — grants access only to the listed effective roles.
    Every specific decorator below (super_admin_required, etc.) is just a
    thin, named wrapper around this one, so permission logic is never
    duplicated across the codebase."""

    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if "user_id" not in session:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Authentication required"}), 401
                flash("Please login to continue.", "warning")
                return redirect(url_for("auth.login_page"))

            if session.get("role") not in roles:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "You are not allowed to access this resource"}), 403
                flash("You are not allowed to access that page.", "error")
                return redirect(url_for("auth.root"))

            return view(*args, **kwargs)

        return wrapped_view

    return decorator


# Named roles — use these in routes instead of roles_required(...) directly,
# so the permission a route requires is obvious at a glance.
super_admin_required = roles_required("super_admin")
company_admin_required = roles_required("company_admin", "super_admin")
customer_required = roles_required("customer")

# Backward-compatible alias: earlier Version 3 code used @admin_required to
# mean "either kind of admin". Kept so nothing that already imports it breaks.
admin_required = roles_required("super_admin", "company_admin")
