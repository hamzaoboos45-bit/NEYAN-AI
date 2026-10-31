"""Application-wide failed-login rate limit backed by login_attempts."""

from database.db import get_db_connection
from backend.security import security_config


def is_global_limited():
    """Return (limited, reason, failure_count) for the configured time window."""
    threshold = int(security_config.GLOBAL_LOGIN_THRESHOLD)
    window_minutes = int(security_config.GLOBAL_LOGIN_WINDOW_MINUTES)

    if threshold <= 0 or window_minutes <= 0:
        return False, "Global login limit is disabled", 0

    conn = get_db_connection()
    try:
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM login_attempts
            WHERE success = 0
              AND attempted_at >= datetime('now', ?)
            """,
            (f"-{window_minutes} minutes",),
        ).fetchone()
        failure_count = int(row[0]) if row else 0

        if failure_count >= threshold:
            return (
                True,
                f"Global failed-login threshold reached ({failure_count}/{threshold})",
                failure_count,
            )

        return False, "Global login limit not reached", failure_count
    finally:
        conn.close()
