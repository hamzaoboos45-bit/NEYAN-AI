"""
config.py — Central configuration constants.

All environment-level settings live here so they can be changed
in one place without hunting through the codebase.
"""

import os
import secrets
from pathlib import Path
from dotenv import load_dotenv


class ConfigurationError(RuntimeError):
    """Raised when a production deployment is missing a critical setting."""


PROJECT_ROOT = Path(__file__).resolve().parent
# Load only the project-local operator file, before *any* setting below is
# resolved.  python-dotenv leaves explicit operating-system environment
# variables untouched when override=False, so deployment environment values
# always take precedence over a developer's local .env file.
load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)
APP_ENV = os.environ.get("APP_ENV", os.environ.get("FLASK_ENV", "development")).strip().lower()
if APP_ENV not in {"development", "testing", "production"}:
    raise ConfigurationError("APP_ENV must be development, testing, or production.")
IS_PRODUCTION = APP_ENV == "production"


def _bool_env(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    if value.strip().lower() in {"1", "true", "yes", "on"}:
        return True
    if value.strip().lower() in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} must be a boolean value.")


def _int_env(name, default, minimum=0):
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer.") from exc
    if value < minimum:
        raise ConfigurationError(f"{name} must be at least {minimum}.")
    return value


def _resolved_path(name, default):
    value = os.environ.get(name)
    return Path(value).expanduser().resolve() if value else Path(default).resolve()


# Deployment contract. All runtime paths are resolved at import time, rather
# than from the working directory. Production operators should use absolute
# DATABASE_PATH and UPLOAD_DIR values on persistent writable storage.
DATABASE_PATH = str(_resolved_path("DATABASE_PATH", PROJECT_ROOT / "database" / "transport.db"))
UPLOAD_DIR = str(_resolved_path("UPLOAD_DIR", PROJECT_ROOT / "uploads"))
HOST = os.environ.get("HOST", "0.0.0.0" if IS_PRODUCTION else "127.0.0.1")
PORT = _int_env("PORT", 5000, minimum=1)
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
ASSET_VERSION = os.environ.get("ASSET_VERSION", "post-gate8-defect-closure-1")
TRUSTED_PROXY_COUNT = _int_env("TRUSTED_PROXY_COUNT", 0, minimum=0)
DEBUG = False if IS_PRODUCTION else _bool_env("FLASK_DEBUG", False)
SESSION_COOKIE_SECURE = _bool_env(
    "SESSION_COOKIE_SECURE",
    _bool_env("FORCE_SECURE_COOKIES", IS_PRODUCTION),
)


def get_secret_key():
    """Return an operator-provided key in production, or an isolated dev key."""
    key = os.environ.get("FLASK_SECRET_KEY") or os.environ.get("SECRET_KEY")
    unsafe = {"secret", "dev-secret", "change-me", "default-key", "test-key"}
    if IS_PRODUCTION:
        if not key or len(key) < 32 or key.strip().lower() in unsafe:
            raise ConfigurationError(
                "Production requires FLASK_SECRET_KEY (or SECRET_KEY) with at least 32 non-default characters."
            )
        return key
    return key or secrets.token_urlsafe(48)


def ensure_database_directory():
    """Create only the configured SQLite parent directory; permission errors propagate."""
    Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)


def prepare_runtime_directories():
    """Create configured writable runtime directories without masking failures."""
    ensure_database_directory()
    Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)


def validate_runtime_configuration():
    """Fail closed for incomplete production configuration before app startup."""
    if not IS_PRODUCTION:
        return
    get_secret_key()
    if DEBUG:
        raise ConfigurationError("DEBUG cannot be enabled when APP_ENV=production.")
    if not SESSION_COOKIE_SECURE:
        raise ConfigurationError("SESSION_COOKIE_SECURE must be enabled in production behind HTTPS.")
    if not Path(DATABASE_PATH).is_absolute() or not Path(UPLOAD_DIR).is_absolute():
        raise ConfigurationError("Production DATABASE_PATH and UPLOAD_DIR must resolve to absolute paths.")
    prepare_runtime_directories()

