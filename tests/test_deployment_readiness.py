"""Production-style configuration and clean-room startup contracts."""

import os
import secrets
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _production_env(tmp_path):
    env = os.environ.copy()
    env.update(
        {
            "APP_ENV": "production",
            "FLASK_SECRET_KEY": secrets.token_urlsafe(48),
            "DATABASE_PATH": str((tmp_path / "persistent" / "transport.db").resolve()),
            "UPLOAD_DIR": str((tmp_path / "persistent" / "uploads").resolve()),
            "SESSION_COOKIE_SECURE": "1",
            "TRUSTED_PROXY_COUNT": "0",
            "ENABLE_AI_NLP": "0",
        }
    )
    return env


def _run(code, env, timeout=45):
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def test_production_requires_a_strong_external_secret(tmp_path):
    env = _production_env(tmp_path)
    for unsafe_secret in (None, "dev-secret", "short"):
        if unsafe_secret is None:
            env.pop("FLASK_SECRET_KEY", None)
        else:
            env["FLASK_SECRET_KEY"] = unsafe_secret
        result = _run("import config; config.validate_runtime_configuration()", env)
        assert result.returncode != 0
        assert "Production requires FLASK_SECRET_KEY" in (result.stdout + result.stderr)


def test_production_clean_room_wsgi_health_static_customer_and_admin_smoke(tmp_path):
    env = _production_env(tmp_path)
    password = "A1" + secrets.token_urlsafe(24)
    env["NEYAN_TEST_PASSWORD"] = password
    env["NEYAN_TEST_CUSTOMER_PASSWORD"] = "A1" + secrets.token_urlsafe(24)
    code = r'''
import os, re, subprocess, sys
from pathlib import Path
from backend.speech import whisper_engine
from backend.nlp import model_loader
whisper_engine.preload = lambda: None
model_loader.preload = lambda: None
import wsgi
app = wsgi.app
assert app.config["DEBUG"] is False
assert app.config["TESTING"] is False
assert app.config["SESSION_COOKIE_SECURE"] is True
client = app.test_client()
base = "https://neyan.test"
assert client.get("/health", base_url=base).status_code == 200
assert client.get("/health", base_url=base).get_json() == {"status": "ok"}
for asset in ("/static/css/main.css", "/static/css/tokens.css", "/static/js/theme-lang.js", "/static/brand/neyan-logo-full.png"):
    assert client.get(asset, base_url=base).status_code == 200
login = client.get("/login", base_url=base)
assert login.status_code == 200
token = re.search(r'name="csrf_token" value="([^"]+)"', login.get_data(as_text=True)).group(1)
registered = client.post("/register", base_url=base, data={
    "csrf_token": token, "name": "Clean Room Customer", "email": "customer@example.test",
    "password": os.environ["NEYAN_TEST_CUSTOMER_PASSWORD"]
})
assert registered.status_code == 302 and registered.headers["Location"].endswith("/home")
for page in ("/home", "/trips", "/chat", "/maintenance"):
    assert client.get(page, base_url=base).status_code == 200
assert client.get("/logout", base_url=base).status_code == 302
bootstrap = subprocess.run(
    [sys.executable, "scripts/bootstrap_super_admin.py", "--name", "Clean Room Owner", "--email", "owner@example.test", "--password-stdin"],
    cwd=Path.cwd(), env=os.environ.copy(), input=os.environ["NEYAN_TEST_PASSWORD"] + "\n", text=True, capture_output=True
)
assert bootstrap.returncode == 0, bootstrap.stderr
assert os.environ["NEYAN_TEST_PASSWORD"] not in (bootstrap.stdout + bootstrap.stderr)
login = client.get("/login", base_url=base)
token = re.search(r'name="csrf_token" value="([^"]+)"', login.get_data(as_text=True)).group(1)
admin = client.post("/login", base_url=base, data={
    "csrf_token": token, "email": "owner@example.test", "password": os.environ["NEYAN_TEST_PASSWORD"]
})
assert admin.status_code == 302 and admin.headers["Location"].endswith("/admin")
assert client.get("/admin", base_url=base).status_code == 200
assert client.get("/api/admin/control-center/overview", base_url=base).status_code == 200
assert Path(os.environ["DATABASE_PATH"]).is_file()
assert Path(os.environ["UPLOAD_DIR"]).is_dir()
print("production-clean-room-ok")
'''
    result = _run(code, env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "production-clean-room-ok" in result.stdout


def test_deployment_contract_is_documented_and_has_no_public_bootstrap_source_route():
    config_source = (ROOT / "config.py").read_text(encoding="utf-8")
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "validate_runtime_configuration" in config_source
    assert "DATABASE_PATH" in config_source and "UPLOAD_DIR" in config_source
    assert '"/health"' in app_source and "ProxyFix" in app_source
    assert "waitress-serve" in readme and "Production / Deployment Readiness" in readme
    assert "bootstrap" not in "\n".join(
        line for line in app_source.splitlines() if "route(" in line.lower()
    ).lower()
