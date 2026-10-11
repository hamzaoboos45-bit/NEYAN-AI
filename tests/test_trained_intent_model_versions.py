"""Version-selection regressions for local V2 operator training."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import config
from backend.nlp import trained_intent_model
from scripts import evaluate_chat_model_v2


class TrainedIntentModelVersionTests(unittest.TestCase):
    def tearDown(self):
        trained_intent_model.reset_for_tests()

    def test_v1_selection_preserves_existing_artifact_names(self):
        self.assertEqual(trained_intent_model.artifact_spec("v1"), {"metadata_file": "chat_intent_metadata.json", "state_file": "arabert_intent_delta.pt", "format": "neyan-arabert-intent-head-v1"})

    def test_v2_selection_uses_only_v2_artifact_names(self):
        self.assertEqual(trained_intent_model.artifact_spec("v2"), {"metadata_file": "chat_intent_metadata_v2.json", "state_file": "arabert_intent_delta_v2.pt", "format": "neyan-arabert-intent-delta-v2"})

    def test_v2_missing_artifact_falls_back_without_claiming_availability(self):
        missing_directory = str(Path(__file__).resolve().parent / "_missing_v2_model_fixture")
        with patch.object(config, "TRAINED_CHAT_MODEL_PATH", missing_directory):
            trained_intent_model.reset_for_tests()
            self.assertFalse(trained_intent_model.is_available("v2"))
            self.assertEqual(trained_intent_model.classify_for_version("بدي أحجز", "v2"), (None, 0.0))
            self.assertIn("chat_intent_metadata_v2.json", trained_intent_model.load_error("v2"))

    def test_v2_metadata_validation_requires_v2_format_version_and_state_file(self):
        metadata = {"format": "neyan-arabert-intent-delta-v2", "dataset_version": "v2", "state_file": "arabert_intent_delta_v2.pt", "labels": ["book_trip"]}
        trained_intent_model.validate_metadata(metadata, "v2")
        with self.assertRaises(ValueError):
            trained_intent_model.validate_metadata({**metadata, "state_file": "arabert_intent_delta.pt"}, "v2")
        with self.assertRaises(ValueError):
            trained_intent_model.validate_metadata({**metadata, "dataset_version": "v1"}, "v2")

    def test_production_classify_uses_configured_version(self):
        captured = []
        with patch.object(config, "TRAINED_CHAT_MODEL_VERSION", "v1"), patch.object(trained_intent_model, "classify_for_version", side_effect=lambda text, version: (captured.append(version) or ("greeting", 0.9))):
            self.assertEqual(trained_intent_model.classify("مرحبا"), ("greeting", 0.9))
        self.assertEqual(captured, ["v1"])

    def test_evaluator_calls_v2_explicitly_not_runtime_default(self):
        rows = [{"text": "اختبار", "intent": "greeting"}]
        with patch.object(trained_intent_model, "classify_many_for_version", return_value=[("greeting", 0.91)]) as classifier:
            self.assertEqual(evaluate_chat_model_v2.v2_predictions(rows), [("greeting", 0.91)])
        classifier.assert_called_once_with(["اختبار"], "v2")