# Chatbot behavior
MAX_CONVERSATION_TURNS = 20        # Reset session after N turns
SESSION_TIMEOUT_MINUTES = 30       # Auto-expire idle sessions

# Chat API security. 2,000 characters comfortably covers a detailed Arabic
# support request while stopping oversized input before NLP/model processing.
CHAT_MAX_MESSAGE_LENGTH = 2000
CHAT_RATE_LIMIT_USER_REQUESTS = 30  # per authenticated user...
CHAT_RATE_LIMIT_IP_REQUESTS = 60    # ...or source IP...
CHAT_RATE_LIMIT_WINDOW_SECONDS = 60 # ...within one minute.

# Jordan governorates are the single reference dataset for every broad route
# or service-area control. ``storage`` preserves Arabic values already used
# by the legacy ``*_city`` route columns; those names predate this contract.
# UI code renders ``en`` or ``ar`` while APIs normalize either language to a
# stable storage value, so a language switch never creates another route.
JORDAN_GOVERNORATES = (
    {"key": "amman", "en": "Amman", "ar": "عمّان", "storage": "عمان"},
    {"key": "irbid", "en": "Irbid", "ar": "إربد", "storage": "إربد"},
    {"key": "zarqa", "en": "Zarqa", "ar": "الزرقاء", "storage": "الزرقاء"},
    {"key": "balqa", "en": "Balqa", "ar": "البلقاء", "storage": "البلقاء"},
    {"key": "mafraq", "en": "Mafraq", "ar": "المفرق", "storage": "المفرق"},
    {"key": "jerash", "en": "Jerash", "ar": "جرش", "storage": "جرش"},
    {"key": "ajloun", "en": "Ajloun", "ar": "عجلون", "storage": "عجلون"},
    {"key": "madaba", "en": "Madaba", "ar": "مادبا", "storage": "مادبا"},
    {"key": "karak", "en": "Karak", "ar": "الكرك", "storage": "الكرك"},
    {"key": "tafilah", "en": "Tafilah", "ar": "الطفيلة", "storage": "الطفيلة"},
    {"key": "maan", "en": "Ma'an", "ar": "معان", "storage": "معان"},
    {"key": "aqaba", "en": "Aqaba", "ar": "العقبة", "storage": "العقبة"},
)
GOVERNORATE_BY_KEY = {governorate["key"]: governorate for governorate in JORDAN_GOVERNORATES}
GOVERNORATE_STORAGE_VALUES = tuple(governorate["storage"] for governorate in JORDAN_GOVERNORATES)

# Backward-compatible legacy name used by existing route/chat code. It is
# derived only from the canonical governorate contract above.
SUPPORTED_CITIES = list(GOVERNORATE_STORAGE_VALUES)

# Vehicle types
VEHICLE_TYPES = ["bus", "car", "van"]

# Trip classes
TRIP_CLASSES = ["economy", "business", "vip"]

# Phase 5 — Forming-trip policy.  These are server-owned defaults and are
# copied to each request at creation so later policy changes never rewrite a
# customer's existing demand terms.
# Vehicle policy is authoritative and snapshotted when a request is created.
# Capacities follow the existing operational seed/fleet semantics: car=4,
# van=10, bus=45. Existing request rows keep their saved values.
TRIP_REQUEST_VEHICLE_POLICY = {
    "car": {"minimum_passengers": 3, "maximum_passengers": 4},
    "van": {"minimum_passengers": 7, "maximum_passengers": 10},
    "bus": {"minimum_passengers": 12, "maximum_passengers": 45},
}
# Backward-compatible aliases for integrations that need the bus default.
TRIP_REQUEST_DEFAULT_MIN_PASSENGERS = TRIP_REQUEST_VEHICLE_POLICY["bus"]["minimum_passengers"]
TRIP_REQUEST_DEFAULT_MAX_PASSENGERS = TRIP_REQUEST_VEHICLE_POLICY["bus"]["maximum_passengers"]
TRIP_REQUEST_EXPIRY_LEAD_HOURS = 24

