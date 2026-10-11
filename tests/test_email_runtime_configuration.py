"""Runtime configuration contracts for real password-reset delivery."""
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_project_config_loads_dotenv_before_values_and_preserves_os_precedence():
    source = (ROOT / "config.py").read_text(encoding="utf-8")
    assert "from dotenv import load_dotenv" in source
    assert 'load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)' in source


def test_dotenv_values_load_but_explicit_os_environment_wins(tmp_path):
    config_copy = tmp_path / "config.py"
    config_copy.write_text((ROOT / "config.py").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / ".env").write_text(
        "APP_ENV=development\nEMAIL_PROVIDER=smtp\nSMTP_USERNAME=dotenv-user\nSMTP_PASSWORD=dotenv-password\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update({"PYTHONPATH": str(tmp_path), "EMAIL_PROVIDER": "sendgrid", "SENDGRID_API_KEY": "os-only-key"})
    probe = "import config; print(config.EMAIL_PROVIDER); print(config.SMTP_USERNAME); print(config.SENDGRID_API_KEY)"
    result = subprocess.run([sys.executable, "-c", probe], cwd=tmp_path, env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["sendgrid", "dotenv-user", "os-only-key"]


def test_invalid_smtp_security_fails_closed_without_echoing_environment(tmp_path):
    config_copy = tmp_path / "config.py"
    config_copy.write_text((ROOT / "config.py").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / ".env").write_text("SMTP_SECURITY=unsupported-mode\nSMTP_PASSWORD=should-not-appear\n", encoding="utf-8")
    result = subprocess.run([sys.executable, "-c", "import config"], cwd=tmp_path, text=True, capture_output=True)
    assert result.returncode != 0
    assert "SMTP_SECURITY must be either starttls or ssl" in result.stderr
    assert "should-not-appear" not in result.stderr


def test_example_documents_safe_full_reset_delivery_configuration():
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    for key in (
        "APP_ENV", "FLASK_SECRET_KEY", "DATABASE_PATH", "UPLOAD_DIR", "SESSION_COOKIE_SECURE",
        "HOST", "PORT", "EMAIL_PROVIDER", "SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME",
        "SMTP_PASSWORD", "SMTP_SECURITY", "EMAIL_FROM", "EMAIL_FROM_NAME", "SENDGRID_API_KEY", "APP_BASE_URL",
    ):
        assert f"{key}=" in example
    assert "Gmail App Password" in example


def test_email_diagnostic_is_boolean_only_and_never_prints_secrets():
    script = (ROOT / "scripts" / "check_email_delivery.py").read_text(encoding="utf-8")
    assert "configuration_status" in script
    assert "SMTP_SECURITY=" in script
    assert "SMTP_PASSWORD=" not in script
    assert "SENDGRID_API_KEY=" not in script
    assert "example.invalid/neyan-ai-email-delivery-test" in script
