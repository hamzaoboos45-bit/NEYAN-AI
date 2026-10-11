"""
backend/speech/recorder.py — Orchestrates the server-side half of the
voice pipeline for both live recordings and drag-and-dropped files:

    validate upload -> save temp file -> VAD check -> Whisper transcribe
        -> delete temp file -> (optionally) persist to voice_history

Both POST /api/voice (live mic recording) and drag-and-drop upload share
this exact function, per the spec: "the uploaded audio should follow the
same Whisper pipeline."
"""

import os
import shutil
import time
import uuid

import config
from backend.speech import audio_utils, vad, whisper_engine
from database import voice_db


class VoicePipelineError(Exception):
    def __init__(self, message, code="pipeline_error", status=400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


def process_voice_upload(
    file_storage, user_id, session_id, language=None, save_history=True,
    require_transient_mime=False, skip_vad=False,
):
    """
    Runs the full pipeline for one uploaded/recorded audio file.

    Returns:
        {
            "transcription": str,
            "duration_seconds": float,
            "speech_ratio": float,
            "voice_id": int | None,   # voice_history row id, if saved
        }

    Raises VoicePipelineError with a clean, user-facing message + code
    for every failure mode (validation, no speech, whisper failure, etc.)
    """
    started = time.perf_counter()
    try:
        validator = audio_utils.validate_transient_recording if require_transient_mime else audio_utils.validate_upload
        ext = validator(file_storage)
    except audio_utils.AudioValidationError as exc:
        raise VoicePipelineError(exc.message, code=exc.code, status=exc.status) from exc

    validation_ms = (time.perf_counter() - started) * 1000
    with audio_utils.temp_audio_file(file_storage, ext) as temp_path:
        # 1) Voice Activity Detection — reject silence/noise early with a
        #    clear, specific error instead of wasting a Whisper pass on it.
        vad_started = time.perf_counter()
        if skip_vad:
            # Browser fallback recordings are transient and never archived.
            # Whisper already decodes the file for inference, so avoiding a
            # second ffmpeg decode removes the largest avoidable latency from
            # progressive and final fallback requests. Empty speech still
            # produces the established no_speech_detected response below.
            vad_result = {"duration_seconds": None, "speech_ratio": None}
        else:
            try:
                vad_result = vad.analyze_speech_presence(temp_path)
            except vad.VADError as exc:
                raise VoicePipelineError(str(exc), code="decode_failed", status=422) from exc

            if vad_result["duration_seconds"] > config.VOICE_MAX_RECORDING_SECONDS:
                raise VoicePipelineError(
                    f"Recording exceeds the {config.VOICE_MAX_RECORDING_SECONDS}s limit.",
                    code="recording_too_long",
                    status=413,
                )

            if not vad_result["has_speech"]:
                raise VoicePipelineError(
                    "No speech detected. Please try again closer to the microphone.",
                    code="no_speech_detected",
                    status=422,
                )
        vad_ms = (time.perf_counter() - vad_started) * 1000

        # 2) Whisper transcription (model loaded once, reused every call).
        inference_started = time.perf_counter()
        try:
            transcription = whisper_engine.transcribe(temp_path, language=language)
        except whisper_engine.WhisperNotAvailableError as exc:
            raise VoicePipelineError(exc.message, code="whisper_unavailable", status=503) from exc
        except RuntimeError as exc:
            raise VoicePipelineError(str(exc), code="whisper_failed", status=500) from exc

        inference_ms = (time.perf_counter() - inference_started) * 1000
        if not transcription:
            raise VoicePipelineError(
                "Whisper could not recognize any words in this recording.",
                code="no_speech_detected",
                status=422,
            )

        # 3) Persist to voice history (permanent copy, separate from the
        #    temp file which is deleted the moment we leave this `with`).
        voice_id = None
        if save_history and user_id is not None:
            if vad_result["duration_seconds"] is None:
                raise VoicePipelineError("Transient recordings cannot be archived.", code="invalid_voice_mode")
            voice_id = _archive_to_history(
                temp_path, ext, user_id, session_id, transcription, vad_result["duration_seconds"]
            )

    return {
        "transcription": transcription,
        "duration_seconds": vad_result["duration_seconds"],
        "speech_ratio": vad_result["speech_ratio"],
        "voice_id": voice_id,
        "timing_ms": {
            "validation": round(validation_ms, 2),
            "vad": round(vad_ms, 2),
            "inference": round(inference_ms, 2),
            "total": round((time.perf_counter() - started) * 1000, 2),
        },
    }


def _archive_to_history(temp_path, ext, user_id, session_id, transcription, duration_seconds):
    os.makedirs(config.VOICE_HISTORY_DIR, exist_ok=True)
    archived_name = f"{uuid.uuid4().hex}.{ext}"
    archived_path = os.path.join(config.VOICE_HISTORY_DIR, archived_name)
    shutil.copyfile(temp_path, archived_path)

    return voice_db.save_history_entry(
        user_id=user_id,
        session_id=session_id,
        audio_filename=archived_name,
        transcription=transcription,
        duration_seconds=duration_seconds,
    )
