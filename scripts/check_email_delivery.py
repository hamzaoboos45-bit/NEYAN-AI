"""Trusted-shell email configuration diagnostic; never prints secrets."""
import argparse
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import config
from backend.email import email_service


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Show safe email-provider readiness; optionally send an explicit test message."
    )
    parser.add_argument("--send-test-to", metavar="EMAIL", help="Explicit recipient for a safe test email.")
    args = parser.parse_args(argv)

    status = email_service.configuration_status()
    print(f"EMAIL_PROVIDER={status['provider']}")
    print(f"EMAIL_CONFIGURED={'YES' if status['configured'] else 'NO'}")
    if status["smtp_security"]:
        print(f"SMTP_SECURITY={status['smtp_security']}")
    for key in (
        "smtp_host_present", "smtp_username_present", "smtp_password_present",
        "email_from_present", "sendgrid_api_key_present",
    ):
        print(f"{key.upper()}={'YES' if status[key] else 'NO'}")
    print(f"APP_BASE_URL_PRESENT={'YES' if bool(config.APP_BASE_URL) else 'NO'}")

    if not args.send_test_to:
        return 0 if status["configured"] else 2
    if not status["configured"]:
        print("Test email was not attempted because provider configuration is incomplete.", file=sys.stderr)
        return 2

    # This is intentionally a non-functional URL: the command tests only
    # provider transport/authentication, never creates or exposes a reset token.
    result = email_service.send_password_reset_email(
        args.send_test_to, "https://example.invalid/neyan-ai-email-delivery-test"
    )
    if result.sent:
        print(f"TEST_EMAIL_ACCEPTED provider={result.provider}")
        return 0
    print(f"TEST_EMAIL_FAILED provider={result.provider} error={result.error or 'unspecified'}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
