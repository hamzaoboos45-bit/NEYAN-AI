"""
backend/speech/whisper_engine.py — Local Whisper STT.

The model is loaded exactly once (module-level singleton) and reused for
every /api/voice request. `preload()` is called once during app startup
(create_app) so the first user request doesn't pay the model-load cost.

If openai-whisper (or its ffmpeg dependency) isn't available, the engine
degrades to a clear, catchable error instead of crashing the whole app —
so the rest of the platform (V1/V2 chatbot, bookings, admin, etc.) keeps
working even on a machine that hasn't installed the voice extras yet.
"""

import threading

import config

_model = None
_loaded_engine = None
_load_lock = threading.Lock()
_load_error = None


class WhisperNotAvailableError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def _do_load():
    """Load the configured STT engine once for the process lifetime."""
    global _model, _loaded_engine, _load_error
    engine = config.VOICE_STT_ENGINE
    try:
        if engine == "faster-whisper":
            from faster_whisper import WhisperModel

            _model = WhisperModel(
                config.WHISPER_MODEL_SIZE,
                device=config.WHISPER_DEVICE,
                compute_type=config.WHISPER_COMPUTE_TYPE,
            )
        else:
            import whisper  # openai-whisper

            # fp16 is unavailable on ordinary CPU execution. The original
            # engine remains the compatibility default until an operator
            # explicitly selects the optional faster-whisper backend.
            _model = whisper.load_model(config.WHISPER_MODEL_SIZE, device=config.WHISPER_DEVICE)
        _loaded_engine = engine
        _load_error = None
    except ImportError as exc:
        package = "faster-whisper" if engine == "faster-whisper" else "openai-whisper"
        _load_error = f"{package} is not installed for VOICE_STT_ENGINE={engine}."
        raise WhisperNotAvailableError(_load_error) from exc
    except Exception as exc:
        _load_error = f"Failed to load {engine} model '{config.WHISPER_MODEL_SIZE}': {exc}"
        raise WhisperNotAvailableError(_load_error) from exc


def preload():
    """Call once at app startup. Never raises — logs and defers the real
    error to the first actual transcription request instead, so a missing
    voice dependency never prevents the Flask app from booting."""
    try:
        get_model()
        print(f"[Voice] {config.VOICE_STT_ENGINE} '{config.WHISPER_MODEL_SIZE}' model loaded and ready.")
    except WhisperNotAvailableError as exc:
        print(f"[Voice] WARNING — Whisper not ready yet: {exc.message}")


def get_model():
    """Thread-safe lazy singleton accessor. Loads once, reused forever."""
    global _model
    if _model is not None:
        return _model
    with _load_lock:
        if _model is None:
            # A failed dependency/model load must not be retried for every
            # audio request. A process restart is the deliberate recovery
            # boundary after an operator fixes the runtime dependency.
            if _load_error:
                raise WhisperNotAvailableError(_load_error)
            _do_load()
    return _model


def transcribe(path, language=None):
    """
    Transcribe an audio file at `path` (any format ffmpeg can decode:
    wav/webm/ogg/mp3/m4a). Returns the recognized text (stripped).
    Raises WhisperNotAvailableError or RuntimeError on failure.
    """
    model = get_model()
    lang = language or config.WHISPER_LANGUAGE
    try:
        if _loaded_engine == "faster-whisper":
            segments, _info = model.transcribe(path, language=lang, beam_size=5)
            return " ".join(segment.text.strip() for segment in segments if segment.text).strip()
        result = model.transcribe(path, language=lang, fp16=False)
        return (result.get("text") or "").strip()
    except Exception as exc:
        raise RuntimeError(f"Whisper transcription failed: {exc}") from exc
