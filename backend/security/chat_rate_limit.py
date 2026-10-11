"""Small persistent rate limiter for authenticated Chat requests.

The limit is intentionally conversation-friendly: 30 messages/minute for a
user and 60/minute for an IP. ``consume_request`` performs the check and event
write in one SQLite write transaction so concurrent requests cannot both pass
the same threshold in a single application database.
"""

import config
from database.db import get_db_connection


def consume_request(user_id: int, ip_address: str) -> bool:
    """Record one request and return True only when it is within the limit."""
    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        window = f"-{config.CHAT_RATE_LIMIT_WINDOW_SECONDS} seconds"
        user_count = conn.execute(
            """SELECT COUNT(*) FROM chat_rate_limit_events
               WHERE user_id = ? AND created_at >= datetime('now', ?)""",
            (user_id, window),
        ).fetchone()[0]
        ip_count = conn.execute(
            """SELECT COUNT(*) FROM chat_rate_limit_events
               WHERE ip_address = ? AND created_at >= datetime('now', ?)""",
            (ip_address or "", window),
        ).fetchone()[0]
        if user_count >= config.CHAT_RATE_LIMIT_USER_REQUESTS or ip_count >= config.CHAT_RATE_LIMIT_IP_REQUESTS:
            conn.rollback()
            return False

        conn.execute(
            "INSERT INTO chat_rate_limit_events (user_id, ip_address) VALUES (?, ?)",
            (user_id, ip_address or ""),
        )
        conn.execute(
            "DELETE FROM chat_rate_limit_events WHERE created_at < datetime('now', '-1 day')"
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
