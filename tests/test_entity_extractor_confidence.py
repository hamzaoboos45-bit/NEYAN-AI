"""
tests/test_entity_extractor_confidence.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from backend.nlp import entity_extractor, confidence, preprocessing


def _extract(raw_text):
    pre = preprocessing.preprocess(raw_text)
    return entity_extractor.extract(pre["normalized"], raw_text=pre["cleaned"])


class TestRouteExtraction:
    def test_from_to_with_cue_words(self):
        entities = _extract("اريد السفر من عمان الى اربد")
        assert entities["from_city"] == "عمان"
        assert entities["to_city"] == "إربد"

    def test_positional_fallback_two_cities_no_cue(self):
        entities = _extract("عمان اربد رحلة")
        assert entities["from_city"] == "عمان"
        assert entities["to_city"] == "إربد"

    def test_single_city_no_role_assigned(self):
        entities = _extract("عمان")
        assert entities.get("from_city") is None
        assert entities.get("to_city") is None
        assert entities["cities"] == ["عمان"]


class TestPassengerCountExtraction:
    def test_dual_form_word(self):
        entities = _extract("اريد مقعدين من عمان الى الزرقاء")
        assert entities["seats"] == 2

    def test_explicit_count_with_cue(self):
        entities = _extract("اريد حجز رحلة لثلاثة اشخاص")
        assert entities["seats"] == 3

    def test_date_not_confused_with_seats(self):
        # Regression test for a real bug found during integration testing:
        # a date adjacent to a seat-cue word must not leak its digits into
        # the passenger count.
        entities = _extract("اريد حجز رحلة من عمان الى اربد يوم 2025-08-01 لشخصين")
        assert entities["seats"] == 2
        assert entities["date"] == "2025-08-01"

    def test_no_cue_word_no_seats(self):
        entities = _extract("اريد حجز رحلة من عمان الى اربد بتاريخ 2025-08-01")
        assert entities.get("seats") is None


class TestDateExtractionSurvivesNormalization:
    def test_date_with_dashes_extracted(self):
        # Regression test: preprocessing strips punctuation for the
        # AI/intent layer, but date extraction must still work off the
        # less-aggressively-cleaned text.
        entities = _extract("موعد الصيانة يوم 2025-09-10 صباحا")
        assert entities["date"] == "2025-09-10"


class TestServiceMaintenanceEntities:
    def test_oil_change_detected(self):
        entities = _extract("بدي تغيير زيت للسيارة")
        assert entities["service_type"] == "oil_change"


class TestEntitiesNeverRaise:
    def test_empty_string(self):
        assert entity_extractor.extract("") == {}

    def test_garbage_input(self):
        # Part Seven (Security): malformed/garbage input must never crash.
        result = entity_extractor.extract("!@#$%^&*()_+ 🚀🚀🚀 \x00\x01")
        assert isinstance(result, dict)


class TestConfidenceThreshold:
    def test_below_threshold_rejected(self):
        assert confidence.should_trust_ai("book_trip", 0.10) is False

    def test_above_threshold_accepted(self):
        original = config.NLP_CONFIDENCE_THRESHOLD
        config.NLP_CONFIDENCE_THRESHOLD = 0.5
        try:
            assert confidence.should_trust_ai("book_trip", 0.9) is True
        finally:
            config.NLP_CONFIDENCE_THRESHOLD = original

    def test_none_intent_rejected(self):
        assert confidence.should_trust_ai(None, 0.99) is False

    def test_none_confidence_rejected(self):
        assert confidence.should_trust_ai("book_trip", None) is False

    def test_nan_confidence_rejected(self):
        assert confidence.should_trust_ai("book_trip", float("nan")) is False

    def test_malformed_confidence_rejected(self):
        assert confidence.should_trust_ai("book_trip", "not-a-number") is False
