"""
Central security configuration for NEYAN AI.

Keep login protection thresholds and security feature settings
in one place instead of hardcoding them across modules.
"""

import os


# ─────────────────────────────────────────────────────────────────────────────
# Login rate limiting
# ─────────────────────────────────────────────────────────────────────────────

# Existing limits from brute_force.py
EMAIL_FAIL_THRESHOLD = 5
IP_FAIL_THRESHOLD = 20
LOGIN_WINDOW_MINUTES = 15
LOGIN_LOCKOUT_MINUTES = 15

# Global limit across all login attempts.
# This is a baseline for a single-app deployment using SQLite.
GLOBAL_LOGIN_THRESHOLD = int(os.getenv("GLOBAL_LOGIN_THRESHOLD", "100"))
GLOBAL_LOGIN_WINDOW_MINUTES = int(
    os.getenv("GLOBAL_LOGIN_WINDOW_MINUTES", "15")
)


# ─────────────────────────────────────────────────────────────────────────────
# Progressive delay
# ─────────────────────────────────────────────────────────────────────────────

# Delay starts after this many consecutive failures for an account.
PROGRESSIVE_DELAY_START = int(
    os.getenv("PROGRESSIVE_DELAY_START", "3")
)

# Delay doubles with each additional failure, up to the maximum.
PROGRESSIVE_DELAY_BASE_SECONDS = int(
    os.getenv("PROGRESSIVE_DELAY_BASE_SECONDS", "2")
)

PROGRESSIVE_DELAY_MAX_SECONDS = int(
    os.getenv("PROGRESSIVE_DELAY_MAX_SECONDS", "60")
)


# ─────────────────────────────────────────────────────────────────────────────
# Risk-based challenge / CAPTCHA
# ─────────────────────────────────────────────────────────────────────────────

# A challenge may be required after this many recent failures.
CAPTCHA_FAILURE_THRESHOLD = int(
    os.getenv("CAPTCHA_FAILURE_THRESHOLD", "3")
)

# CAPTCHA is disabled until a provider is configured and integrated.
CAPTCHA_ENABLED = (
    os.getenv("CAPTCHA_ENABLED", "false").strip().lower() == "true"
)

CAPTCHA_PROVIDER = os.getenv("CAPTCHA_PROVIDER", "").strip()

CAPTCHA_SECRET_KEY = os.getenv("CAPTCHA_SECRET_KEY", "").strip()
CAPTCHA_SITE_KEY = os.getenv("CAPTCHA_SITE_KEY", "").strip()


# ─────────────────────────────────────────────────────────────────────────────
# Multi-factor authentication (MFA)
# ─────────────────────────────────────────────────────────────────────────────

# Recommended initial policy: require MFA for administrative accounts.
MFA_REQUIRED_ROLES = ("super_admin", "company_admin")

# MFA remains unavailable until a real MFA flow is implemented/configured.
MFA_ENABLED = (
    os.getenv("MFA_ENABLED", "false").strip().lower() == "true"
)


# ─────────────────────────────────────────────────────────────────────────────
# Security monitoring
# ─────────────────────────────────────────────────────────────────────────────

SECURITY_MONITORING_ENABLED = (
    os.getenv("SECURITY_MONITORING_ENABLED", "true").strip().lower()
    == "true"
)

# Alert threshold for repeated failures targeting one account.
SECURITY_ALERT_ACCOUNT_FAILURES = int(
    os.getenv("SECURITY_ALERT_ACCOUNT_FAILURES", "10")
)

# Alert threshold for a large number of failures from one IP.
SECURITY_ALERT_IP_FAILURES = int(
    os.getenv("SECURITY_ALERT_IP_FAILURES", "30")
)

# Alert threshold for a high volume of login failures system-wide.
SECURITY_ALERT_GLOBAL_FAILURES = int(
    os.getenv("SECURITY_ALERT_GLOBAL_FAILURES", "100")
)


# ─────────────────────────────────────────────────────────────────────────────
# Storage / deployment
# ─────────────────────────────────────────────────────────────────────────────

# SQLite is suitable for the current single-instance project deployment.
# For multiple application instances/workers, use a shared store such as Redis.
SECURITY_COUNTERS_BACKEND = os.getenv(
    "SECURITY_COUNTERS_BACKEND", "sqlite"
).strip().lower()