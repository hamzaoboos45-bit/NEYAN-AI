"""Gate 5 source/runtime-boundary coverage for browser-owned speech input."""
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    previous = config.DATABASE_PATH
    config.DATABASE_PATH = path
    try:
        from app import create_app

        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as test_client:
            yield test_client
    finally:
        config.DATABASE_PATH = previous
        if os.path.exists(path):
            os.remove(path)


def source(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def identity(client, session_id="gate5"):
    from backend.security.csrf import SESSION_KEY

    with client.session_transaction() as session:
        session.update(user_id=1, role="customer", session_id=session_id, **{SESSION_KEY: "gate5-csrf"})


def test_voice_feature_detection_single_init_and_accessible_unavailable_state():
    script = source("frontend/static/js/voice.js")
    page = source("frontend/templates/chat.html")
    css = source("frontend/static/css/voice.css")
    assert script.count("window.NeyanVoiceInput") == 2  # initialization guard and test surface
    assert "window.SpeechRecognition||window.webkitSpeechRecognition" in script
    assert "disable(true)" in script and 'aria-disabled",value?"true":"false"' in script
    assert "LISTENING_BROWSER" in script and "FALLBACK_RECORDING" in script and "FINAL_TRANSCRIBING" in script
    assert page.count('id="voiceMicBtn"') == 1
    assert 'type="button"' in page and 'aria-label="بدء الإدخال الصوتي"' in page
    assert ".voice-mic-btn:disabled" in css and "prefers-reduced-motion" in css


def test_interim_final_deduplication_and_network_fallback_reuses_the_composer():
    script = source("frontend/static/js/voice.js")
    for required in (
        "active.interimResults=true",
        "finalByIndex[i]=phrase",
        "if(!transcript||submitted||cancelled)",
        'event.error==="not-allowed"',
        'event.error==="audio-capture"',
        'event.error==="no-speech"',
        'event.error==="network"',
        "restore()",
        "MediaRecorder",
        "navigator.mediaDevices.getUserMedia",
        "FALLBACK_RECORDING",
        'fetch("/api/voice/transcribe"',
        'document.addEventListener("neyan:chatready"',
        "ar-JO",
        "en-US",
        'form.append("partial","1")',
        "partialRevision",
        "pendingPartial",
        "mediaRecorder.start(PARTIAL_INTERVAL_MS)",
    ):
        assert required in script
    assert 'fetch("/api/chat"' not in script
    assert script.count("window.sendMessage()") == 1
    assert "window.sendMessage()" in script


def test_final_voice_text_crosses_the_normal_authenticated_chat_boundary(client):
    """Voice passes text to sendMessage; this is the same server boundary it reaches."""
    identity(client)
    response = client.post("/api/chat", json={"message": "بدي صيانة", "csrf_token": "gate5-csrf"})
    assert response.status_code == 200
    assert "صيانة" in response.get_json()["reply"]
    history = client.get("/api/chat/history")
    assert history.status_code == 200
    assert any(row["sender"] == "user" and row["message_text"] == "بدي صيانة" for row in history.get_json()["messages"])


def test_voice_transcription_is_transient_and_has_no_business_logic_path():
    script = source("frontend/static/js/voice.js")
    routes = source("routes/chat_routes.py")
    assert "voice_booking" not in script
    assert "voice_booking" not in routes
    assert "message" in routes and "/api/chat" in routes
    voice_routes = source("routes/voice_routes.py")
    assert 'fetch("/api/voice/transcribe"' in script and "FormData" in script
    assert "save_history=False" in voice_routes
    assert 'request.form.get("partial", "0")' in voice_routes
    endpoint = voice_routes[voice_routes.index("def api_voice_transcribe"):voice_routes.index("# ─────────────────────────────────────────────────────────", voice_routes.index("def api_voice_transcribe"))]
    assert "chatbot" not in endpoint.lower()
    assert "TripRequestService" not in endpoint
