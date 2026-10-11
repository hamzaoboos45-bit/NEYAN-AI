"""Trusted-shell maintenance for existing super-admin access.

There is intentionally no HTTP endpoint for these operations. The service
returns only account identifiers and never emits a password or password hash.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from backend.security.credentials import EMAIL_RE, PASSWORD_RE, hash_password
from database.db import get_db_connection


class AdminManagementError(ValueError):
    """A safe, operator-facing administration error."""


@dataclass(frozen=True)
class AdminIdentity:
    user_id: int
    email: str


def list_super_admins() -> list[AdminIdentity]:
    """List enabled platform-admin identifiers, never credential material."""
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """SELECT user_id, email FROM users
               WHERE role='admin' AND company_id IS NULL
                 AND status='approved' AND is_active=1
               ORDER BY lower(email), user_id"""
        ).fetchall()
        return [AdminIdentity(int(row["user_id"]), row["email"]) for row in rows]
    finally:
        conn.close()


def reset_super_admin_password(email: str, password: str) -> AdminIdentity:
    """Reset one platform-super-admin password without changing its account state.

    A trusted operator may reset an inactive administrator's password for
    recovery readiness, but this operation deliberately does not reactivate
    the account.  Only the existing authoritative administration workflow
    controls status and is_active.
    """
    normalized_email = (email or "").strip().lower()
    if not EMAIL_RE.match(normalized_email):
        raise AdminManagementError("Provide a valid super-admin email address.")
    if not isinstance(password, str) or not PASSWORD_RE.match(password):
        raise AdminManagementError("Password must be at least 8 characters and include a letter and a number.")

    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """SELECT user_id, email FROM users
               WHERE lower(email)=? AND role='admin' AND company_id IS NULL
                 AND status='approved'
            """,
            (normalized_email,),
        ).fetchone()
        if not row:
            raise AdminManagementError("No super-admin account matches that email address.")
        conn.execute("UPDATE users SET password_hash=? WHERE user_id=?", (hash_password(password), row["user_id"]))
        # A remembered browser must not survive an operator-initiated reset.
        conn.execute("DELETE FROM remember_tokens WHERE user_id=?", (row["user_id"],))
        conn.commit()
        return AdminIdentity(int(row["user_id"]), row["email"])
    except AdminManagementError:
        conn.rollback()
        raise
    except sqlite3.Error as exc:
        conn.rollback()
        raise AdminManagementError("Database operation failed; no password was changed.") from exc
    finally:
        conn.close()
