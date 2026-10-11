"""
routes/voice_routes.py — Version 3 Voice Assistant API.

    POST   /api/voice                  transcribe a recorded/uploaded clip
    POST   /api/tts                    synthesize speech for a bot reply
    GET    /api/voice/voices           list available TTS voices
    GET    /api/voice/settings         fetch this user's voice settings
    POST   /api/voice/settings         save this user's voice settings
    GET    /api/voice/history          list this user's past recordings
    GET    /api/voice/history/<id>/audio  replay a past recording
    DELETE /api/voice/history/<id>     delete a past recording

All routes require login (same session-based auth as the rest of the
platform) and never modify anything in backend/chatbot.py — voice input
is transcribed here, then handed to the *existing* /api/chat endpoint
exactly as if the user had typed it, from the frontend (frontend/voice.js).
"""

import os

from flask import Blueprint, jsonify, request, send_file, session

import config
from backend.speech import audio_utils, recorder, tts_engine
from database import voice_db
from routes.auth_helpers import login_required

voice_bp = Blueprint("voice", __name__)


def _error(message, code="error", status=400):
    return jsonify({"error": message, "code": code}), status


# ─────────────────────────────────────────────────────────
# Speech-to-Text
# ─────────────────────────────────────────────────────────
@voice_bp.route("/api/voice", methods=["POST"])
@login_required
def api_voice():
    """
    POST /api/voice
    multipart/form-data:
        audio     — the recorded or drag-and-dropped audio file (required)
        language  — optional ISO language code override (default: config)
        save      — optional "0" to skip saving to voice history
    Returns: { "transcription": "...", "duration_seconds": 3.2, "voice_id": 17 }
    """
    if "audio" not in request.files:
        return _error("Missing 'audio' field in form-data.", code="no_file", status=400)

    language = request.form.get("language") or None
    save_history = request.form.get("save", "1") != "0"

    try:
        result = recorder.process_voice_upload(
            file_storage=request.files["audio"],
            user_id=session.get("user_id"),
            session_id=session.get("session_id"),
            language=language,
            save_history=save_history,
        )
    except recorder.VoicePipelineError as exc:
        return _error(exc.message, code=exc.code, status=exc.status)
    except Exception as exc:  # last line of defense — always return clean JSON
        return _error(f"Unexpected server error: {exc}", code="server_error", status=500)

    return jsonify(result)


@voice_bp.route("/api/voice/transcribe", methods=["POST"])
@login_required
def api_voice_transcribe():
    """Transcribe one transient browser recording and return plain text only.

    This endpoint intentionally does not call Chat, booking, maintenance, or
    history services.  The browser passes its returned text to the existing
    Chat sender, preserving the normal authenticated business boundary.
    """
    if "audio" not in request.files:
        return _error("Missing audio recording.", code="no_file", status=400)

    language = (request.form.get("language") or "").strip().lower()
    if language not in {"ar", "en"}:
        return _error("Unsupported transcription language.", code="invalid_language", status=400)
    partial = request.form.get("partial", "0")
    if partial not in {"0", "1"}:
        return _error("Invalid transcription mode.", code="invalid_partial_mode", status=400)

    try:
        result = recorder.process_voice_upload(
            file_storage=request.files["audio"],
            user_id=session.get("user_id"),
            session_id=session.get("session_id"),
            language=language,
            save_history=False,
            require_transient_mime=True,
            skip_vad=True,
        )
    except recorder.VoicePipelineError as exc:
        return _error(exc.message, code=exc.code, status=exc.status)
    except Exception:
        # Never expose an implementation path, decoder message, or provider
        # configuration to the browser.
        return _error("Voice transcription is temporarily unavailable.", code="transcription_failed", status=503)

    transcript = (result.get("transcription") or "").strip()
    if not transcript:
        return _error("No speech was detected.", code="no_speech_detected", status=422)
    response = jsonify({"transcript": transcript})
    timing = result.get("timing_ms") or {}
    if timing:
        response.headers["Server-Timing"] = ", ".join(
            f"{name};dur={value}" for name, value in timing.items()
        )
    return response


