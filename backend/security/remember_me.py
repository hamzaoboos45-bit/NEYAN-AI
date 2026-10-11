"""
backend/security/remember_me.py — "Remember Me" persistent login.

Selector/verifier pattern (the standard, safe way to do long-lived
login cookies):

    cookie value = "<selector>.<verifier>"
        selector  — looked up directly in the DB (not secret)
        verifier  — never stored raw; only sha256(verifier) is stored,
                    so a stolen database dump cannot be replayed as a
                    login cookie.

Every time the cookie is used to restore a session, the token is
ROTATED (old row deleted, new one issued) — this limits how long a
stolen cookie stays useful and lets us detect reuse of a stolen,
already-rotated cookie.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from database.db import get_db_connection

COOKIE_NAME = "remember_token"
COOKIE_MAX_AGE_DAYS = 30


def _hash(verifier: str) -> str:
    return hashlib.sha256(verifier.encode("utf-8")).hexdigest()


def issue_token(user_id: int) -> str:
    """Create a new remember-me token for user_id. Returns the cookie value."""
    selector = secrets.token_hex(12)
    verifier = secrets.token_hex(32)
    expires_at = (datetime.utcnow() + timedelta(days=COOKIE_MAX_AGE_DAYS)).isoformat(sep=" ")

    conn = get_db_connection()
    try:
        conn.execute(
            """
            INSERT INTO remember_tokens (selector, token_hash, user_id, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (selector, _hash(verifier), user_id, expires_at),
        )
        conn.commit()
    finally:
        conn.close()

    return f"{selector}.{verifier}"


def consume_token(cookie_value: str):
    """
    Validate a remember-me cookie and rotate it.
    Returns user_id on success, or None (and deletes the stale row,
    if any) on failure.
    """
    if not cookie_value or "." not in cookie_value:
        return None
    selector, _, verifier = cookie_value.partition(".")

    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT user_id, token_hash, expires_at FROM remember_tokens WHERE selector = ?",
            (selector,),
        ).fetchone()

        # Always remove the presented selector — one-time use, whether it
        # was valid, expired, or forged (guards against token replay).
        conn.execute("DELETE FROM remember_tokens WHERE selector = ?", (selector,))
        conn.commit()

        if not row:
            return None
        if row["expires_at"] < datetime.utcnow().isoformat(sep=" "):
            return None
        if not hmac.compare_digest(row["token_hash"], _hash(verifier)):
            return None

        return row["user_id"]
    finally:
        conn.close()


def revoke_token(cookie_value: str) -> None:
    """Delete a specific remember-me token (used on logout)."""
    if not cookie_value or "." not in cookie_value:
        return
    selector, _, _ = cookie_value.partition(".")
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM remember_tokens WHERE selector = ?", (selector,))
        conn.commit()
    finally:
        conn.close()


def revoke_all_for_user(user_id: int) -> None:
    """Delete every remember-me token for a user (used on password reset)."""
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM remember_tokens WHERE user_id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()
