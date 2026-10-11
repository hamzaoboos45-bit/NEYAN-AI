"""
backend/nlp/intent_classifier.py — AraBERT intent classification (Part One).

── Why embedding similarity, not a trained classification head ──
A supervised AraBERT classification head needs a labeled training set for
this project's specific 16-intent schema, which doesn't exist yet (this
phase's brief is to build the *pipeline*, not collect/label training
data). Training on scratch-initialized labels would produce fake,
meaningless confidence scores — worse than being honest about the
limitation.

Instead, this classifier encodes the user's message with AraBERT and
compares it (cosine similarity) against a small bank of representative
example phrases per intent (built from backend/intents.py's own keyword
lists, so the two layers stay conceptually aligned rather than diverging).
This is a legitimate, standard zero-shot-style technique, gives genuine
(if heuristic) confidence scores, and — critically — degrades safely: if
AraBERT can't be loaded, classify() returns (None, 0.0) and the caller
(hybrid_pipeline.py) falls straight through to the existing Rule-Based
NLP, exactly per the required architecture.

Swapping this out for a properly fine-tuned classifier later (once
labeled conversation logs exist — see the new nlp_analysis_log table)
only requires changing this file; hybrid_pipeline.py's contract
(text -> (intent, confidence)) stays the same.
"""

import threading
import time
import logging

import config
from backend import intents as rule_intents
from backend.nlp import model_loader, trained_intent_model
from backend.nlp.preprocessing import normalize_arabic

# ─── Canonical intent taxonomy (Part One's required list) ──────────────────
# Mapped down to the existing internal names backend/chatbot.py already
# dispatches on, so NOTHING in the state machine has to be renamed.
# 'complaint' and 'general_conversation' are new — chatbot.py gets two new,
# purely additive handler entries for them (see backend/chatbot.py).
LEGACY_INTENT_MAP = {
    "greeting":             "greeting",
    "goodbye":              "goodbye",
    "book_trip":            "booking",
    "cancel_booking":       "cancel_booking",
    "trip_search":          "search_trip",
    "trip_information":     "search_trip",
    "company_information":  "ask_companies",
    "maintenance_request":  "maintenance",
    "complaint":            "complaint",
    "help":                 "help",
    "price_inquiry":        "ask_price",
    "availability_inquiry": "ask_available_seats",
    "confirmation":         "confirm",
    "cancellation":         "cancel",
    "general_conversation": "general_conversation",
    "unknown":               "unknown",
}

# Example anchor phrases per canonical intent. Seeded from backend/intents.py's
# own keyword lists (no duplication of the *words themselves* — imported
# directly) plus a few natural full sentences, since a sentence encoder
# benefits from sentence-shaped examples, not just bare keywords.
_EXAMPLES = {
    "greeting": rule_intents.GREETING_KEYWORDS + ["مرحبا كيفك اليوم"],
    "goodbye": rule_intents.GOODBYE_KEYWORDS + ["شكرا لمساعدتك مع السلامة"],
    "book_trip": rule_intents.BOOKING_KEYWORDS + ["أريد حجز رحلة من عمان الى اربد"],
    "cancel_booking": rule_intents.CANCEL_BOOKING_KEYWORDS,
    "trip_search": rule_intents.SEARCH_TRIP_KEYWORDS + ["ما هي الرحلات المتاحة اليوم"],
    "trip_information": ["معلومات عن الرحلة", "كم تستغرق الرحلة", "ما تفاصيل الرحلة"],
    "company_information": rule_intents.ASK_COMPANIES_KEYWORDS,
    "maintenance_request": rule_intents.MAINTENANCE_KEYWORDS + ["سيارتي تحتاج صيانة"],
    "complaint": [
        "عندي شكوى", "أريد تقديم شكوى", "الخدمة سيئة جداً", "لست راضياً عن الخدمة",
        "الموظف كان غير مهذب", "الرحلة تأخرت كثيراً ولم يعتذر أحد", "أشتكي من جودة الخدمة",
        "this is a complaint", "the service was terrible",
    ],
    "help": rule_intents.HELP_KEYWORDS,
    "price_inquiry": rule_intents.ASK_PRICE_KEYWORDS,
    "availability_inquiry": rule_intents.ASK_SEATS_KEYWORDS,
    "confirmation": rule_intents.CONFIRM_KEYWORDS,
    "cancellation": rule_intents.CANCEL_KEYWORDS,
    "general_conversation": [
        "كيف حالك", "شو الأخبار", "احكيلي نكتة", "شو رأيك بالطقس اليوم",
        "how are you", "tell me something interesting",
    ],
}

