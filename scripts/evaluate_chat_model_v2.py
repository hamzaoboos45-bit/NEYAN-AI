"""Evaluate a trained NEYAN NLP V2 artifact on untouched test data.

This script NEVER trains, tunes, or modifies the model. It explicitly loads
the supplied V2 artifact directory instead of relying on the production
runtime loader, so V1 cannot be evaluated accidentally.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "training_data"))

import config
from backend import intents
from backend.nlp import intent_classifier
from scripts.train_chat_model import metrics
from training_data.dataset_v2 import (
    LABELS,
    dataset_hash,
    read_jsonl,
    validate_isolation,
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        type=Path,
        default=ROOT / "training_data" / "chat_intents_v2.jsonl",
    )
    parser.add_argument(
        "--challenge",
        type=Path,
        default=ROOT / "training_data" / "chat_intents_challenge_test.jsonl",
    )
    parser.add_argument(
        "--legacy",
        type=Path,
        default=ROOT / "training_data" / "chat_intents.jsonl",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=ROOT / "backend" / "nlp" / "models",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "docs" / "CHAT_MODEL_EVALUATION_V2.json",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=ROOT / "docs" / "CHAT_MODEL_EVALUATION_V2.md",
    )
    parser.add_argument("--batch-size", type=int, default=32)
    return parser.parse_args()


def canonical_rule(text: str) -> str:
    legacy = intents.classify(text)
    return next(
        (
            name
            for name, mapped in intent_classifier.LEGACY_INTENT_MAP.items()
            if mapped == legacy
        ),
        "unknown",
    )


def _augmented_metrics(rows, predictions, labels):
    result = metrics(rows, predictions, labels)
    per_class = result["per_class"]
    result["macro_precision"] = round(
        sum(item["precision"] for item in per_class.values()) / len(labels),
        4,
    )
    result["macro_recall"] = round(
        sum(item["recall"] for item in per_class.values()) / len(labels),
        4,
    )
    return result


def prediction_report(rows, predictions):
    labels = list(LABELS)
    resolved = [intent or "unknown" for intent, _ in predictions]

    mistakes = [
        {
            "text": row["text"],
            "expected": row["intent"],
            "predicted": predicted or "unknown",
            "confidence": round(float(confidence), 4),
        }
        for row, (predicted, confidence) in zip(rows, predictions)
        if row["intent"] != (predicted or "unknown")
    ]

    confidences = [float(confidence) for _, confidence in predictions]
    correct_confidences = [
        float(confidence)
        for row, (predicted, confidence) in zip(rows, predictions)
        if row["intent"] == (predicted or "unknown")
    ]
    incorrect_confidences = [
        float(confidence)
        for row, (predicted, confidence) in zip(rows, predictions)
        if row["intent"] != (predicted or "unknown")
    ]

    def summary(values):
        if not values:
            return {
                "count": 0,
                "mean": 0.0,
                "min": 0.0,
                "max": 0.0,
            }
        return {
            "count": len(values),
            "mean": round(sum(values) / len(values), 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
        }

    return {
        "metrics": _augmented_metrics(rows, resolved, labels),
        "misclassified_examples": mistakes,
        "confidence": {
            "all": summary(confidences),
            "correct": summary(correct_confidences),
            "incorrect": summary(incorrect_confidences),
        },
    }


class V2Model:
    def __init__(self, artifact_dir: Path):
        try:
            import torch
            from transformers import (
                AutoModelForSequenceClassification,
                AutoTokenizer,
            )
        except ImportError as exc:
            raise RuntimeError(
                "V2 evaluation requires torch and transformers."
            ) from exc

        self.torch = torch
        self.artifact_dir = artifact_dir
        self.metadata_path = artifact_dir / "chat_intent_metadata_v2.json"

        if not self.metadata_path.exists():
            raise FileNotFoundError(
                f"Missing V2 metadata: {self.metadata_path}"
            )

        self.metadata = json.loads(
            self.metadata_path.read_text(encoding="utf-8")
        )

        if self.metadata.get("format") != "neyan-arabert-intent-delta-v2":
            raise ValueError(
                "Invalid V2 metadata format: "
                f"{self.metadata.get('format')!r}"
            )

        self.labels = list(self.metadata.get("labels") or [])
        if self.labels != list(LABELS):
            raise ValueError(
                "V2 artifact labels do not match the current 15-label schema."
            )

        state_file = self.metadata.get("state_file")
        if not state_file:
            raise ValueError("V2 metadata has no state_file.")

        self.state_path = artifact_dir / state_file
        if not self.state_path.exists():
            raise FileNotFoundError(
                f"Missing V2 state artifact: {self.state_path}"
            )

        base_model = (
            self.metadata.get("base_model")
            or config.ARABERT_MODEL_NAME
        )
        self.max_length = int(
            self.metadata.get("max_sequence_length", 96)
        )

        self.device = torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )

        self.tokenizer = AutoTokenizer.from_pretrained(base_model)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            base_model,
            num_labels=len(self.labels),
            ignore_mismatched_sizes=True,
        )

        state = torch.load(
            self.state_path,
            map_location="cpu",
            weights_only=True,
        )

        if not isinstance(state, dict) or not state:
            raise ValueError("V2 state artifact is empty or invalid.")

        if not any(key.startswith("classifier.") for key in state):
            raise ValueError(
                "V2 state artifact does not contain classifier parameters."
            )

        incompatible = self.model.load_state_dict(state, strict=False)
        if incompatible.unexpected_keys:
            raise ValueError(
                "Unexpected V2 artifact keys: "
                + ", ".join(incompatible.unexpected_keys[:10])
            )

        self.model = self.model.to(self.device)
        self.model.eval()

    def predict_many(self, texts, batch_size=32):
        torch = self.torch
        predictions = []

        with torch.no_grad():
            for start in range(0, len(texts), batch_size):
                batch = texts[start : start + batch_size]
                tokens = self.tokenizer(
                    batch,
                    return_tensors="pt",
                    truncation=True,
                    max_length=self.max_length,
                    padding=True,
                )
                tokens = {
                    key: value.to(self.device)
                    for key, value in tokens.items()
                }

                probabilities = torch.softmax(
                    self.model(**tokens).logits,
                    dim=-1,
                )
                values, indices = torch.max(probabilities, dim=-1)

                predictions.extend(
                    (
                        self.labels[int(index)],
                        round(float(value), 4),
                    )
                    for value, index in zip(
                        values.detach().cpu().tolist(),
                        indices.detach().cpu().tolist(),
                    )
                )

        return predictions

    def benchmark(self, texts, limit=100):
        torch = self.torch
        sample = list(texts[:limit])
        if not sample:
            return {
                "count": 0,
                "mean_ms": 0.0,
                "median_ms": 0.0,
                "p95_ms": 0.0,
            }

        # Warm-up.
        self.predict_many(sample[: min(5, len(sample))], batch_size=1)

        timings = []
        for text in sample:
            if self.device.type == "cuda":
                torch.cuda.synchronize()
            started = time.perf_counter()
            self.predict_many([text], batch_size=1)
            if self.device.type == "cuda":
                torch.cuda.synchronize()
            timings.append((time.perf_counter() - started) * 1000.0)

        ordered = sorted(timings)
        p95_index = min(
            len(ordered) - 1,
            max(0, int(round(0.95 * len(ordered) + 0.5)) - 1),
        )

        return {
            "count": len(timings),
            "mean_ms": round(statistics.mean(timings), 2),
            "median_ms": round(statistics.median(timings), 2),
            "p95_ms": round(ordered[p95_index], 2),
            "device": str(self.device),
        }


def rule_predictions(rows):
    return [
        (
            predicted if predicted != "unknown" else None,
            1.0 if predicted != "unknown" else 0.0,
        )
        for predicted in (canonical_rule(row["text"]) for row in rows)
    ]


def hybrid_predictions(rows, model_predictions, threshold):
    combined = []
    for row, (model_intent, model_confidence) in zip(
        rows,
        model_predictions,
    ):
        rule_intent = canonical_rule(row["text"])

        if rule_intent != "unknown":
            combined.append((rule_intent, 1.0))
        elif model_intent and float(model_confidence) >= threshold:
            combined.append((model_intent, float(model_confidence)))
        else:
            combined.append((None, 0.0))

    return combined


def markdown_summary(result):
    challenge_model = result["model_only_challenge"]["metrics"]
    challenge_hybrid = result["hybrid_challenge"]["metrics"]
    legacy_model = result["model_only_legacy_test"]["metrics"]
    legacy_hybrid = result["hybrid_legacy_test"]["metrics"]

    def pct(value):
        return f"{value * 100:.2f}%"

    return f"""# NEYAN NLP V2 Evaluation

