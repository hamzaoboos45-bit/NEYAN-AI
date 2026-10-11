"""SMTP transport-mode regressions for password-reset delivery."""
import smtplib
import socket
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
from backend.email import email_service


def configure_smtp(monkeypatch, security):
    monkeypatch.setattr(config, "EMAIL_PROVIDER", "smtp")
    monkeypatch.setattr(config, "SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setattr(config, "SMTP_PORT", 465 if security == "ssl" else 587)
    monkeypatch.setattr(config, "SMTP_SECURITY", security)
    monkeypatch.setattr(config, "SMTP_USERNAME", "sender@example.com")
    monkeypatch.setattr(config, "SMTP_PASSWORD", "test-app-password-not-real")
    monkeypatch.setattr(config, "EMAIL_FROM", "sender@example.com")
    monkeypatch.setattr(config, "EMAIL_FROM_NAME", "NEYAN AI")


def test_starttls_mode_uses_smtp_and_negotiates_before_login(monkeypatch):
    configure_smtp(monkeypatch, "starttls")
    server = MagicMock()
    with patch("backend.email.email_service.smtplib.SMTP") as smtp, patch(
        "backend.email.email_service.smtplib.SMTP_SSL"
    ) as smtp_ssl:
        smtp.return_value.__enter__.return_value = server
        result = email_service.send_password_reset_email("recipient@example.com", "https://example.test/reset")

    assert result.sent is True
    smtp.assert_called_once_with("smtp.gmail.com", 587, timeout=10)
    smtp_ssl.assert_not_called()
    assert server.ehlo.call_count == 2
    server.starttls.assert_called_once()
    server.login.assert_called_once_with("sender@example.com", "test-app-password-not-real")
    assert server.sendmail.called


def test_ssl_mode_uses_smtp_ssl_without_starttls(monkeypatch):
    configure_smtp(monkeypatch, "ssl")
    server = MagicMock()
    with patch("backend.email.email_service.smtplib.SMTP") as smtp, patch(
        "backend.email.email_service.smtplib.SMTP_SSL"
    ) as smtp_ssl:
        smtp_ssl.return_value.__enter__.return_value = server
        result = email_service.send_password_reset_email("recipient@example.com", "https://example.test/reset")

    assert result.sent is True
    smtp.assert_not_called()
    smtp_ssl.assert_called_once()
    args, kwargs = smtp_ssl.call_args
    assert args == ("smtp.gmail.com", 465)
    assert kwargs["timeout"] == 10 and kwargs["context"] is not None
    server.starttls.assert_not_called()
    server.ehlo.assert_not_called()
    server.login.assert_called_once_with("sender@example.com", "test-app-password-not-real")
    assert server.sendmail.called


@pytest.mark.parametrize("security, transport", [("starttls", "SMTP"), ("ssl", "SMTP_SSL")])
def test_authentication_and_timeout_errors_remain_safe(monkeypatch, security, transport):
    configure_smtp(monkeypatch, security)
    module_path = f"backend.email.email_service.smtplib.{transport}"
    with patch(module_path) as client:
        server = client.return_value.__enter__.return_value
        server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"test-app-password-not-real")
        auth_result = email_service.send_password_reset_email("recipient@example.com", "https://example.test/reset")
    assert auth_result.sent is False
    assert "authentication failed" in auth_result.error.lower()
    assert config.SMTP_PASSWORD not in auth_result.error

    with patch(module_path, side_effect=socket.timeout):
        timeout_result = email_service.send_password_reset_email("recipient@example.com", "https://example.test/reset")
    assert timeout_result.sent is False
    assert timeout_result.error == "SMTP connection timed out."
    assert config.SMTP_PASSWORD not in timeout_result.error
