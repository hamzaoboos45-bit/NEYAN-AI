"""Source-level regressions for the browser-owned voice input boundary."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def test_chat_exposes_one_accessible_primary_microphone_and_text_composer():
    page = _read("frontend/templates/chat.html")
    assert page.count('id="voiceMicBtn"') == 1
    assert 'aria-label="بدء الإدخال الصوتي"' in page
    assert 'id="chatInput"' in page and 'id="chatSendBtn"' in page
    for removed in ("voiceStopBtn", "voiceReplayBtn", "voiceTranscribeBtn", "voiceUploadTriggerBtn", "voiceTranscriptText"):
        assert removed not in page


def test_voice_uses_browser_recognition_then_a_transient_server_fallback_and_normal_sender():
    source = _read("frontend/static/js/voice.js")
    assert "window.SpeechRecognition||window.webkitSpeechRecognition" in source
    assert "active.interimResults=true" in source
    assert "window.sendMessage()" in source
    assert 'fetch("/api/voice/transcribe"' in source
    assert "MediaRecorder" in source and "getUserMedia" in source
    assert "TripRequestService" not in source and "/api/chat" not in source
    assert 'form.append("partial","1")' in source
    assert "partialActive" in source and "pendingPartial" in source
    assert "partialRevision" in source and "abortPartial" in source
    assert "renderVoiceText(partialVoiceText)" in source


def test_voice_guards_empty_permission_error_rapid_tap_and_navigation_paths():
    source = _read("frontend/static/js/voice.js")
    for guard in ("!Recognition&&!canRecord()", "if(!transcript||submitted||cancelled)", 'event.error==="not-allowed"', 'state===STATE.FALLBACK_RECORDING', 'window.addEventListener("pagehide",cancel)'):
        assert guard in source
    assert "mediaRecorder.start(PARTIAL_INTERVAL_MS)" in source
    assert "MAX_RECORDING_MS" in source


def test_voice_styles_use_shared_tokens_and_reduced_motion_support():
    css = _read("frontend/static/css/voice.css")
    assert "var(--input-border)" in css and "var(--accent)" in css
    assert "prefers-reduced-motion" in css
