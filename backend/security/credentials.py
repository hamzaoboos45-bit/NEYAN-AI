"""Shared credential validation and bcrypt helpers."""

import re

import bcrypt


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PASSWORD_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,}$")


def hash_password(password: str) -> str:
    """Return a bcrypt hash; callers must never persist plaintext passwords."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def is_valid_bcrypt_hash(password_hash) -> bool:
    """Return whether a value is syntactically usable by bcrypt, without logging it."""
    if not isinstance(password_hash, str):
        return False
    try:
        bcrypt.checkpw(b"bootstrap-format-probe", password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False
    return True