## Artifact
- Directory: `{result["artifact"]["directory"]}`
- Base model: `{result["artifact"]["base_model"]}`
- Best validation epoch: `{result["artifact"]["best_epoch"]}`
- Device: `{result["artifact"]["device"]}`
- Confidence threshold: `{result["hybrid_confidence_threshold"]}`

## Untouched Challenge Test
- Samples: {result["challenge_count"]}
- Model-only Accuracy: **{pct(challenge_model["accuracy"])}**
- Model-only Macro F1: **{pct(challenge_model["macro_f1"])}**
- Model-only Weighted F1: **{pct(challenge_model["weighted_f1"])}**
- Hybrid Accuracy: **{pct(challenge_hybrid["accuracy"])}**
- Hybrid Macro F1: **{pct(challenge_hybrid["macro_f1"])}**
- Hybrid Weighted F1: **{pct(challenge_hybrid["weighted_f1"])}**

## Legacy Test
- Samples: {result["legacy_test_count"]}
- Model-only Accuracy: **{pct(legacy_model["accuracy"])}**
- Model-only Macro F1: **{pct(legacy_model["macro_f1"])}**
- Hybrid Accuracy: **{pct(legacy_hybrid["accuracy"])}**
- Hybrid Macro F1: **{pct(legacy_hybrid["macro_f1"])}**

