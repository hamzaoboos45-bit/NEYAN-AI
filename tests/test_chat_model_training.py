"""Regression coverage for the reviewed AraBERT chat-training integration."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.nlp import hybrid_pipeline, intent_classifier
from scripts.train_chat_model import DATASET, read_dataset


def test_training_dataset_is_valid_balanced_and_uses_current_labels():
    rows = read_dataset(DATASET)
    assert len(rows) == 195
    for split, expected in (("train", 8), ("validation", 2), ("test", 3)):
        split_rows = [row for row in rows if row["split"] == split]
        counts = {label: sum(row["intent"] == label for row in split_rows) for label in intent_classifier.LEGACY_INTENT_MAP if label != "unknown"}
        assert set(counts.values()) == {expected}


def test_deployable_delta_metadata_declares_current_backbone_and_labels():
    path = os.path.join(os.path.dirname(__file__), "..", "backend", "nlp", "models", "chat_intent_metadata.json")
    with open(path, encoding="utf-8") as handle:
        metadata = json.load(handle)
    assert metadata["format"] == "neyan-arabert-intent-head-v1"
    assert metadata["base_model"] == "aubmindlab/bert-base-arabertv02"
    assert metadata["trainable_layers"] if "trainable_layers" in metadata else metadata["training_configuration"]["trainable_layers"] == ["classifier"]
    assert set(metadata["labels"]) == set(intent_classifier.LEGACY_INTENT_MAP) - {"unknown"}


def test_deterministic_rule_remains_first_and_never_calls_model(monkeypatch):
    monkeypatch.setattr(intent_classifier.trained_intent_model, "classify", lambda _text: ("maintenance_request", 0.99))
    result = hybrid_pipeline.analyze("مرحبا")
    assert result.intent == "greeting"
    assert result.source == "rule_based"


def test_fine_tuned_prediction_is_only_an_intent_signal(monkeypatch):
    monkeypatch.setattr(intent_classifier.trained_intent_model, "classify", lambda _text: ("trip_search", 0.9))
    result = hybrid_pipeline.analyze("عبارة غير معروفة للقواعد")
    assert result.intent == "trip_search"
    assert result.legacy_intent == "search_trip"
    assert result.source == "ai"
    # No database lookup, booking, price, seat, or other business write is
    # performed by the hybrid analyzer itself.
    assert result.entities == {}