# Maintenance service categories
MAINTENANCE_SERVICES = {
    "tire_repair":    "تصليح إطارات",
    "tire_replace":   "تبديل إطارات",
    "engine":         "صيانة محرك",
    "oil_change":     "تغيير زيت",
    "battery":        "صيانة بطارية",
}

# Company types
COMPANY_TYPES = ["transport", "maintenance"]

# ─────────────────────────────────────────────────────────
# Version 3 — Voice Assistant configuration
# ─────────────────────────────────────────────────────────
VOICE_TEMP_DIR = str(Path(UPLOAD_DIR) / "voice_temp")
VOICE_HISTORY_DIR = str(Path(UPLOAD_DIR) / "voice_history")

VOICE_STT_ENGINE = os.environ.get("VOICE_STT_ENGINE", "whisper").strip().lower()
if VOICE_STT_ENGINE not in {"whisper", "faster-whisper"}:
    raise ConfigurationError("VOICE_STT_ENGINE must be whisper or faster-whisper.")
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL_SIZE", "base").strip().lower()
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cpu").strip().lower()
WHISPER_COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8").strip().lower()
WHISPER_LANGUAGE = "ar"          # Arabic by default; can be overridden per-request

VOICE_ALLOWED_EXTENSIONS = {"wav", "webm", "ogg", "mp3", "m4a"}
VOICE_MAX_UPLOAD_BYTES = 25 * 1024 * 1024      # 25 MB
VOICE_MAX_RECORDING_SECONDS = 120              # hard server-side sanity cap
VOICE_PARTIAL_INTERVAL_MS = _int_env("VOICE_PARTIAL_INTERVAL_MS", 2000, minimum=1500)
VOICE_CLIENT_MAX_RECORDING_SECONDS = _int_env("VOICE_CLIENT_MAX_RECORDING_SECONDS", 45, minimum=10)

TTS_DEFAULT_RATE = 175          # words per minute baseline for pyttsx3
TTS_MAX_TEXT_LENGTH = 2000

# ─────────────────────────────────────────────────────────
# Project Two, Phase Two — Arabic Natural Language Intelligence
# ─────────────────────────────────────────────────────────
import os as _os

# Master switch. False = pure rule-based NLP only, AraBERT/MARBERT never
# even attempt to load (useful for CI, offline dev, or a machine that
# hasn't installed the optional `transformers`/`torch` extras yet). The
# chatbot behaves identically either way — this only decides whether the
# AI layer is attempted before falling back to backend/intents.py.
ENABLE_AI_NLP = _os.environ.get("ENABLE_AI_NLP", "1") != "0"

# Below this confidence, the Hybrid Pipeline discards the AraBERT
# prediction and uses the existing Rule-Based NLP instead. Tune this
# after collecting real usage data in nlp_analysis_log (see database/init_db.py).
NLP_CONFIDENCE_THRESHOLD = float(_os.environ.get("NLP_CONFIDENCE_THRESHOLD", "0.60"))

# A reviewed, compact supervised classifier trained from
# ``training_data/chat_intents.jsonl``.  The default artifact is shipped with
# the application, contains no customer data, and can be overridden only for
# an explicit deployment experiment.  If it is absent or invalid, the hybrid
# pipeline safely continues with the existing optional AraBERT/rule path.
TRAINED_CHAT_MODEL_PATH = _os.environ.get(
    "TRAINED_CHAT_MODEL_PATH",
    os.path.join(os.path.dirname(__file__), "backend", "nlp", "models"),
)

