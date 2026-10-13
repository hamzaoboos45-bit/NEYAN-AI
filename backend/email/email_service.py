"""
backend/email/email_service.py â€” Provider-agnostic email sending.

Architecture (per the brief):

    Auth Route  â†’  Password Reset Service  â†’  Email Service  â†’  Provider

`routes/auth_routes.py` calls `send_password_reset_email()` here.
`backend/security/password_reset.py` remains the "service" for the token
lifecycle (create/verify/consume) â€” this module is the "service" for
email transmission only. It doesn't know anything about tokens, users, or
Flask; it just sends a rendered email through whichever provider is
configured, or reports that none is configured.

Provider selection is entirely environment-driven (config.EMAIL_PROVIDER):
  - "console"  (default) â€” do not attempt to send anything. The caller is
                expected to fall back to logging/displaying the link
                itself, exactly as before this phase existed.
  - "smtp"     â€” any SMTP server, incl. Gmail with an App Password.
  - "sendgrid" â€” SendGrid's HTTP API (no extra pip dependency â€” uses the
                standard library's urllib instead of `requests`, since
                nothing else in this project pulls in `requests` and one
                clean HTTP call doesn't justify a new dependency).

CRITICAL: nothing in this file ever logs, prints, or returns
config.SMTP_PASSWORD or config.SENDGRID_API_KEY. Errors are summarized
into safe, generic diagnostic strings before they're returned or logged.
"""

import json
import smtplib
import socket
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import config
from backend.email.templates import build_password_reset_email

_TIMEOUT_SECONDS = 10


@dataclass
class EmailResult:
    attempted: bool          # False only for the "console"/unconfigured case
    sent: bool                # True only on confirmed provider acceptance
    provider: str             # "console" | "smtp" | "sendgrid"
    error: Optional[str] = None   # safe-to-log summary; never a raw secret


def is_configured() -> bool:
    """True if enough environment configuration exists to actually attempt
    sending â€” independent of whether a send would succeed."""
    if config.EMAIL_PROVIDER == "smtp":
        return bool(config.SMTP_HOST and config.SMTP_USERNAME and config.SMTP_PASSWORD)
    if config.EMAIL_PROVIDER == "sendgrid":
        return bool(config.SENDGRID_API_KEY and config.EMAIL_FROM)
    return False


def configuration_status() -> dict:
    """Return safe, boolean-only provider diagnostics for trusted operators."""
    provider = config.EMAIL_PROVIDER
    return {
        "provider": provider,
        "configured": is_configured(),
        "smtp_host_present": bool(config.SMTP_HOST),
        "smtp_security": config.SMTP_SECURITY if provider == "smtp" else None,
        "smtp_username_present": bool(config.SMTP_USERNAME),
        "smtp_password_present": bool(config.SMTP_PASSWORD),
        "email_from_present": bool(config.EMAIL_FROM),
        "sendgrid_api_key_present": bool(config.SENDGRID_API_KEY),
    }


def _send_via_smtp(to_email: str, content: dict):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = content["subject"]
    msg["From"] = f"{config.EMAIL_FROM_NAME} <{config.EMAIL_FROM}>"
    msg["To"] = to_email
    msg.attach(MIMEText(content["text"], "plain", "utf-8"))
    msg.attach(MIMEText(content["html"], "html", "utf-8"))

    stage = "initialization"

    try:
        context = ssl.create_default_context()

        if config.SMTP_SECURITY == "ssl":
            stage = "SSL connection"
            connection = smtplib.SMTP_SSL(
                config.SMTP_HOST,
                config.SMTP_PORT,
                context=context,
                timeout=_TIMEOUT_SECONDS,
            )
        else:
            stage = "SMTP connection"
            connection = smtplib.SMTP(
                config.SMTP_HOST,
                config.SMTP_PORT,
                timeout=_TIMEOUT_SECONDS,
            )

        with connection as server:
            if config.SMTP_SECURITY == "starttls":
                stage = "STARTTLS negotiation"
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()

            stage = "SMTP authentication"
            server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)

            stage = "message submission"
            server.sendmail(
                config.EMAIL_FROM,
                [to_email],
                msg.as_string(),
            )

        return True, None

    except smtplib.SMTPAuthenticationError:
        return False, "SMTP authentication failed."

    except smtplib.SMTPException as e:
        return False, f"SMTP error during {stage}: {type(e).__name__}."

    except (socket.timeout, TimeoutError):
        return False, f"SMTP timeout during {stage}."

    except OSError as e:
        return False, f"SMTP connection failed during {stage}: {type(e).__name__}."


def send_password_reset_email(to_email: str, reset_link: str) -> EmailResult:
    if config.EMAIL_PROVIDER not in {"console", "smtp", "sendgrid"}:
        return EmailResult(
            attempted=False,
            sent=False,
            provider=config.EMAIL_PROVIDER,
            error="Unknown email provider configuration.",
        )

    if not is_configured():
        error = (
            None
            if config.EMAIL_PROVIDER == "console"
            else "Email provider configuration is incomplete."
        )
        return EmailResult(
            attempted=False,
            sent=False,
            provider=config.EMAIL_PROVIDER,
            error=error,
        )

    content = build_password_reset_email(reset_link)

    if config.EMAIL_PROVIDER == "smtp":
        ok, error = _send_via_smtp(to_email, content)
        return EmailResult(
            attempted=True,
            sent=ok,
            provider="smtp",
            error=error,
        )

    if config.EMAIL_PROVIDER == "sendgrid":
        ok, error = _send_via_sendgrid(to_email, content)
        return EmailResult(
            attempted=True,
            sent=ok,
            provider="sendgrid",
            error=error,
        )

    return EmailResult(
        attempted=False,
        sent=False,
        provider=config.EMAIL_PROVIDER,
        error="Email provider configuration is incomplete.",
    )

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Providers â€” each returns (ok: bool, safe_error_message: str | None) and
# is responsible for never leaking config.SMTP_PASSWORD / SENDGRID_API_KEY
# into that error message, into a log line, or into an exception re-raise.
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _send_via_sendgrid(to_email: str, content: dict):
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": config.EMAIL_FROM, "name": config.EMAIL_FROM_NAME},
        "subject": content["subject"],
        "content": [
            {"type": "text/plain", "value": content["text"]},
            {"type": "text/html", "value": content["html"]},
        ],
    }
    request = urllib.request.Request(
        "https://api.sendgrid.com/v3/mail/send",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {config.SENDGRID_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as resp:
            # SendGrid returns 202 Accepted on success.
            if 200 <= resp.status < 300:
                return True, None
            return False, f"SendGrid returned unexpected status {resp.status}."
    except urllib.error.HTTPError as e:
        # e.code is safe to log (e.g. 401, 403, 429); the body may echo
        # request details back, so it's deliberately not included.
        return False, f"SendGrid HTTP error {e.code}."
    except urllib.error.URLError as e:
        return False, f"SendGrid connection failed: {type(e.reason).__name__ if e.reason else 'unknown'}."
    except socket.timeout:
        return False, "SendGrid request timed out."
