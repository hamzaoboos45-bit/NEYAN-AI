import sqlite3

import bcrypt
from flask import Blueprint, current_app, flash, make_response, redirect, render_template, request, session, url_for

import config
from backend.email import email_service
from backend.security import brute_force, password_reset, remember_me, reset_rate_limit
from backend.security.credentials import EMAIL_RE, PASSWORD_RE, hash_password
from database.db import get_db_connection
from routes.auth_helpers import (
    current_user,
    effective_role,
    login_required,
    super_admin_required,
)

auth_bp = Blueprint("auth", __name__)

def _normalize_email(email):
    return (email or "").strip().lower()


def _hash_password(password):
    return hash_password(password)


def _check_password(password, password_hash):
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def _display_name(row):
    return row["name"] or row["full_name"]


def _client_ip():
    # Forwarded client addresses are trusted only when the deployment has
    # explicitly configured one or more trusted reverse proxies. ProxyFix
    # then normalizes remote_addr before this function runs.
    if config.TRUSTED_PROXY_COUNT <= 0:
        return request.remote_addr or ""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or ""


def _create_session(user):
    session.clear()
    session.permanent = True
    session["user_id"] = user["user_id"]
    session["user_name"] = _display_name(user)
    session["role"] = effective_role(user["role"], user["company_id"])
    session["company_id"] = user["company_id"]