# Explicit deployment selector for reviewed supervised intent artifacts.  V1
# remains the safe default until an operator completes V2 validation gates.
# Invalid values do not fall through to an arbitrary artifact: the loader
# reports an unavailable model and the existing semantic/rule fallback applies.
TRAINED_CHAT_MODEL_VERSION = _os.environ.get("TRAINED_CHAT_MODEL_VERSION", "v1").strip().lower()

# Public, well-known Hugging Face model IDs. Downloaded + cached locally
# on first use (standard `transformers` behavior) — see
# backend/nlp/model_loader.py for what happens if that download can't
# complete (e.g. no network access at deploy time).
ARABERT_MODEL_NAME = _os.environ.get("ARABERT_MODEL_NAME", "aubmindlab/bert-base-arabertv02")
MARBERT_NER_MODEL_NAME = _os.environ.get("MARBERT_NER_MODEL_NAME", "hatmimoha/arabic-ner")

# Part Nine (UI): show detected intent/confidence/entities under each bot
# reply for developers. MUST be off in production — default is False and
# is only ever flipped on via an explicit env var, never hardcoded on.
NLP_DEBUG_MODE = _os.environ.get("NLP_DEBUG_MODE", "0") == "1"

# ─────────────────────────────────────────────────────────
# Phase 3 continuation — Email infrastructure
# ─────────────────────────────────────────────────────────
# No credentials live here or anywhere else in source. Every value below
# is read from the environment only; if unset, EMAIL_PROVIDER defaults to
# "console" and the app behaves exactly as it did before this phase —
# reset links are logged server-side and shown on the page behind the
# existing "Development mode" notice. Nothing breaks if these are never set.
#
# To enable real delivery, set these in your environment (never in a
# committed file) and restart the app:
#
#   EMAIL_PROVIDER=smtp          (or "sendgrid", or leave unset/"console")
#
#   --- for EMAIL_PROVIDER=smtp (e.g. Gmail) ---
#   SMTP_HOST=smtp.gmail.com
#   SMTP_PORT=587
#   SMTP_SECURITY=starttls       (or ssl for implicit TLS on port 465)
#   SMTP_USERNAME=your-address@gmail.com
#   SMTP_PASSWORD=<16-character Gmail App Password — NOT your Gmail password>
#
#   --- for EMAIL_PROVIDER=sendgrid ---
#   SENDGRID_API_KEY=<your SendGrid API key>
#
#   --- either provider ---
#   EMAIL_FROM=your-address@gmail.com     (defaults to SMTP_USERNAME for smtp)
#   EMAIL_FROM_NAME=Neyan AI
#   APP_BASE_URL=https://your-real-domain.example   (see §11 of the brief —
#       leave unset in dev; reset links then fall back to Flask's own
#       request-derived URL, exactly as they do today)
EMAIL_PROVIDER = _os.environ.get("EMAIL_PROVIDER", "console").strip().lower()

SMTP_HOST = _os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(_os.environ.get("SMTP_PORT", "587") or "587")
SMTP_SECURITY = _os.environ.get("SMTP_SECURITY", "starttls").strip().lower()
if SMTP_SECURITY not in {"starttls", "ssl"}:
    raise ConfigurationError("SMTP_SECURITY must be either starttls or ssl.")
SMTP_USERNAME = _os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = _os.environ.get("SMTP_PASSWORD", "")

SENDGRID_API_KEY = _os.environ.get("SENDGRID_API_KEY", "")

EMAIL_FROM = _os.environ.get("EMAIL_FROM", "") or SMTP_USERNAME
EMAIL_FROM_NAME = _os.environ.get("EMAIL_FROM_NAME", "Neyan AI")

# Used to build the reset link. Empty in dev on purpose — the route falls
# back to Flask's own url_for(..., _external=True), which is already
# correct for local development. Set this in production so links are
# never accidentally generated with a request's Host header instead of
# the real public domain.
APP_BASE_URL = _os.environ.get("APP_BASE_URL", "").rstrip("/")
