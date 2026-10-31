# backend/security/progressive_delay.py

import time

from backend.security import security_config
from database.db import get_db_connection


def apply_delay(email: str, ip_address: str) -> int:
    """
    Apply an increasing delay after repeated failed login attempts.

    Returns the number of seconds delayed.
    """

    start_after = security_config.PROGRESSIVE_DELAY_START
    base_delay = security_config.PROGRESSIVE_DELAY_BASE_SECONDS
    max_delay = security_config.PROGRESSIVE_DELAY_MAX_SECONDS
    window_minutes = security_config.WINDOW_MINUTES

    if start_after <= 0 or base_delay <= 0 or max_delay <= 0:
        return 0

    conn = get_db_connection()

    try:
        row = conn.execute(
            """
            SELECT COUNT(*) AS failures
            FROM login_attempts
            WHERE success = 0
              AND lower(email) = lower(?)
              AND ip_address = ?
              AND datetime(attempted_at) >= datetime('now', ?)
            """,
            (email, ip_address, f"-{window_minutes} minutes"),
        ).fetchone()

        failures = int(row["failures"] or 0) if row else 0

    finally:
        conn.close()

    if failures < start_after:
        return 0

    exponent = failures - start_after
    delay_seconds = min(base_delay * (2 ** exponent), max_delay)

    time.sleep(delay_seconds)
    return delay_seconds