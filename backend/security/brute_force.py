"""
backend/security/brute_force.py — Login brute-force protection.

Two independent counters, both backed by the login_attempts table
(database/init_db.py):

    per email — 5 failed attempts within 15 minutes locks that
                account's login for 15 minutes, regardless of IP.
    per IP    — 20 failed attempts within 15 minutes locks that IP
                from logging in to ANY account for 15 minutes
                (stops credential-stuffing across many emails).

A successful login clears the failing streak for that email.
Old rows are pruned opportunistically so the table never grows
unbounded on a long-running server.
"""

from database.db import get_db_connection

EMAIL_FAIL_THRESHOLD = 5
IP_FAIL_THRESHOLD = 20
WINDOW_MINUTES = 15
LOCKOUT_MINUTES = 15


def record_attempt(email: str, ip_address: str, success: bool) -> None:
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO login_attempts (email, ip_address, success) VALUES (?, ?, ?)",
            (email, ip_address or "", 1 if success else 0),
        )
        # Best-effort housekeeping — keep the table small.
        conn.execute(
            "DELETE FROM login_attempts WHERE attempted_at < datetime('now', '-1 day')"
        )
        conn.commit()
    finally:
        conn.close()


def _recent_failures(conn, column: str, value: str) -> int:
    row = conn.execute(
        f"""
        SELECT COUNT(*) FROM login_attempts
        WHERE {column} = ?
          AND success = 0
          AND attempted_at >= datetime('now', ?)
        """,
        (value, f"-{WINDOW_MINUTES} minutes"),
    ).fetchone()
    return row[0] if row else 0


def is_locked(email: str, ip_address: str):
    """
    Returns (locked: bool, reason: str | None).
    Checked BEFORE verifying the password, so a locked account
    never even reaches the password-comparison step.
    """
    conn = get_db_connection()
    try:
        email_fails = _recent_failures(conn, "email", email)
        if email_fails >= EMAIL_FAIL_THRESHOLD:
            return True, (
                f"Too many failed attempts for this account. "
                f"Please try again in {LOCKOUT_MINUTES} minutes."
            )

        ip_fails = _recent_failures(conn, "ip_address", ip_address or "")
        if ip_fails >= IP_FAIL_THRESHOLD:
            return True, (
                f"Too many failed login attempts from this network. "
                f"Please try again in {LOCKOUT_MINUTES} minutes."
            )

        return False, None
    finally:
        conn.close()


def reset_failures(email: str) -> None:
    """Called after a successful login — clears this account's failing streak."""
    conn = get_db_connection()
    try:
        conn.execute(
            "DELETE FROM login_attempts WHERE email = ? AND success = 0",
            (email,),
        )
        conn.commit()
    finally:
        conn.close()