_lock = threading.Lock()
_reference_embeddings = None  # dict[intent] -> torch.Tensor, built lazily once
_logger = logging.getLogger(__name__)


def _build_reference_embeddings():
    """Encode every example phrase once and average per intent. Cached at
    module scope for the lifetime of the process (Part Six: load once)."""
    import torch

    embeddings = {}
    for intent, examples in _EXAMPLES.items():
        vectors = [model_loader.embed_text(normalize_arabic(ex)) for ex in examples]
        embeddings[intent] = torch.stack(vectors).mean(dim=0)
    return embeddings


def _get_reference_embeddings():
    global _reference_embeddings
    if _reference_embeddings is not None:
        return _reference_embeddings
    with _lock:
        if _reference_embeddings is None:
            started = time.perf_counter()
            _reference_embeddings = _build_reference_embeddings()
            _logger.info(
                "NLP reference embeddings initialized in %.2f ms",
                (time.perf_counter() - started) * 1000,
            )
    return _reference_embeddings


def preload_reference_embeddings() -> None:
    """Warm immutable intent anchors once after a successful model preload."""
    _get_reference_embeddings()


def classify(normalized_text: str):
    """
    Classify user intent using AraBERT sentence embeddings.

    Returns (canonical_intent: str | None, confidence: float).
    (None, 0.0) means "AraBERT unavailable or produced no usable signal —
    the caller must fall back to the Rule-Based NLP." This function NEVER
    raises; every failure mode degrades to that tuple.
    """
    if not normalized_text or not normalized_text.strip():
        return None, 0.0

    # The compact supervised artifact is the first probabilistic layer.  It is
    # deliberately optional: a missing/invalid file returns ``(None, 0.0)``
    # and leaves the established AraBERT then deterministic fallbacks intact.
    trained_intent, trained_confidence = trained_intent_model.classify(normalized_text)
    if trained_intent:
        return trained_intent, trained_confidence
    if not config.ENABLE_AI_NLP:
        return None, 0.0

    try:
        import torch

        reference = _get_reference_embeddings()
        query_vec = model_loader.embed_text(normalized_text)

        best_intent, best_score = None, -1.0
        for intent, ref_vec in reference.items():
            score = torch.nn.functional.cosine_similarity(
                query_vec.unsqueeze(0), ref_vec.unsqueeze(0)
            ).item()
            if score > best_score:
                best_intent, best_score = intent, score

        # Cosine similarity for sentence-pair semantic match rarely exceeds
        # ~0.9 or drops below ~0.3 in practice for this kind of short-text
        # comparison; rescale to a 0..1 confidence band so the configured
        # threshold (config.NLP_CONFIDENCE_THRESHOLD) is meaningful rather
        # than requiring near-1.0 similarity to ever fire.
        confidence = max(0.0, min(1.0, (best_score - 0.3) / (0.9 - 0.3)))
        return best_intent, round(confidence, 4)

    except model_loader.AraBERTNotAvailableError:
        return None, 0.0
    except Exception:
        # Defensive catch-all: Part Seven (Security) — malformed input or
        # any unexpected inference error must never crash the chatbot.
        return None, 0.0


def to_legacy_intent(canonical_intent: str) -> str:
    """Map a canonical AraBERT intent label to the legacy internal name
    backend/chatbot.py's state machine already dispatches on."""
    return LEGACY_INTENT_MAP.get(canonical_intent, canonical_intent)