def _log_activity(user_id, action_type, details="{}"):
    conn = get_db_connection()
    try:
        conn.execute(
            """
            INSERT INTO activity_logs (user_id, action_type, details_json, ip_address)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, action_type, details, _client_ip()),
        )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()


def _fetch_user_row(conn, user_id):
    return conn.execute(
        """
        SELECT user_id, full_name, name, email, password_hash, role, status, is_active, company_id
        FROM users
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()


def _set_remember_cookie(response, user_id):
    cookie_value = remember_me.issue_token(user_id)
    response.set_cookie(
        remember_me.COOKIE_NAME,
        cookie_value,
        max_age=remember_me.COOKIE_MAX_AGE_DAYS * 24 * 60 * 60,
        httponly=True,
        samesite="Lax",
        secure=current_app.config["SESSION_COOKIE_SECURE"],
    )


def _clear_remember_cookie(response):
    response.delete_cookie(remember_me.COOKIE_NAME)


# ─────────────────────────────────────────────────────────────────────────────
# Session bootstrap — restore a session from a "remember me" cookie
# ─────────────────────────────────────────────────────────────────────────────

def load_logged_in_user_from_remember_cookie():
    """Registered as an app.before_request hook in app.py. If there's no
    active session but a valid remember-me cookie is present, silently
    re-establish the session (and rotate the token)."""
    if "user_id" in session:
        return
    cookie_value = request.cookies.get(remember_me.COOKIE_NAME)
    if not cookie_value:
        return

    user_id = remember_me.consume_token(cookie_value)
    if not user_id:
        return

    conn = get_db_connection()
    try:
        user = _fetch_user_row(conn, user_id)
        if not user or int(user["is_active"]) != 1:
            return
        if user["role"] == "admin" and user["status"] != "approved":
            return
        if user["status"] not in ("active", "approved"):
            return
        _create_session(user)
        # Rotation: issue a fresh cookie tied to the new token row.
        session["_pending_remember_rotation"] = True
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Landing / login / register pages
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/")
def root():
    # A post-action redirect can carry a one-time success/error flash (for
    # example, expired-password-reset feedback). Route it directly to the
    # normal destination so the message is not hidden by the cinematic entry.
    # Ordinary fresh entries still receive /intro below.
    if session.get("_flashes"):
        if "user_id" not in session:
            return redirect(url_for("auth.login_page"))
        if session.get("role") in ("super_admin", "company_admin"):
            return redirect(url_for("admin.admin_dashboard"))
        return redirect(url_for("auth.home"))
    return redirect(url_for("auth.intro"))


@auth_bp.route("/intro")
def intro():
    """Brand entry that receives an already server-derived safe destination."""
    if "user_id" not in session:
        destination = url_for("auth.login_page")
    elif session.get("role") in ("super_admin", "company_admin"):
        destination = url_for("admin.admin_dashboard")
    else:
        destination = url_for("auth.home")
    return render_template("intro.html", intro_destination=destination)


@auth_bp.route("/login")
def login_page():
    if "user_id" in session:
        return redirect(url_for("auth.root"))
    return render_template("login.html", auth_mode="login")


@auth_bp.route("/register")
def register_page():
    if "user_id" in session:
        return redirect(url_for("auth.root"))
    return render_template("login.html", auth_mode="register")


@auth_bp.route("/login", methods=["POST"])
def login():
    email = _normalize_email(request.form.get("email"))
    password = request.form.get("password", "")
    remember = request.form.get("remember") == "on" or request.form.get("remember") == "1"
    ip_address = _client_ip()

    if not EMAIL_RE.match(email) or not password:
        flash("Please enter a valid email and password.", "error")
        return redirect(url_for("auth.login_page"))

    locked, reason = brute_force.is_locked(email, ip_address)
    if locked:
        flash(reason, "error")
        return redirect(url_for("auth.login_page"))

    conn = get_db_connection()
    try:
        user = conn.execute(
            """
            SELECT user_id, full_name, name, email, password_hash, role, status, is_active, company_id
            FROM users
            WHERE lower(email) = ?
            """,
            (email,),
        ).fetchone()

        if not user or not _check_password(password, user["password_hash"]):
            brute_force.record_attempt(email, ip_address, success=False)
            flash("Invalid email or password.", "error")
            return redirect(url_for("auth.login_page"))

        if user["role"] == "admin" and user["status"] != "approved":
            flash("Your administrator account is waiting for approval.", "warning")
            return redirect(url_for("auth.login_page"))

        if user["status"] != "active" and user["role"] != "admin":
            flash("This account is not active.", "error")
            return redirect(url_for("auth.login_page"))

        if int(user["is_active"]) != 1:
            flash("This account has been disabled.", "error")
            return redirect(url_for("auth.login_page"))

        brute_force.record_attempt(email, ip_address, success=True)
        brute_force.reset_failures(email)

        conn.execute("UPDATE users SET last_login = datetime('now') WHERE user_id = ?", (user["user_id"],))
        conn.commit()
        _create_session(user)
        _log_activity(user["user_id"], "login")

        target = url_for("admin.admin_dashboard") if session["role"] in ("super_admin", "company_admin") else url_for("auth.home")
        response = make_response(redirect(target))
        if remember:
            _set_remember_cookie(response, user["user_id"])
        return response
    finally:
        conn.close()


@auth_bp.route("/register", methods=["POST"])
def register():
    # Phase 3.1: the public registration form used to let anyone check a
    # box, pick ANY company from a dropdown, and submit a "pending"
    # company_admin request for it — approved later by a super_admin. Per
    # product decision, that self-service path is removed entirely: every
    # admin account (super_admin or company_admin) is now created only by
    # an existing super_admin from the admin dashboard's "+ Add User"
    # modal (routes/auth_routes.py:admin_create_user, RBAC-gated). This
    # route no longer reads or honors any role/company_id fields from the
    # request at all — public registration always creates a plain,
    # immediately-active customer account, regardless of what a client
    # sends. That's enforced here server-side, not just hidden in the UI.
    name = (request.form.get("name") or "").strip()
    email = _normalize_email(request.form.get("email"))
    password = request.form.get("password", "")

    if len(name) < 2:
        flash("Please enter your full name.", "error")
        return redirect(url_for("auth.register_page"))
    if not EMAIL_RE.match(email):
        flash("Please enter a valid email address.", "error")
        return redirect(url_for("auth.register_page"))
    if not PASSWORD_RE.match(password):
        flash("Password must be at least 8 characters and include a letter and a number.", "error")
        return redirect(url_for("auth.register_page"))

    conn = get_db_connection()
    try:
        duplicate = conn.execute("SELECT 1 FROM users WHERE lower(email) = ?", (email,)).fetchone()
        if duplicate:
            flash("An account with this email already exists.", "error")
            return redirect(url_for("auth.register_page"))

        password_hash = _hash_password(password)

        try:
            cursor = conn.execute(
                """
                INSERT INTO users (full_name, name, email, password_hash, role, status, company_id, is_active)
                VALUES (?, ?, ?, ?, 'user', 'active', NULL, 1)
                """,
                (name, name, email, password_hash),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            # Defense in depth (Phase 3): same narrow race window as
            # admin_create_user() below — the duplicate check above and this
            # INSERT aren't atomic. `email` is UNIQUE at the schema level
            # regardless, so this can only mean a concurrent request just
            # took the email. Never leak the raw sqlite3 error to the user.
            conn.rollback()
            flash("An account with this email already exists.", "error")
            return redirect(url_for("auth.register_page"))

        user = _fetch_user_row(conn, cursor.lastrowid)
        _create_session(user)
        _log_activity(user["user_id"], "login")
        return redirect(url_for("auth.home"))
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Forgot / reset password (architecture — see backend/security/password_reset.py)
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/forgot-password", methods=["GET"])
def forgot_password_page():
    if "user_id" in session:
        return redirect(url_for("auth.root"))
    return render_template("forgot_password.html")


@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    email = _normalize_email(request.form.get("email"))
    ip_address = _client_ip()
    dev_reset_link = None  # only ever populated when EMAIL_PROVIDER is unset (see below)

    # Rate limit BEFORE anything else — deliberately the exact same
    # generic response either way, so being rate-limited never tells an
    # attacker anything different from "the request was processed"
    # (see backend/security/reset_rate_limit.py's docstring for why this
    # must not get its own distinct message).
    if EMAIL_RE.match(email) and not reset_rate_limit.is_rate_limited(email, ip_address):
        reset_rate_limit.record_request(email, ip_address)

        conn = get_db_connection()
        try:
            user = conn.execute(
                "SELECT user_id FROM users WHERE lower(email) = ? AND is_active = 1", (email,)
            ).fetchone()
            if user:
                token = password_reset.create_reset_token(user["user_id"])
                if config.APP_BASE_URL:
                    reset_link = f"{config.APP_BASE_URL}{url_for('auth.reset_password_page', token=token)}"
                else:
                    reset_link = url_for("auth.reset_password_page", token=token, _external=True)

                result = email_service.send_password_reset_email(email, reset_link)

                if result.provider == "console" and not config.IS_PRODUCTION:
                    # EMAIL_PROVIDER isn't configured (config.EMAIL_PROVIDER
                    # == "console", the default) — fall back to exactly the
                    # behavior this flow has always had: log it server-side
                    # and show it directly on the page behind the
                    # "Development mode" notice, so the flow stays fully
                    # testable with zero configuration.
                    dev_reset_link = reset_link
                elif result.sent:
                    current_app.logger.info("Password reset email accepted by provider=%s", result.provider)
                else:
                    # A real provider IS configured but the send failed
                    # (bad credentials, provider outage, etc). Per the
                    # brief: never show a fake success to the requester,
                    # but also never reveal anything account-specific to
                    # them either — so the user-facing message below stays
                    # identical to every other case. The actual, safe
                    # (secret-free) diagnostic goes to the server log only,
                    # for whoever is operating the app to notice and fix.
                    current_app.logger.warning(
                        "Password reset email delivery failed: provider=%s configured=%s error=%s",
                        result.provider, email_service.is_configured(), result.error or "unspecified",
                    )
        finally:
            conn.close()

    # Always the same generic message, regardless of: whether the email
    # exists, whether it was rate-limited, or whether delivery actually
    # succeeded — this is what prevents the form from being usable to
    # discover which emails are registered, or to distinguish a delivery
    # failure from "no such account" from "you're doing that too often".
    flash("If an account exists for that email, a password reset link has been generated.", "success")
    return render_template("forgot_password.html", dev_reset_link=dev_reset_link, submitted=True)


@auth_bp.route("/reset-password/<token>", methods=["GET"])
def reset_password_page(token):
    user_id = password_reset.verify_reset_token(token)
    if not user_id:
        flash("This password reset link is invalid or has expired. Please request a new one.", "error")
        return redirect(url_for("auth.forgot_password_page"))
    return render_template("reset_password.html", token=token)


@auth_bp.route("/reset-password/<token>", methods=["POST"])
def reset_password(token):
    user_id = password_reset.verify_reset_token(token)
    if not user_id:
        flash("This password reset link is invalid or has expired. Please request a new one.", "error")
        return redirect(url_for("auth.forgot_password_page"))

    password = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")

    if not PASSWORD_RE.match(password):
        flash("Password must be at least 8 characters and include a letter and a number.", "error")
        return render_template("reset_password.html", token=token)
    if password != confirm:
        flash("Passwords do not match.", "error")
        return render_template("reset_password.html", token=token)

    conn = get_db_connection()
    try:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE user_id = ?",
            (_hash_password(password), user_id),
        )
        conn.commit()
    finally:
        conn.close()

    password_reset.consume_reset_token(token)
    remember_me.revoke_all_for_user(user_id)  # force re-login everywhere else
    _log_activity(user_id, "login", '{"event": "password_reset"}')

    flash("Your password has been reset. Please sign in with your new password.", "success")
    return redirect(url_for("auth.login_page"))


# ─────────────────────────────────────────────────────────────────────────────
# Authenticated pages
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/home")
@login_required
def home():
    if session.get("role") in {"super_admin", "company_admin"}:
        return redirect(url_for("admin.admin_dashboard"))
    return render_template("home.html", active="home")


@auth_bp.route("/profile")
@login_required
def profile():
    conn = get_db_connection()
    try:
        user = conn.execute(
            """
            SELECT u.user_id, u.full_name, u.name, u.email, u.role, u.status,
                   u.company_id, u.created_at, u.last_login,
                   c.name_ar AS company_name
            FROM users u
            LEFT JOIN companies c ON u.company_id = c.company_id
            WHERE u.user_id = ?
            """,
            (session["user_id"],),
        ).fetchone()
        return render_template("profile.html", active="profile", user=user, role=session.get("role"))
    finally:
        conn.close()


@auth_bp.route("/logout")
@login_required
def logout():
    user_id = session.get("user_id")
    cookie_value = request.cookies.get(remember_me.COOKIE_NAME)

    session.clear()
    if user_id:
        _log_activity(user_id, "logout")
    flash("You have been logged out.", "success")

    response = make_response(redirect(url_for("auth.login_page")))
    if cookie_value:
        remember_me.revoke_token(cookie_value)
        _clear_remember_cookie(response)
    return response


# ─────────────────────────────────────────────────────────────────────────────
# Super-admin controlled user management
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/api/admin/pending-admins")
@super_admin_required
def pending_admins():
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT u.user_id, u.name, u.full_name, u.email, u.created_at, u.company_id,
                   c.name_ar AS company_name
            FROM users u
            LEFT JOIN companies c ON u.company_id = c.company_id
            WHERE u.role = 'admin' AND u.status = 'pending'
            ORDER BY u.created_at ASC
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


@auth_bp.route("/api/admin/users")
@super_admin_required
def users_list():
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT u.user_id, u.name, u.full_name, u.email, u.role, u.status,
                   u.company_id, u.is_active, u.created_at, u.last_login,
                   c.name_ar AS company_name
            FROM users u
            LEFT JOIN companies c ON u.company_id = c.company_id
            ORDER BY u.created_at DESC
            """
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["effective_role"] = effective_role(row["role"], row["company_id"])
            result.append(item)
        return result
    finally:
        conn.close()


@auth_bp.route("/api/admin/pending-admins/<int:user_id>/approve", methods=["POST"])
@super_admin_required
def approve_admin(user_id):
    if user_id == session.get("user_id"):
        return {"error": "You cannot approve your own account."}, 400

    conn = get_db_connection()
    try:
        result = conn.execute(
            "UPDATE users SET status = 'approved', is_active = 1 WHERE user_id = ? AND role = 'admin' AND status = 'pending'",
            (user_id,),
        )
        conn.commit()
        if result.rowcount == 0:
            return {"error": "Pending account was not found."}, 404
        _log_activity(session["user_id"], "admin_action", f'{{"approved_admin_id": {user_id}}}')
        return {"status": "approved"}
    finally:
        conn.close()


@auth_bp.route("/api/admin/pending-admins/<int:user_id>/reject", methods=["POST"])
@super_admin_required
def reject_admin(user_id):
    if user_id == session.get("user_id"):
        return {"error": "You cannot reject your own account."}, 400

    conn = get_db_connection()
    try:
        result = conn.execute(
            "UPDATE users SET status = 'rejected', is_active = 0 WHERE user_id = ? AND role = 'admin' AND status = 'pending'",
            (user_id,),
        )
        conn.commit()
        if result.rowcount == 0:
            return {"error": "Pending account was not found."}, 404
        _log_activity(session["user_id"], "admin_action", f'{{"rejected_admin_id": {user_id}}}')
        return {"status": "rejected"}
    finally:
        conn.close()


@auth_bp.route("/api/admin/users/<int:user_id>/toggle-active", methods=["POST"])
@super_admin_required
def toggle_user_active(user_id):
    """Admin-controlled account disable/enable (requirement: no self-lockout)."""
    if user_id == session.get("user_id"):
        return {"error": "You cannot disable your own account."}, 400

    conn = get_db_connection()
    try:
        user = conn.execute("SELECT is_active FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not user:
            return {"error": "User not found."}, 404
        new_state = 0 if int(user["is_active"]) == 1 else 1
        conn.execute("UPDATE users SET is_active = ? WHERE user_id = ?", (new_state, user_id))
        conn.commit()
        if new_state == 0:
            remember_me.revoke_all_for_user(user_id)
        _log_activity(
            session["user_id"], "admin_action",
            f'{{"toggled_active_user_id": {user_id}, "new_state": {new_state}}}',
        )
        return {"status": "disabled" if new_state == 0 else "enabled"}
    finally:
        conn.close()


@auth_bp.route("/api/admin/users", methods=["POST"])
@super_admin_required
def admin_create_user():
    """
    User Registration (Admin controlled): a super_admin can create any
    account directly — customer, company_admin (with a company), or
    another super_admin — fully active, no approval step needed since
    a super_admin is vouching for it.
    """
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = _normalize_email(data.get("email"))
    password = data.get("password") or ""
    role_choice = data.get("role")  # 'customer' | 'company_admin' | 'super_admin'
    company_id = data.get("company_id")

    if len(name) < 2:
        return {"error": "Please provide a full name."}, 400
    if not EMAIL_RE.match(email):
        return {"error": "Please provide a valid email address."}, 400
    if not PASSWORD_RE.match(password):
        return {"error": "Password must be at least 8 characters and include a letter and a number."}, 400
    if role_choice not in ("customer", "company_admin", "super_admin"):
        return {"error": "Invalid role."}, 400
    if role_choice == "company_admin" and not company_id:
        return {"error": "company_id is required for a company_admin account."}, 400

    db_role = "user" if role_choice == "customer" else "admin"

    # Bug fix (Phase 3): company_id arrives as a JSON string and was passed
    # straight into int() with no error handling. Nothing in the UI showed a
    # super_admin which numeric ID belongs to which company (see the Phase 3
    # report), so any non-numeric value here crashed with an unhandled
    # ValueError -> HTTP 500 with no JSON body, which the frontend couldn't
    # even display an error for. Now it's a normal, catchable 400.
    final_company_id = None
    if role_choice == "company_admin" and company_id not in (None, ""):
        try:
            final_company_id = int(company_id)
        except (TypeError, ValueError):
            return {"error": "Invalid company."}, 400

    conn = get_db_connection()
    try:
        if final_company_id is not None:
            valid_company = conn.execute(
                "SELECT 1 FROM companies WHERE company_id = ?", (final_company_id,)
            ).fetchone()
            if not valid_company:
                return {"error": "Company not found."}, 404

        duplicate = conn.execute("SELECT 1 FROM users WHERE lower(email) = ?", (email,)).fetchone()
        if duplicate:
            return {"error": "An account with this email already exists."}, 409

        try:
            cursor = conn.execute(
                """
                INSERT INTO users (full_name, name, email, password_hash, role, status, company_id, is_active)
                VALUES (?, ?, ?, ?, ?, 'approved', ?, 1)
                """,
                (name, name, email, _hash_password(password), db_role, final_company_id),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            # Defense in depth (Phase 3): the SELECT-then-INSERT duplicate
            # check above has a narrow race window. `email` is UNIQUE at the
            # schema level regardless, so this can only mean a concurrent
            # request took the email first. Same friendly message as the
            # normal duplicate path — never leak the raw sqlite3 error.
            conn.rollback()
            return {"error": "An account with this email already exists."}, 409

        _log_activity(session["user_id"], "admin_action", f'{{"created_user_id": {cursor.lastrowid}}}')
        return {"status": "created", "user_id": cursor.lastrowid}, 201
    finally:
        conn.close()
