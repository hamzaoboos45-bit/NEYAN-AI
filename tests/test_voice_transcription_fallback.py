"""Focused contract tests for transient server-side Voice fallback STT."""
import io
import os
import sys
import tempfile
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    original_path = config.DATABASE_PATH
    config.DATABASE_PATH = path
    try:
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as test_client:
            yield test_client
    finally:
        config.DATABASE_PATH = original_path
        if os.path.exists(path):
            os.remove(path)


def identity(client, token="voice-csrf"):
    from backend.security.csrf import SESSION_KEY
    with client.session_transaction() as session:
        session.update(user_id=1, role="customer", session_id="voice-fallback", **{SESSION_KEY: token})
    return token


def audio_form(content=b"audio", mimetype="audio/webm", filename="clip.webm", language="en"):
    return {"audio": (io.BytesIO(content), filename, mimetype), "language": language}


def test_transcription_requires_authenticated_session(client):
    from backend.security.csrf import SESSION_KEY
    with client.session_transaction() as session:
        session[SESSION_KEY] = "anonymous-csrf"
    response = client.post("/api/voice/transcribe", data=audio_form(), headers={"X-CSRFToken": "anonymous-csrf"})
    assert response.status_code == 401


def test_transcription_requires_csrf_and_audio(client):
    identity(client)
    assert client.post("/api/voice/transcribe", data=audio_form()).status_code == 400
    response = client.post("/api/voice/transcribe", data={"language": "en"}, headers={"X-CSRFToken": "voice-csrf"})
    assert response.status_code == 400
    assert response.get_json()["code"] == "no_file"


def test_transcription_rejects_invalid_mime_before_stt(client):
    token = identity(client)
    response = client.post("/api/voice/transcribe", data=audio_form(b"not audio", "text/plain"), headers={"X-CSRFToken": token})
    assert response.status_code == 415
    assert response.get_json()["code"] == "unsupported_mime"


def test_transcription_rejects_an_unknown_progressive_mode(client):
    token = identity(client)
    payload = audio_form()
    payload["partial"] = "later"
    response = client.post("/api/voice/transcribe", data=payload, headers={"X-CSRFToken": token})
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_partial_mode"


def test_transcription_rejects_oversized_upload_before_stt(client, monkeypatch):
    token = identity(client)
    monkeypatch.setattr(config, "VOICE_MAX_UPLOAD_BYTES", 3)
    response = client.post("/api/voice/transcribe", data=audio_form(b"four"), headers={"X-CSRFToken": token})
    assert response.status_code == 413
    assert response.get_json()["code"] == "file_too_large"


@patch("routes.voice_routes.recorder.process_voice_upload")
def test_transcription_returns_unicode_text_and_never_archives_audio(process, client):
    token = identity(client)
    process.return_value = {"transcription": "أريد حجز رحلة إلى العقبة"}
    response = client.post("/api/voice/transcribe", data=audio_form(language="ar"), headers={"X-CSRFToken": token})
    assert response.status_code == 200
    assert response.get_json() == {"transcript": "أريد حجز رحلة إلى العقبة"}
    assert process.call_args.kwargs["save_history"] is False
    assert process.call_args.kwargs["require_transient_mime"] is True


@patch("routes.voice_routes.recorder.process_voice_upload")
def test_progressive_transcription_is_text_only_and_never_archives_audio(process, client):
    token = identity(client)
    process.return_value = {"transcription": "نص جزئي"}
    payload = audio_form(language="ar")
    payload["partial"] = "1"
    response = client.post("/api/voice/transcribe", data=payload, headers={"X-CSRFToken": token})
    assert response.status_code == 200
    assert response.get_json() == {"transcript": "نص جزئي"}
    assert process.call_args.kwargs["save_history"] is False


@patch("routes.voice_routes.recorder.process_voice_upload")
def test_transcription_handles_provider_failure_and_empty_transcript(process, client):
    from backend.speech.recorder import VoicePipelineError
    token = identity(client)
    process.side_effect = VoicePipelineError("temporarily unavailable", code="whisper_unavailable", status=503)
    response = client.post("/api/voice/transcribe", data=audio_form(), headers={"X-CSRFToken": token})
    assert response.status_code == 503
    assert response.get_json()["code"] == "whisper_unavailable"
    process.side_effect = None
    process.return_value = {"transcription": "  "}
    response = client.post("/api/voice/transcribe", data=audio_form(), headers={"X-CSRFToken": token})
    assert response.status_code == 422
    assert response.get_json()["code"] == "no_speech_detected"


def test_transcription_route_has_no_chat_or_business_service_dependency():
    source = open(os.path.join(os.path.dirname(__file__), "..", "routes", "voice_routes.py"), encoding="utf-8").read()
    start = source.index('def api_voice_transcribe')
    section = source[start:source.index("# ─────────────────────────────────────────────────────────", start)]
    for forbidden in ("/api/chat", "ChatbotEngine", "TripRequestService", "Maintenance"):
        assert forbidden not in section
