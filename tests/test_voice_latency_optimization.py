"""Focused regressions for the Voice latency optimization boundary."""

from pathlib import Path
import os
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_browserless_voice_contract_covers_overlap_merge_prefix_and_single_send():
    result = subprocess.run(
        ["node", "tests/voice_runtime_contract.js"], cwd=ROOT,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "voice runtime contract passed" in result.stdout


def test_transient_voice_route_skips_duplicate_vad_and_returns_non_noisy_timing(monkeypatch):
    import config
    from app import create_app
    from backend.security.csrf import SESSION_KEY
    from routes.voice_routes import recorder
    import io

    original_database = config.DATABASE_PATH
    import tempfile
    handle, database = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    Path(database).unlink(missing_ok=True)
    try:
        config.DATABASE_PATH = database
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as client:
            with client.session_transaction() as session:
                session.update(user_id=1, role="customer", session_id="voice-timing", **{SESSION_KEY: "voice-timing-csrf"})
            observed = {}

            def process(**kwargs):
                observed.update(kwargs)
                return {"transcription": "hello", "timing_ms": {"validation": 1.2, "vad": 0.0, "inference": 4.8, "total": 6.1}}

            monkeypatch.setattr(recorder, "process_voice_upload", process)
            response = client.post(
                "/api/voice/transcribe",
                data={"audio": (io.BytesIO(b"audio"), "clip.webm", "audio/webm"), "language": "en", "partial": "1"},
                headers={"X-CSRFToken": "voice-timing-csrf"},
            )
        assert response.status_code == 200
        assert response.get_json() == {"transcript": "hello"}
        assert observed["skip_vad"] is True
        assert observed["save_history"] is False
        assert "inference;dur=4.8" in response.headers["Server-Timing"]
    finally:
        config.DATABASE_PATH = original_database
        Path(database).unlink(missing_ok=True)


def test_unavailable_stt_engine_error_is_cached_until_process_restart(monkeypatch):
    from backend.speech import whisper_engine

    original_model = whisper_engine._model
    original_error = whisper_engine._load_error
    original_engine = whisper_engine._loaded_engine
    calls = []
    try:
        monkeypatch.setattr(whisper_engine, "_model", None)
        monkeypatch.setattr(whisper_engine, "_load_error", "configured STT dependency is unavailable")
        monkeypatch.setattr(whisper_engine, "_do_load", lambda: calls.append("load"))
        with pytest.raises(whisper_engine.WhisperNotAvailableError):
            whisper_engine.get_model()
        assert calls == []
    finally:
        whisper_engine._model = original_model
        whisper_engine._load_error = original_error
        whisper_engine._loaded_engine = original_engine


def test_voice_source_keeps_singleton_configurable_engine_and_overlap_safe_merge():
    engine = (ROOT / "backend/speech/whisper_engine.py").read_text(encoding="utf-8")
    client = (ROOT / "frontend/static/js/voice.js").read_text(encoding="utf-8")
    recorder = (ROOT / "backend/speech/recorder.py").read_text(encoding="utf-8")
    assert '"faster-whisper"' in engine and "WhisperModel" in engine
    assert "if _load_error:" in engine
    assert "reconcileTranscript" in client and "collapseRepeatedPrefix" in client
    assert "skip_vad" in recorder and "timing_ms" in recorder
