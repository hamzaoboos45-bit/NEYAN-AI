"""
backend/security/reset_rate_limit.py — Forgot-password abuse throttling.

Phase 3 continuation: the forgot-password endpoint previously had no rate
limiting at all (documented risk — see the phase report). Unlike login
brute-force protection (backend/security/brute_force.py, which counts
*failed password guesses*), this counts *reset requests themselves*,
because the risk here is different: spamming someone's inbox and, once a
real email provider is configured, burning through that provider's send
quota — not credential guessing.

Deliberately generous thresholds so a legitimate user who mistypes their
email or re-requests a link never gets blocked, while a script hammering
the endpoint does. This mirrors brute_force.py's existing table-backed
pattern (same project, same conventions) rather than introducing a new
rate-limiting framework/dependency, per the brief's "do not introduce a
huge security framework just for this phase" instruction.
"""

from database.db import get_db_connection

EMAIL_THRESHOLD = 3       # max requests for the same email...
IP_THRESHOLD = 10         # ...or from the same IP...
WINDOW_MINUTES = 15       # ...within this many minutes.


def record_request(email: str, ip_address: str) -> None:
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO password_reset_requests (email, ip_address) VALUES (?, ?)",
            (email, ip_address or ""),
        )
        # Best-effort housekeeping, same approach as brute_force.py.
        conn.execute(
            "DELETE FROM password_reset_requests WHERE requested_at < datetime('now', '-1 day')"
        )
        conn.commit()
    finally:
        conn.close()


def is_rate_limited(email: str, ip_address: str) -> bool:
    """Returns True if this email or IP has made too many reset requests
    recently. Deliberately returns only a bool (no reason string) —
    unlike brute_force.is_locked(), the caller must NOT surface a
    different message for this case, or a rate-limit-specific message
    would itself leak whether the email exists (see auth_routes.py)."""
    conn = get_db_connection()
    try:
        email_count = conn.execute(
            """
            SELECT COUNT(*) FROM password_reset_requests
            WHERE email = ? AND requested_at >= datetime('now', ?)
            """,
            (email, f"-{WINDOW_MINUTES} minutes"),
        ).fetchone()[0]
        if email_count >= EMAIL_THRESHOLD:
            return True

        ip_count = conn.execute(
            """
            SELECT COUNT(*) FROM password_reset_requests
            WHERE ip_address = ? AND requested_at >= datetime('now', ?)
            """,
            (ip_address or "", f"-{WINDOW_MINUTES} minutes"),
        ).fetchone()[0]
        return ip_count >= IP_THRESHOLD
    finally:
        conn.close()
