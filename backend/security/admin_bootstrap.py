"""Operator-only provisioning for the first Neyan AI super administrator."""

from dataclasses import dataclass

import sqlite3

from backend.security.credentials import EMAIL_RE, PASSWORD_RE, hash_password, is_valid_bcrypt_hash
from database.db import get_db_connection


class BootstrapError(ValueError):
    """A safe, operator-facing bootstrap validation error."""


@dataclass(frozen=True)
class BootstrapResult:
    user_id: int
    email: str


def _normalise_email(email) -> str:
    return (email or "").strip().lower()


def _validate_input(name, email, password):
    name = (name or "").strip()
    email = _normalise_email(email)
    if len(name) < 2:
        raise BootstrapError("Name must contain at least two characters.")
    if not EMAIL_RE.match(email):
        raise BootstrapError("Please provide a valid email address.")
    if not PASSWORD_RE.match(password or ""):
        raise BootstrapError("Password must be at least 8 characters and include a letter and a number.")
    return name, email


def _valid_super_admin_exists(conn) -> bool:
    """Identify a real platform-admin identity without trusting old placeholders.

    A disabled real administrator is still an existing privileged identity.
    Bootstrap must never bypass an intentional disable by creating a second
    platform administrator; its status remains an account-management concern.
    Old non-bcrypt seed placeholders do not represent usable accounts and may
    therefore not block the first official bootstrap on an upgraded database.
    """
    rows = conn.execute(
        """
        SELECT password_hash
        FROM users
        WHERE role = 'admin'
          AND company_id IS NULL
        """
    ).fetchall()
    return any(is_valid_bcrypt_hash(row["password_hash"]) for row in rows)


def provision_first_super_admin(name, email, password) -> BootstrapResult:
    """Create the first enabled super admin exactly once.

    There is intentionally no HTTP route for this action. Existing valid super
    admins are never changed, reset, or duplicated by this operation.
    """
    name, email = _validate_input(name, email, password)
    conn = get_db_connection()
    try:
        # Serialize the existence check with the insert.  This makes two
        # concurrently launched trusted-shell commands deterministic instead
        # of relying on a check-then-insert race.
        conn.execute("BEGIN IMMEDIATE")
        if _valid_super_admin_exists(conn):
            raise BootstrapError("A valid super admin already exists; bootstrap was not performed.")

        duplicate = conn.execute("SELECT 1 FROM users WHERE lower(email) = ?", (email,)).fetchone()
        if duplicate:
            raise BootstrapError("An account with this email already exists; bootstrap was not performed.")

        cursor = conn.execute(
            """
            INSERT INTO users
                (full_name, name, email, password_hash, role, status, company_id, is_active)
            VALUES (?, ?, ?, ?, 'admin', 'approved', NULL, 1)
            """,
            (name, name, email, hash_password(password)),
        )
        conn.commit()
        return BootstrapResult(user_id=cursor.lastrowid, email=email)
    except BootstrapError:
        conn.rollback()
        raise
    except sqlite3.Error as exc:
        conn.rollback()
        raise BootstrapError("Database operation failed; no administrator account was created.") from exc
    finally:
        conn.close()
