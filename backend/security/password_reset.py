"""
backend/security/password_reset.py — Forgot/Reset password architecture.

Phase One implements the full token lifecycle (create, verify, consume,
expire) as requested. No SMTP provider is wired up yet, so the reset
link is logged server-side and also surfaced directly on the "forgot
password" page behind a clearly-labeled "Development mode" notice —
see routes/auth_routes.py::forgot_password(). Swapping in a real email
provider later only means replacing that one notice with an email send;
nothing about the token model needs to change.
"""

import hashlib
import secrets
from datetime import datetime, timedelta

from database.db import get_db_connection

TOKEN_TTL_MINUTES = 30


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_reset_token(user_id: int) -> str:
    """Create a one-time reset token for user_id. Returns the RAW token
    (only the sha256 hash is persisted)."""
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.utcnow() + timedelta(minutes=TOKEN_TTL_MINUTES)).isoformat(sep=" ")

    conn = get_db_connection()
    try:
        # Invalidate any earlier outstanding tokens for this user first.
        conn.execute("DELETE FROM password_resets WHERE user_id = ?", (user_id,))
        conn.execute(
            """
            INSERT INTO password_resets (token_hash, user_id, expires_at)
            VALUES (?, ?, ?)
            """,
            (_hash(token), user_id, expires_at),
        )
        conn.commit()
    finally:
        conn.close()

    return token


def verify_reset_token(token: str):
    """Return user_id if token is valid, unused, and unexpired — else None."""
    if not token:
        return None
    conn = get_db_connection()
    try:
        row = conn.execute(
            """
            SELECT user_id, expires_at, used FROM password_resets
            WHERE token_hash = ?
            """,
            (_hash(token),),
        ).fetchone()
        if not row or row["used"]:
            return None
        if row["expires_at"] < datetime.utcnow().isoformat(sep=" "):
            return None
        return row["user_id"]
    finally:
        conn.close()


def consume_reset_token(token: str) -> None:
    """Mark a token used so it cannot be replayed."""
    conn = get_db_connection()
    try:
        conn.execute(
            "UPDATE password_resets SET used = 1 WHERE token_hash = ?",
            (_hash(token),),
        )
        conn.commit()
    finally:
        conn.close()
