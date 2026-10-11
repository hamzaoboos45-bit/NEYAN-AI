"""
backend/speech/vad.py — Server-side Voice Activity Detection.

Real-time VAD (used to auto-stop the microphone while the user is
speaking) happens client-side in voice.js via the Web Audio API, since
that's where the live mic stream lives.

This module provides a lightweight, dependency-light *server-side* check
used right after upload/transcription: did this audio actually contain
speech, or is it silence / noise? It reuses Whisper's own ffmpeg-based
decoder (whisper.audio.load_audio) so no extra audio library is required
beyond openai-whisper + a working `ffmpeg` binary on PATH.
"""

import numpy as np

FRAME_MS = 30
SAMPLE_RATE = 16000  # Whisper always decodes to 16kHz mono


class VADError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def _load_pcm(path):
    try:
        import whisper.audio as whisper_audio
    except ImportError as exc:
        raise VADError(
            "openai-whisper is not installed. Run `pip install -U openai-whisper` "
            "and ensure `ffmpeg` is on PATH."
        ) from exc

    try:
        return whisper_audio.load_audio(path, sr=SAMPLE_RATE)
    except Exception as exc:  # ffmpeg decode failure, corrupt file, etc.
        raise VADError(f"Could not decode audio file: {exc}") from exc


def analyze_speech_presence(path, silence_threshold=0.012, min_speech_ratio=0.03):
    """
    Returns a dict:
        {
            "has_speech": bool,
            "duration_seconds": float,
            "speech_ratio": float,   # fraction of frames above the energy threshold
        }

    `silence_threshold` is an RMS amplitude threshold in [0, 1]. Audio
    where fewer than `min_speech_ratio` of frames exceed it is treated
    as "no speech detected".
    """
    samples = _load_pcm(path)
    duration_seconds = float(len(samples) / SAMPLE_RATE) if len(samples) else 0.0

    if duration_seconds == 0.0:
        return {"has_speech": False, "duration_seconds": 0.0, "speech_ratio": 0.0}

    frame_len = int(SAMPLE_RATE * FRAME_MS / 1000)
    if frame_len <= 0:
        frame_len = 480

    num_frames = max(1, len(samples) // frame_len)
    speech_frames = 0

    for i in range(num_frames):
        chunk = samples[i * frame_len:(i + 1) * frame_len]
        if chunk.size == 0:
            continue
        rms = float(np.sqrt(np.mean(np.square(chunk))))
        if rms >= silence_threshold:
            speech_frames += 1

    speech_ratio = speech_frames / num_frames
    return {
        "has_speech": speech_ratio >= min_speech_ratio,
        "duration_seconds": round(duration_seconds, 2),
        "speech_ratio": round(speech_ratio, 4),
    }
