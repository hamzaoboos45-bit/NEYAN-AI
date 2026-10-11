"""
backend/ai/arabert_placeholder.py — AraBERT integration hook.

This module is a STUB. It provides the exact same interface that
a real AraBERT/MARBERT model would use, so swapping in the real
model requires changing ONLY this file.

Future implementation steps:
1. Install: pip install transformers torch
2. Load: AutoTokenizer + AutoModelForSequenceClassification
3. Replace ai_classify() body with model inference
4. Replace transcribe_audio() with OpenAI Whisper

Architecture note:
- chatbot.py calls ai_classify() as a fallback after rule-based
- The rule-based system takes precedence (faster, cheaper)
- AI is only invoked when rules return 'unknown'
"""

from typing import Optional


# ─── Intent Classification ────────────────────────────────────

def ai_classify(text: str) -> str:
    """
    Classify user intent using AI model.

    STUB — always returns 'unknown'.

    Real implementation:
        tokens = tokenizer(text, return_tensors="pt", truncation=True)
        output = model(**tokens)
        label_id = output.logits.argmax().item()
        return id2label[label_id]
    """
    # TODO: Replace with AraBERT/MARBERT inference
    return "unknown"


# ─── Named Entity Recognition ─────────────────────────────────

def ai_extract_entities(text: str) -> dict:
    """
    Extract city names, dates, and numbers from Arabic text.

    STUB — returns empty dict.

    Real implementation would use MARBERT NER model to extract:
    - LOC (locations/cities)
    - DATE (travel dates)
    - NUM (seat counts)
    """
    # TODO: Replace with NER model
    return {"cities": [], "dates": [], "numbers": []}


# ─── Voice Transcription ─────────────────────────────────────

def transcribe_audio(audio_bytes: bytes, language: str = "ar") -> Optional[str]:
    """
    Transcribe Arabic audio to text using Whisper.

    STUB — returns None.

    Real implementation:
        import whisper
        model = whisper.load_model("medium")
        result = model.transcribe(audio_path, language=language)
        return result["text"]
    """
    # TODO: Replace with OpenAI Whisper integration
    return None


# ─── Sentiment Analysis ───────────────────────────────────────

def analyze_sentiment(text: str) -> str:
    """
    Detect customer sentiment for escalation logic.

    STUB — returns 'neutral'.
    Real: fine-tuned AraBERT on Arabic sentiment dataset.
    """
    # TODO: Replace with sentiment model
    return "neutral"
