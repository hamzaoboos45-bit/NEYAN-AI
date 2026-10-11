"""
backend/speech/tts_engine.py — Local, offline Text-To-Speech using pyttsx3.

pyttsx3 wraps the OS-native speech engine (SAPI5 on Windows, NSSpeechSynthesizer
on macOS, espeak/espeak-ng on Linux) — no API key, no network call, no
per-minute cost. Available voices (and Arabic support) depend entirely on
what's installed on the host OS. On most Linux servers, installing
`espeak-ng` gives you a usable Arabic voice out of the box:

    sudo apt-get install espeak-ng

Known pyttsx3 quirk: reusing a single engine instance for many sequential
`runAndWait()` calls across a threaded Flask process is unreliable on some
platforms. To keep this rock solid in production we take a short-lived
lock and spin up a fresh engine per synthesis call — cheap for pyttsx3
(it doesn't load a heavy ML model like Whisper does) and avoids
"run loop already started" failures entirely.
"""

import os
import tempfile
import threading
import uuid

import config

_voices_cache = None
_engine_lock = threading.Lock()


class TTSNotAvailableError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def _import_pyttsx3():
    try:
        import pyttsx3
        return pyttsx3
    except ImportError as exc:
        raise TTSNotAvailableError(
            "pyttsx3 is not installed. Run `pip install pyttsx3` "
            "(Linux also needs `espeak-ng` installed system-wide)."
        ) from exc


def list_voices(force_refresh=False):
    """Returns [{id, name, languages}] for every system voice pyttsx3 finds."""
    global _voices_cache
    if _voices_cache is not None and not force_refresh:
        return _voices_cache

    pyttsx3 = _import_pyttsx3()
    with _engine_lock:
        engine = pyttsx3.init()
        try:
            raw_voices = engine.getProperty("voices") or []
            voices = []
            for v in raw_voices:
                languages = getattr(v, "languages", None) or []
                decoded_langs = []
                for lang in languages:
                    if isinstance(lang, bytes):
                        decoded_langs.append(lang.decode(errors="ignore"))
                    else:
                        decoded_langs.append(str(lang))
                voices.append({"id": v.id, "name": v.name, "languages": decoded_langs})
            _voices_cache = voices
        finally:
            engine.stop()
    return _voices_cache


def synthesize(text, voice_id=None, rate=None, volume=1.0):
    """
    Synthesizes `text` to a temporary WAV file and returns its path.
    Caller is responsible for deleting the file after streaming it
    (the /api/tts route does this via a Flask after_request cleanup).
    """
    if not text or not text.strip():
        raise ValueError("No text provided for speech synthesis.")

    text = text.strip()
    if len(text) > config.TTS_MAX_TEXT_LENGTH:
        text = text[: config.TTS_MAX_TEXT_LENGTH]

    pyttsx3 = _import_pyttsx3()

    out_dir = config.VOICE_TEMP_DIR
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"tts_{uuid.uuid4().hex}.wav")

    with _engine_lock:
        engine = pyttsx3.init()
        try:
            engine.setProperty("rate", rate or config.TTS_DEFAULT_RATE)
            engine.setProperty("volume", max(0.0, min(1.0, volume)))

            if voice_id:
                try:
                    engine.setProperty("voice", voice_id)
                except Exception:
                    pass  # fall back to default voice rather than failing the request

            engine.save_to_file(text, out_path)
            engine.runAndWait()
        except Exception as exc:
            raise RuntimeError(f"Text-to-speech synthesis failed: {exc}") from exc
        finally:
            engine.stop()

    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        raise RuntimeError("Text-to-speech produced no audio output.")

    return out_path
