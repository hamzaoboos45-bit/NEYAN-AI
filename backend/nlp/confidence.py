"""
backend/nlp/confidence.py — Confidence scoring + fallback decision.

One tiny, well-tested function is deliberately kept separate from
hybrid_pipeline.py so the "should we trust the AI or fall back to rules?"
decision is easy to unit test in isolation and easy to tune without
touching the orchestration logic.
"""

import config


def get_threshold() -> float:
    """Configurable confidence threshold (see config.NLP_CONFIDENCE_THRESHOLD).
    Kept as a function (not a bare constant import) so tests can monkeypatch
    config.NLP_CONFIDENCE_THRESHOLD and see the change take effect."""
    return getattr(config, "NLP_CONFIDENCE_THRESHOLD", 0.60)


def should_trust_ai(intent: str | None, confidence: float | None) -> bool:
    """
    Decide whether the AraBERT prediction is trustworthy enough to use
    directly, or whether the existing Rule-Based NLP should take over.

    Returns False (→ fall back to rules) whenever:
        - the AI layer didn't return a prediction at all (model unavailable,
          import error, etc. — intent is None)
        - the AI is not confident enough (confidence below threshold)
        - the AI's own answer is itself "unknown"/"general_conversation"
          with low signal (still respects genuinely confident matches)

    Never raises — a malformed confidence value is treated as "don't trust".
    """
    if not intent:
        return False
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        return False
    if confidence != confidence:  # NaN check without importing math
        return False
    return confidence >= get_threshold()
