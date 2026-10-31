"""Evaluate V2 artifacts without exposing the challenge test to training.

The script emits complete machine-readable evidence only after an artifact is
provided.  It deliberately does not train, tune thresholds, or modify files.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "training_data"))

from backend import intents
from backend.nlp import intent_classifier
from backend.nlp import trained_intent_model
from training_data.dataset_v2 import LABELS, dataset_hash, read_jsonl, validate_isolation
from scripts.train_chat_model import metrics


def canonical_rule(text: str) -> str:
    legacy = intents.classify(text)
    return next((name for name, mapped in intent_classifier.LEGACY_INTENT_MAP.items() if mapped == legacy), "unknown")


def prediction_report(rows: list[dict], predictions: list[tuple[str | None, float]]) -> dict:
    labels = list(LABELS)
    resolved = [intent or "unknown" for intent, _ in predictions]
    mistakes = [{"text": row["text"], "expected": row["intent"], "predicted": predicted, "confidence": confidence} for row, (predicted, confidence) in zip(rows, predictions) if row["intent"] != (predicted or "unknown")]
    confidences = [confidence for _, confidence in predictions]
    return {"metrics": metrics(rows, resolved, labels), "misclassified_examples": mistakes, "confidence": {"count": len(confidences), "mean": round(sum(confidences) / len(confidences), 4) if confidences else 0.0, "min": min(confidences, default=0.0), "max": max(confidences, default=0.0)}}


def v2_predictions(rows: list[dict]) -> list[tuple[str | None, float]]:
    """Always use V2, independent of production's deliberately-V1 default."""
    return trained_intent_model.classify_many_for_version([row["text"] for row in rows], "v2")


def hybrid_predictions(rows: list[dict], model_predictions: list[tuple[str | None, float]]) -> list[tuple[str | None, float]]:
    resolved = []
    for row, model_prediction in zip(rows, model_predictions):
        rule = canonical_rule(row["text"])
        resolved.append((rule, 1.0) if rule != "unknown" else model_prediction)
    return resolved


def suite(rows: list[dict]) -> dict:
    rules = [(canonical_rule(row["text"]), 1.0) for row in rows]
    model = v2_predictions(rows)
    return {"rule_only": prediction_report(rows, rules), "model_only": prediction_report(rows, model), "hybrid": prediction_report(rows, hybrid_predictions(rows, model))}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=ROOT / "training_data" / "chat_intents_v2.jsonl")
    parser.add_argument("--challenge", type=Path, default=ROOT / "training_data" / "chat_intents_challenge_test.jsonl")
    parser.add_argument("--legacy", type=Path, default=ROOT / "training_data" / "chat_intents.jsonl")
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "CHAT_MODEL_EVALUATION_V2.json")
    args = parser.parse_args()
    v2 = read_jsonl(args.dataset, {"train", "validation"})
    challenge = read_jsonl(args.challenge, {"challenge"})
    integrity = validate_isolation(v2, challenge)
    legacy = read_jsonl(args.legacy, {"train", "validation", "test"})
    legacy_test = [row for row in legacy if row["split"] == "test"]
    if not trained_intent_model.is_available("v2"):
        raise RuntimeError(f"V2 artifact could not be loaded: {trained_intent_model.load_error('v2') or 'unknown error'}")
    result = {"dataset_v2": integrity, "legacy_test_hash": dataset_hash(legacy_test), "artifact_version": "v2", "legacy_test": suite(legacy_test), "challenge_test": suite(challenge)}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    # Windows consoles may default to cp1252; JSON output remains readable
    # without making dataset generation depend on terminal encoding.
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