## Latency
- Mean: {result["latency"]["mean_ms"]} ms
- Median: {result["latency"]["median_ms"]} ms
- P95: {result["latency"]["p95_ms"]} ms

## Integrity
The challenge corpus was loaded only by this evaluation script after the
trained artifact already existed. Training/model selection must remain based
only on the train + validation corpus.
"""


def main():
    args = parse_args()

    v2 = read_jsonl(args.dataset, {"train", "validation"})
    challenge = read_jsonl(args.challenge, {"challenge"})
    integrity = validate_isolation(v2, challenge)

    legacy = read_jsonl(
        args.legacy,
        {"train", "validation", "test"},
    )
    legacy_test = [
        row for row in legacy if row["split"] == "test"
    ]

    model = V2Model(args.artifact_dir)

    challenge_texts = [row["text"] for row in challenge]
    legacy_texts = [row["text"] for row in legacy_test]

    challenge_model = model.predict_many(
        challenge_texts,
        batch_size=args.batch_size,
    )
    legacy_model = model.predict_many(
        legacy_texts,
        batch_size=args.batch_size,
    )

    threshold = float(
        getattr(config, "NLP_CONFIDENCE_THRESHOLD", 0.60)
    )

    challenge_rules = rule_predictions(challenge)
    legacy_rules = rule_predictions(legacy_test)

    challenge_hybrid = hybrid_predictions(
        challenge,
        challenge_model,
        threshold,
    )
    legacy_hybrid = hybrid_predictions(
        legacy_test,
        legacy_model,
        threshold,
    )

    result = {
        "model_evaluation": "run",
        "dataset_v2": integrity,
        "challenge_count": len(challenge),
        "legacy_test_count": len(legacy_test),
        "legacy_test_hash": dataset_hash(legacy_test),
        "artifact": {
            "directory": str(args.artifact_dir),
            "state_file": model.state_path.name,
            "metadata_file": model.metadata_path.name,
            "format": model.metadata.get("format"),
            "base_model": model.metadata.get("base_model"),
            "best_epoch": model.metadata.get("best_epoch"),
            "validation_metrics": model.metadata.get(
                "validation_metrics"
            ),
            "unfreeze_last_layers": model.metadata.get(
                "unfreeze_last_layers"
            ),
            "device": str(model.device),
        },
        "hybrid_confidence_threshold": threshold,
        "rule_only_challenge": prediction_report(
            challenge,
            challenge_rules,
        ),
        "model_only_challenge": prediction_report(
            challenge,
            challenge_model,
        ),
        "hybrid_challenge": prediction_report(
            challenge,
            challenge_hybrid,
        ),
        "rule_only_legacy_test": prediction_report(
            legacy_test,
            legacy_rules,
        ),
        "model_only_legacy_test": prediction_report(
            legacy_test,
            legacy_model,
        ),
        "hybrid_legacy_test": prediction_report(
            legacy_test,
            legacy_hybrid,
        ),
        "latency": model.benchmark(challenge_texts, limit=100),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(
        markdown_summary(result),
        encoding="utf-8",
    )

    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
