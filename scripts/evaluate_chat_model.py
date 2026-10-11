"""Evaluate the frozen held-out set without retraining."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from backend import intents
from backend.nlp import intent_classifier
from backend.nlp.trained_intent_model import classify_many
from scripts.train_chat_model import metrics, read_dataset

def _canonical_rule(text: str) -> str:
    legacy = intents.classify(text)
    return next((canonical for canonical, mapped in intent_classifier.LEGACY_INTENT_MAP.items() if mapped == legacy), "unknown")

def evaluate() -> dict:
    rows = read_dataset(); labels = sorted({row["intent"] for row in rows}); held_out = [row for row in rows if row["split"] == "test"]
    baseline = [_canonical_rule(row["text"]) for row in held_out]
    # This exactly follows the production hybrid order: deterministic signals
    # first, then the fine-tuned model only for unresolved messages.
    unresolved_positions = [index for index, prediction in enumerate(baseline) if prediction == "unknown"]
    inferred = classify_many([held_out[index]["text"] for index in unresolved_positions])
    combined = list(baseline)
    for index, (intent, _confidence) in zip(unresolved_positions, inferred):
        combined[index] = intent or "unknown"
    return {"frozen_test_rows": len(held_out), "baseline_rule_metrics": metrics(held_out, baseline, labels), "hybrid_fine_tuned_metrics": metrics(held_out, combined, labels)}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate()
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
