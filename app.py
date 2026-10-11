
import os
import logging
import sqlite3
from datetime import timedelta

from flask import Flask, jsonify, request, session
from werkzeug.middleware.proxy_fix import ProxyFix

import config
from database.init_db import initialize_database
from database.db import get_db_connection
from routes.admin_routes import admin_bp
from routes.dashboard_routes import dashboard_bp
from routes.auth_routes import auth_bp, load_logged_in_user_from_remember_cookie
from routes.booking_routes import booking_bp
from routes.chat_routes import chat_bp
from routes.maintenance_routes import maintenance_bp
from routes.review_routes import review_bp
from routes.nlp_routes import nlp_bp
from routes.voice_routes import voice_bp
from routes.trip_request_routes import trip_request_bp
from routes.demand_admin_routes import demand_admin_bp
from routes.notification_routes import notification_bp
from routes.pricing_routes import pricing_bp
from backend.security.csrf import init_csrf
from backend.security import remember_me


def _configure_logging(app):
    """Configure application logging without adding file/secret logging."""
    level = getattr(logging, config.LOG_LEVEL, logging.INFO)
    app.logger.setLevel(level)
    for handler in app.logger.handlers:
        handler.setLevel(level)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"
        ))


def create_app():
    # Production validation happens before any database, model, or request
    # work. It deliberately fails closed rather than creating a weak session
    # key or silently falling back to a source-tree runtime path.
    config.validate_runtime_configuration()

    app = Flask(
        __name__,
        template_folder="frontend/templates",
        static_folder="frontend/static",
    )
    app.jinja_env.globals["asset_version"] = config.ASSET_VERSION
    app.jinja_env.globals["jordan_governorates"] = config.JORDAN_GOVERNORATES
    app.jinja_env.globals["voice_partial_interval_ms"] = config.VOICE_PARTIAL_INTERVAL_MS
    app.jinja_env.globals["voice_client_max_recording_seconds"] = config.VOICE_CLIENT_MAX_RECORDING_SECONDS

    app.secret_key = config.get_secret_key()
    if not (os.environ.get("FLASK_SECRET_KEY") or os.environ.get("SECRET_KEY")):
        app.logger.warning(
            "No session key is configured; using an isolated development-only key."
        )

    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = config.SESSION_COOKIE_SECURE
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=4)
    app.config["MAX_CONTENT_LENGTH"] = config.VOICE_MAX_UPLOAD_BYTES
    app.config["DEBUG"] = False if config.IS_PRODUCTION else config.DEBUG
    app.config["TESTING"] = False
    app.config["PROPAGATE_EXCEPTIONS"] = False if config.IS_PRODUCTION else None

    _configure_logging(app)

    # Forwarded headers are ignored unless the operator explicitly declares
    # how many reverse proxies are trusted. This is required for HTTPS-aware
    # session behavior behind a proxy, without trusting arbitrary clients.
    if config.TRUSTED_PROXY_COUNT:
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=config.TRUSTED_PROXY_COUNT,
            x_proto=config.TRUSTED_PROXY_COUNT,
            x_host=config.TRUSTED_PROXY_COUNT,
        )

    @app.before_request
    def _restore_session_from_remember_me():
        # Runs before the CSRF check (registered next) so a restored
        # session is available immediately, including on this request.
        load_logged_in_user_from_remember_cookie()

    init_csrf(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(booking_bp)
    app.register_blueprint(trip_request_bp)
    app.register_blueprint(demand_admin_bp)
    app.register_blueprint(maintenance_bp)
    app.register_blueprint(review_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(voice_bp)
    app.register_blueprint(nlp_bp)
    app.register_blueprint(notification_bp)
    app.register_blueprint(pricing_bp)

    @app.get("/health")
    def health():
        """Minimal liveness/readiness probe without operational disclosure."""
        try:
            conn = get_db_connection()
            try:
                conn.execute("SELECT 1")
            finally:
                conn.close()
        except sqlite3.Error:
            app.logger.warning("Health check database connectivity failed")
            return jsonify({"status": "unavailable"}), 503
        return jsonify({"status": "ok"})

    @app.errorhandler(500)
    def internal_server_error(_error):
        # Do not return tracebacks, SQL errors, paths, or configuration data
        # to production users. Detailed exception logging remains server-side.
        app.logger.exception("Unhandled application error")
        if request.path.startswith("/api/"):
            return jsonify({"error": "An unexpected server error occurred."}), 500
        return "An unexpected server error occurred.", 500

    @app.after_request
    def _rotate_remember_cookie(response):
        # See auth_routes.load_logged_in_user_from_remember_cookie(): when a
        # session was just restored from a remember-me cookie, the token was
        # already rotated server-side — this writes the NEW cookie value out
        # so the old (now-deleted) one isn't reused on the next request.
        if session.pop("_pending_remember_rotation", False):
            cookie_value = remember_me.issue_token(session["user_id"])
            response.set_cookie(
                remember_me.COOKIE_NAME,
                cookie_value,
                max_age=remember_me.COOKIE_MAX_AGE_DAYS * 24 * 60 * 60,
                httponly=True,
                samesite="Lax",
                secure=app.config["SESSION_COOKIE_SECURE"],
            )
        return response

    initialize_database()

    # Version 3 — Voice Assistant: load Whisper once at startup and reuse
    # it for every request. Never crashes app boot if voice deps aren't
    # installed yet; the /api/voice endpoint reports a clean 503 instead.
    from backend.speech import audio_utils, whisper_engine

    audio_utils.ensure_voice_dirs()
    audio_utils.cleanup_stale_temp_files()
    whisper_engine.preload()

    # Project Two, Phase Two — Arabic Natural Language Intelligence:
    # load AraBERT/MARBERT once at startup (Part Six: Performance). Same
    # never-crash-app-boot guarantee as whisper_engine.preload() above —
    # if the models aren't available (not installed, or no network access
    # to download weights on first run), the Hybrid Pipeline transparently
    # uses the existing Rule-Based NLP instead. See
    # backend/nlp/model_loader.py for details.
    from backend.nlp import model_loader

    model_loader.preload()

    return app


if __name__ == "__main__":
    app = create_app()

    # ngrok remains a local-development convenience only. Production is
    # served by the documented WSGI entry point, never Flask's dev server.
    ngrok_token = os.environ.get("NGROK_AUTH_TOKEN") if not config.IS_PRODUCTION else None
    if ngrok_token:
        try:
            from pyngrok import ngrok

            ngrok.set_auth_token(ngrok_token)
            public_url = ngrok.connect(5000)
            print("\n" + "=" * 50)
            print(f"Public URL: {public_url}")
            print("=" * 50 + "\n")
        except Exception as exc:
            print(f"[ngrok] Public tunnel skipped: {exc}")
    elif not config.IS_PRODUCTION:
        print("[ngrok] Skipped — set NGROK_AUTH_TOKEN to expose a public tunnel.")

    if config.IS_PRODUCTION:
        raise SystemExit(
            "Production mode does not use the Flask development server. "
            "Run `waitress-serve --listen=0.0.0.0:5000 wsgi:app` instead."
        )
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
