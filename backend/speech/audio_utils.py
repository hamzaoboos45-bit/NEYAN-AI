"""
backend/speech/audio_utils.py — Validation, safe storage, and cleanup for
uploaded / recorded audio. Kept dependency-free (only stdlib + Werkzeug,
both already required by Flask) so this file works even before optional
speech dependencies (whisper, pyttsx3) are installed.
"""

import os
import time
import uuid
from contextlib import contextmanager

from werkzeug.utils import secure_filename

import config


class AudioValidationError(Exception):
    """Raised for any client-facing audio validation failure."""

    def __init__(self, message, code="invalid_audio", status=400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


def ensure_voice_dirs():
    """Create the voice temp/history directories if they don't exist yet."""
    os.makedirs(config.VOICE_TEMP_DIR, exist_ok=True)
    os.makedirs(config.VOICE_HISTORY_DIR, exist_ok=True)


def get_extension(filename):
    if not filename or "." not in filename:
        return ""
    return filename.rsplit(".", 1)[1].lower()


def validate_upload(file_storage):
    """
    Validate a Werkzeug FileStorage object before it ever touches disk.
    Raises AudioValidationError on any problem; returns a clean extension
    string on success.
    """
    if file_storage is None or file_storage.filename == "":
        raise AudioValidationError("No audio file was provided.", code="no_file")

    ext = get_extension(file_storage.filename)
    if ext not in config.VOICE_ALLOWED_EXTENSIONS:
        raise AudioValidationError(
            f"Unsupported audio format: '.{ext}'. Allowed formats: "
            f"{', '.join(sorted(config.VOICE_ALLOWED_EXTENSIONS))}.",
            code="unsupported_format",
            status=415,
        )

    # Determine size without loading the whole file into memory.
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)

    if size == 0:
        raise AudioValidationError("Uploaded audio file is empty.", code="empty_file")

    if size > config.VOICE_MAX_UPLOAD_BYTES:
        max_mb = config.VOICE_MAX_UPLOAD_BYTES // (1024 * 1024)
        raise AudioValidationError(
            f"Audio file exceeds the {max_mb}MB size limit.",
            code="file_too_large",
            status=413,
        )

    return ext


def validate_transient_recording(file_storage):
    """Validate a browser MediaRecorder upload for one-time transcription.

    The older voice-history route accepts supported file extensions for
    backwards compatibility.  The fallback route is deliberately stricter:
    it requires both a supported extension and a browser audio MIME type
    before writing the clip to disk.  MIME metadata is not treated as proof
    that a file is decodable (Whisper/ffmpeg remains the final decoder), but
    it prevents obvious non-audio form uploads from entering the pipeline.
    """
    ext = validate_upload(file_storage)
    mimetype = (file_storage.mimetype or "").lower().split(";", 1)[0].strip()
    allowed_mimetypes = {
        "wav": {"audio/wav", "audio/x-wav", "audio/wave"},
        "webm": {"audio/webm", "video/webm"},
        "ogg": {"audio/ogg", "application/ogg"},
        "mp3": {"audio/mpeg", "audio/mp3"},
        "m4a": {"audio/mp4", "audio/x-m4a", "video/mp4"},
    }
    if mimetype not in allowed_mimetypes[ext]:
        raise AudioValidationError(
            "Unsupported audio content type.", code="unsupported_mime", status=415
        )
    return ext


def save_temp_upload(file_storage, ext):
    """Persist an incoming upload to a uniquely named temp file. Returns the path."""
    ensure_voice_dirs()
    safe_name = f"{uuid.uuid4().hex}_{secure_filename(file_storage.filename)}"
    if not safe_name.endswith(f".{ext}"):
        safe_name = f"{safe_name}.{ext}"
    path = os.path.join(config.VOICE_TEMP_DIR, safe_name)
    file_storage.save(path)
    return path


@contextmanager
def temp_audio_file(file_storage, ext):
    """
    Context manager: saves the upload to a temp path, yields it, and
    guarantees deletion afterward — even if transcription raises.
    """
    path = save_temp_upload(file_storage, ext)
    try:
        yield path
    finally:
        safe_delete(path)


def safe_delete(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        # Deletion failures shouldn't crash a request; log-worthy in production.
        pass


def cleanup_stale_temp_files(max_age_seconds=3600):
    """
    Housekeeping: remove any temp audio files older than max_age_seconds.
    Safe to call periodically (e.g. once per app startup) since /voice
    always tries to delete its own temp file immediately after use.
    """
    ensure_voice_dirs()
    now = time.time()
    for name in os.listdir(config.VOICE_TEMP_DIR):
        path = os.path.join(config.VOICE_TEMP_DIR, name)
        try:
            if os.path.isfile(path) and (now - os.path.getmtime(path)) > max_age_seconds:
                os.remove(path)
        except OSError:
            continue
