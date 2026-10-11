"""
backend/nlp/hybrid_pipeline.py — orchestrates the full Hybrid NLP Pipeline
(Part Five), matching the required architecture exactly:

    User
      -> Voice/Text                     (routes/voice_routes.py already
                                          transcribes voice to text before
                                          this pipeline ever runs)
      -> Preprocessing                  (backend/nlp/preprocessing.py)
      -> AraBERT Intent Classification  (backend/nlp/intent_classifier.py)
      -> Confidence Score
           |-- >= threshold --> use AraBERT's intent
           |-- <  threshold --> Rule-Based Fallback (backend/intents.py,
                                 UNCHANGED — this phase never touches it)
      -> MARBERT Entity Extraction      (backend/nlp/entity_extractor.py)
      -> Conversation Memory            (merge_entities(), used by
                                          backend/chatbot.py)
      -> Business Logic                 (backend/chatbot.py — untouched)
      -> Bot Response

This module is the ONLY new integration point backend/chatbot.py needs to
import from — everything else in this package is an implementation detail
behind analyze().
"""

from dataclasses import dataclass, field
import logging
import time

from backend import intents as rule_intents
from backend.nlp import confidence as confidence_module
from backend.nlp import entity_extractor, intent_classifier, preprocessing

_logger = logging.getLogger(__name__)


@dataclass
class NLPResult:
    intent: str                 # canonical intent name (Part One's taxonomy)
    legacy_intent: str           # name backend/chatbot.py's dispatch table uses
    confidence: float
    source: str                  # "ai" | "rule_based"
    normalized_text: str
    entities: dict = field(default_factory=dict)

    def to_api_dict(self) -> dict:
        """Shape matches Part Eight's documented POST /api/nlp/analyze
        response exactly (intent / confidence / normalized_text / entities)."""
        return {
            "intent": self.intent,
            "confidence": self.confidence,
            "normalized_text": self.normalized_text,
            "entities": self.entities,
            "source": self.source,
        }


def analyze(raw_text: str) -> NLPResult:
    """
    Run the full hybrid pipeline on one user message. Never raises —
    every stage degrades independently (AI unavailable -> rule-based;
    NER model unavailable -> gazetteer/regex only), per Part Six/Seven.
    """
    started = time.perf_counter()
    pre = preprocessing.preprocess(raw_text or "")
    preprocess_done = time.perf_counter()
    normalized = pre["normalized"]

    # Obvious, bounded conversational/domain signals are resolved before any
    # model call.  This keeps common one-word requests fast and deterministic
    # while retaining AraBERT for messages that the reviewed rules cannot
    # safely interpret.
    legacy_from_rules = rule_intents.classify(normalized)
    if legacy_from_rules != "unknown":
        canonical_intent = _legacy_to_canonical(legacy_from_rules)
        # This is an exact deterministic match marker for the existing API
        # contract, not a calibrated statistical probability.
        confidence = 1.0
        source = "rule_based"
        intent_done = time.perf_counter()
    else:
        ai_intent, ai_confidence = intent_classifier.classify(normalized)
        intent_done = time.perf_counter()
        if confidence_module.should_trust_ai(ai_intent, ai_confidence):
            canonical_intent = ai_intent
            confidence = ai_confidence
            source = "ai"
        else:
            canonical_intent = "unknown"
            confidence = 0.0
            source = "rule_based"

    legacy_intent = intent_classifier.to_legacy_intent(canonical_intent)
    entities = entity_extractor.extract(normalized, raw_text=pre["cleaned"])
    entity_done = time.perf_counter()
    _logger.info(
        "NLP timing preprocess=%.2fms intent=%.2fms entities=%.2fms total=%.2fms",
        (preprocess_done - started) * 1000,
        (intent_done - preprocess_done) * 1000,
        (entity_done - intent_done) * 1000,
        (entity_done - started) * 1000,
    )

    return NLPResult(
        intent=canonical_intent,
        legacy_intent=legacy_intent,
        confidence=confidence,
        source=source,
        normalized_text=normalized,
        entities=entities,
    )


_REVERSE_LEGACY_MAP = None


def _legacy_to_canonical(legacy_intent: str) -> str:
    global _REVERSE_LEGACY_MAP
    if _REVERSE_LEGACY_MAP is None:
        # Several canonical names can map to the same legacy name
        # (trip_search/trip_information -> search_trip); prefer the
        # first-declared canonical name for a stable, deterministic
        # reverse mapping.
        _REVERSE_LEGACY_MAP = {}
        for canonical, legacy in intent_classifier.LEGACY_INTENT_MAP.items():
            _REVERSE_LEGACY_MAP.setdefault(legacy, canonical)
    return _REVERSE_LEGACY_MAP.get(legacy_intent, legacy_intent)


def merge_entities(ctx: dict, entities: dict, *, overwrite: bool = False) -> dict:
    """
    Part Three (Context integration): fold newly-extracted entities into
    the existing conversation context WITHOUT overwriting anything the
    user already told the bot earlier in the conversation. "If an entity
    is already known, do NOT ask for it again" — the corollary enforced
    here is that a later, possibly-noisier extraction never clobbers an
    earlier, already-confirmed value either.
    """
    ctx = dict(ctx or {})
    for key in ("from_city", "to_city", "date", "time", "seats", "trip_class",
                "service_type", "vehicle_type", "location",
                "passenger_name"):
        value = entities.get(key)
        if value is not None and (overwrite or ctx.get(key) is None):
            ctx[key] = value
    return ctx