# ─────────────────────────────────────────────────────────
# Text-to-Speech
# ─────────────────────────────────────────────────────────
@voice_bp.route("/api/tts", methods=["POST"])
@login_required
def api_tts():
    """
    POST /api/tts
    JSON body: { "text": "...", "voice_id": "...", "rate": 175, "volume": 1.0 }
    Returns: audio/wav stream
    """
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return _error("Missing 'text' field.", code="no_text", status=400)

    try:
        wav_path = tts_engine.synthesize(
            text=text,
            voice_id=data.get("voice_id"),
            rate=data.get("rate"),
            volume=data.get("volume", 1.0),
        )
    except tts_engine.TTSNotAvailableError as exc:
        return _error(exc.message, code="tts_unavailable", status=503)
    except ValueError as exc:
        return _error(str(exc), code="no_text", status=400)
    except RuntimeError as exc:
        return _error(str(exc), code="tts_failed", status=500)
    except Exception as exc:
        return _error(f"Unexpected server error: {exc}", code="server_error", status=500)

    try:
        response = send_file(wav_path, mimetype="audio/wav", as_attachment=False)
        response.call_on_close(lambda: audio_utils.safe_delete(wav_path))
        return response
    except Exception as exc:
        audio_utils.safe_delete(wav_path)
        return _error(f"Could not stream synthesized audio: {exc}", code="server_error", status=500)


@voice_bp.route("/api/voice/voices", methods=["GET"])
@login_required
def api_voice_voices():
    try:
        voices = tts_engine.list_voices()
    except tts_engine.TTSNotAvailableError as exc:
        return _error(exc.message, code="tts_unavailable", status=503)
    return jsonify({"voices": voices})


# ─────────────────────────────────────────────────────────
# Settings
# ─────────────────────────────────────────────────────────
@voice_bp.route("/api/voice/settings", methods=["GET"])
@login_required
def api_get_voice_settings():
    return jsonify(voice_db.get_settings(session["user_id"]))


@voice_bp.route("/api/voice/settings", methods=["POST"])
@login_required
def api_save_voice_settings():
    data = request.get_json(silent=True) or {}
    voice_db.save_settings(session["user_id"], data)
    return jsonify({"status": "saved"})


# ─────────────────────────────────────────────────────────
# History
# ─────────────────────────────────────────────────────────
@voice_bp.route("/api/voice/history", methods=["GET"])
@login_required
def api_voice_history():
    entries = voice_db.list_history(session["user_id"])
    return jsonify({"history": entries})


@voice_bp.route("/api/voice/history/<int:voice_id>/audio", methods=["GET"])
@login_required
def api_voice_history_audio(voice_id):
    entry = voice_db.get_history_entry(voice_id, session["user_id"])
    if not entry:
        return _error("Recording not found.", code="not_found", status=404)

    path = os.path.join(config.VOICE_HISTORY_DIR, entry["audio_filename"])
    if not os.path.exists(path):
        return _error("Audio file no longer exists on the server.", code="not_found", status=404)

    return send_file(path, as_attachment=False)


@voice_bp.route("/api/voice/history/<int:voice_id>", methods=["DELETE"])
@login_required
def api_voice_history_delete(voice_id):
    entry = voice_db.get_history_entry(voice_id, session["user_id"])
    if not entry:
        return _error("Recording not found.", code="not_found", status=404)

    audio_utils.safe_delete(os.path.join(config.VOICE_HISTORY_DIR, entry["audio_filename"]))
    voice_db.delete_history_entry(voice_id, session["user_id"])
    return jsonify({"status": "deleted"})


# ─────────────────────────────────────────────────────────
# Error handlers scoped to this blueprint (large uploads, etc.)
# ─────────────────────────────────────────────────────────
@voice_bp.errorhandler(413)
def _voice_too_large(_exc):
    return _error("Audio file is too large.", code="file_too_large", status=413)
