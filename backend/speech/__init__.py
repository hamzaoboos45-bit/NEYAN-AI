"""
backend/speech — Version 3 Voice Assistant engine.

Modules:
    whisper_engine.py — local Whisper STT, loaded once and reused
    tts_engine.py      — local pyttsx3 TTS, loaded once and reused
    vad.py             — energy-based voice-activity / silence detection
    audio_utils.py     — validation, safe filenames, cleanup helpers
    recorder.py        — orchestrates upload -> validate -> transcribe -> persist
"""
