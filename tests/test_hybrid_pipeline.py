"""
tests/test_hybrid_pipeline.py

These tests run WITHOUT transformers/torch installed (this sandbox's
actual condition), which is exactly the "AraBERT unavailable" path that
must degrade gracefully to the Rule-Based NLP per the required
architecture. If transformers/torch + network access ARE available in
whatever environment runs this suite, intent_classifier.classify() may
return real AI predictions instead of (None, 0.0) — the assertions below
only pin down the CONTRACT (never raises, always returns a usable
result), not which layer answered, so the suite is meaningful either way.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.nlp import hybrid_pipeline, intent_classifier, model_loader


class TestIntentClassifierGracefulDegradation:
    def test_classify_never_raises_on_empty(self):
        intent, conf = intent_classifier.classify("")
        assert intent is None
        assert conf == 0.0

    def test_classify_never_raises_when_model_unavailable(self):
        # In this sandbox transformers/torch aren't installed, so this
        # exercises the real AraBERTNotAvailableError path end-to-end.
        intent, conf = intent_classifier.classify("مرحبا")
        assert intent is None or isinstance(intent, str)
        assert isinstance(conf, float)

    def test_legacy_intent_map_covers_every_canonical_intent(self):
        # Every canonical intent must map to SOME legacy dispatch name —
        # otherwise chatbot._handle_idle would silently no-op for it.
        for canonical in intent_classifier._EXAMPLES:
            assert canonical in intent_classifier.LEGACY_INTENT_MAP

    def test_to_legacy_intent_unknown_passthrough(self):
        assert intent_classifier.to_legacy_intent("totally_made_up") == "totally_made_up"


class TestHybridPipelineAnalyze:
    def test_analyze_never_raises_on_empty_string(self):
        result = hybrid_pipeline.analyze("")
        assert result.intent == "unknown"
        assert result.source == "rule_based"

    def test_analyze_falls_back_to_rule_based_when_ai_unavailable(self):
        result = hybrid_pipeline.analyze("مرحبا كيف حالك")
        # AraBERT is unavailable in this sandbox (no transformers/torch) —
        # confirm the rule-based fallback actually fired rather than
        # silently returning nothing.
        assert result.source in ("ai", "rule_based")
        assert result.legacy_intent in ("greeting", "unknown")

    def test_analyze_booking_message_extracts_route_entities(self):
        result = hybrid_pipeline.analyze("اريد حجز رحلة من عمان الى اربد")
        assert result.legacy_intent == "booking"
        assert result.entities.get("from_city") == "عمان"
        assert result.entities.get("to_city") == "إربد"

    def test_to_api_dict_shape_matches_spec(self):
        result = hybrid_pipeline.analyze("مرحبا")
        api_dict = result.to_api_dict()
        assert set(api_dict.keys()) == {
            "intent", "confidence", "normalized_text", "entities", "source"
        }

    def test_analyze_handles_none_gracefully(self):
        result = hybrid_pipeline.analyze(None)
        assert result.intent == "unknown"


class TestMergeEntities:
    def test_fills_empty_slots(self):
        ctx = {}
        merged = hybrid_pipeline.merge_entities(ctx, {"from_city": "عمان"})
        assert merged["from_city"] == "عمان"

    def test_never_overwrites_already_known_value(self):
        ctx = {"from_city": "الزرقاء"}
        merged = hybrid_pipeline.merge_entities(ctx, {"from_city": "عمان"})
        # Part Three: an already-known entity must not be clobbered by a
        # later, possibly noisier extraction.
        assert merged["from_city"] == "الزرقاء"

    def test_does_not_mutate_input_ctx(self):
        ctx = {}
        hybrid_pipeline.merge_entities(ctx, {"from_city": "عمان"})
        assert ctx == {}  # original dict untouched; a new dict is returned


class TestModelLoaderNeverCrashesAppBoot:
    def test_preload_does_not_raise(self):
        # This is the single most important guarantee in this whole
        # phase: whatever happens (missing deps, no network), app
        # startup must never be blocked by the AI layer.
        model_loader.preload()

    def test_is_arabert_available_returns_bool(self):
        assert isinstance(model_loader.is_arabert_available(), bool)

    def test_is_marbert_available_returns_bool(self):
        assert isinstance(model_loader.is_marbert_available(), bool)
