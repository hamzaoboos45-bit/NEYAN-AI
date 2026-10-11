"""Fine-tune the current AraBERT backbone for NEYAN's reviewed chat intents.

No customer database or history is opened.  The script validates synthetic
JSONL, keeps explicit leakage-resistant splits, trains the classifier head
over the current frozen AraBERT encoder on CPU, selects the best epoch by validation macro-F1,
and saves only the deployable delta state.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config
from backend.nlp.intent_classifier import LEGACY_INTENT_MAP
from backend.nlp.preprocessing import normalize_arabic

DATASET = ROOT / "training_data" / "chat_intents.jsonl"
MODEL_DIR = ROOT / "backend" / "nlp" / "models"
STATE_FILE = "arabert_intent_delta.pt"
REPORT = ROOT / "docs" / "CHAT_MODEL_TRAINING_METRICS.json"
SEED = 20260920
PHONE_OR_EMAIL = re.compile(r"(?:\+?\d[\d\s-]{6,}\d)|(?:[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})")


def read_dataset(path: Path = DATASET) -> list[dict]:
    valid_labels = set(LEGACY_INTENT_MAP) - {"unknown"}
    rows, seen = [], {}
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"malformed JSON at line {number}") from exc
            text, intent, split = row.get("text"), row.get("intent"), row.get("split")
            normalized = normalize_arabic(text or "") if isinstance(text, str) else ""
            if not normalized:
                raise ValueError(f"empty text at line {number}")
            if intent not in valid_labels or split not in {"train", "validation", "test"}:
                raise ValueError(f"invalid label or split at line {number}")
            if PHONE_OR_EMAIL.search(text):
                raise ValueError(f"possible PII at line {number}")
            if normalized in seen:
                raise ValueError(f"duplicate normalized text at lines {seen[normalized]} and {number}")
            seen[normalized] = number
            rows.append({"text": text, "intent": intent, "split": split})
    if not rows or any(not any(row["split"] == split for row in rows) for split in ("train", "validation", "test")):
        raise ValueError("dataset requires non-empty train/validation/test splits")
    return rows


def metrics(rows: list[dict], predictions: list[str], labels: list[str]) -> dict:
    columns = [*labels, *([] if all(value in labels for value in predictions) else ["unknown"])]
    matrix = {label: {other: 0 for other in columns} for label in labels}
    for row, predicted in zip(rows, predictions):
        matrix[row["intent"]][predicted] += 1
    per_class, macro_precision, macro_recall, macro, weighted = {}, 0.0, 0.0, 0.0, 0.0
    for label in labels:
        tp = matrix[label][label]
        fp = sum(matrix[other][label] for other in labels if other != label)
        fn = sum(matrix[label][other] for other in columns if other != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        support = sum(matrix[label].values())
        per_class[label] = {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4), "support": support}
        macro_precision += precision
        macro_recall += recall
        macro += f1
        weighted += f1 * support
    return {"accuracy": round(sum(matrix[label][label] for label in labels) / len(rows), 4), "macro_precision": round(macro_precision / len(labels), 4), "macro_recall": round(macro_recall / len(labels), 4), "macro_f1": round(macro / len(labels), 4), "weighted_f1": round(weighted / len(rows), 4), "per_class": per_class, "confusion_matrix": matrix}


def _predict(model, tokenizer, rows, labels, torch, max_length):
    started, predictions = time.perf_counter(), []
    model.eval()
    with torch.no_grad():
        for row in rows:
            tokens = tokenizer(row["text"], return_tensors="pt", truncation=True, max_length=max_length, padding=True)
            predictions.append(labels[int(torch.argmax(model(**tokens).logits, dim=-1)[0].item())])
    return predictions, (time.perf_counter() - started) * 1000 / max(1, len(rows))


def _encode_frozen(model, tokenizer, rows, torch, max_length, batch_size=32):
    """Encode the small reviewed corpus once; train only the task head."""
    vectors, targets = [], []
    model.bert.eval()
    with torch.no_grad():
        for start in range(0, len(rows), batch_size):
            batch = rows[start:start + batch_size]
            tokens = tokenizer([row["text"] for row in batch], return_tensors="pt", truncation=True, max_length=max_length, padding=True)
            output = model.bert(**tokens)
            vectors.append(output.pooler_output.detach())
    return torch.cat(vectors, dim=0)


def train() -> dict:
    try:
        import torch
        from torch.utils.data import DataLoader
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except ImportError as exc:
        raise RuntimeError("AraBERT training needs optional torch and transformers") from exc
    random.seed(SEED); torch.manual_seed(SEED); torch.use_deterministic_algorithms(True, warn_only=True)
    rows = read_dataset()
    sets = {split: [row for row in rows if row["split"] == split] for split in ("train", "validation", "test")}
    labels = sorted({row["intent"] for row in rows}); label_index = {label: i for i, label in enumerate(labels)}
    tokenizer = AutoTokenizer.from_pretrained(config.ARABERT_MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(config.ARABERT_MODEL_NAME, num_labels=len(labels), ignore_mismatched_sizes=True)
    for parameter in model.parameters(): parameter.requires_grad = False
    for parameter in model.classifier.parameters(): parameter.requires_grad = True
    # CPU profiling showed final-layer unfreezing was disproportionate to this
    # small reviewed corpus. This controlled second configuration updates the
    # task head only and retains AraBERT's pretrained encoder intact.
    max_length, batch_size, epochs, head_learning_rate = 64, 16, 60, 5e-3
    optimizer = torch.optim.AdamW(model.classifier.parameters(), lr=head_learning_rate)
    train_vectors = _encode_frozen(model, tokenizer, sets["train"], torch, max_length)
    validation_vectors = _encode_frozen(model, tokenizer, sets["validation"], torch, max_length)
    test_vectors = _encode_frozen(model, tokenizer, sets["test"], torch, max_length)
    train_targets = torch.tensor([label_index[row["intent"]] for row in sets["train"]])
    loader = DataLoader(list(zip(train_vectors, train_targets)), batch_size=batch_size, shuffle=True, generator=torch.Generator().manual_seed(SEED))
    best, history, started, stale_epochs = {"macro": -1.0}, [], time.perf_counter(), 0
    for epoch in range(1, epochs + 1):
        model.classifier.train(); losses = []
        for batch in loader:
            vectors, target = batch
            optimizer.zero_grad(); loss = torch.nn.functional.cross_entropy(model.classifier(vectors), target); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.classifier.parameters(), 1.0); optimizer.step(); losses.append(float(loss.item()))
        model.classifier.eval()
        with torch.no_grad():
            validation_predictions = [labels[int(index)] for index in torch.argmax(model.classifier(validation_vectors), dim=-1).tolist()]
        validation = metrics(sets["validation"], validation_predictions, labels)
        history.append({"epoch": epoch, "training_loss": round(sum(losses) / len(losses), 4), "validation_macro_f1": validation["macro_f1"]})
        if validation["macro_f1"] > best["macro"]:
            state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items() if key.startswith("classifier.")}
            best = {"macro": validation["macro_f1"], "epoch": epoch, "state": state}
            stale_epochs = 0
        else:
            stale_epochs += 1
            if stale_epochs >= 8:
                break
    model.load_state_dict(best["state"], strict=False)
    model.classifier.eval()
    with torch.no_grad():
        test_predictions = [labels[int(index)] for index in torch.argmax(model.classifier(test_vectors), dim=-1).tolist()]
    _, latency = _predict(model, tokenizer, sets["test"], labels, torch, max_length)
    MODEL_DIR.mkdir(parents=True, exist_ok=True); torch.save(best["state"], MODEL_DIR / STATE_FILE)
    metadata = {"format": "neyan-arabert-intent-head-v1", "base_model": config.ARABERT_MODEL_NAME, "state_file": STATE_FILE, "labels": labels, "max_sequence_length": max_length, "best_epoch": best["epoch"], "training_configuration": {"seed": SEED, "max_epochs": epochs, "head_learning_rate": head_learning_rate, "batch_size": batch_size, "device": "cpu", "early_stopping_patience": 8, "trainable_layers": ["classifier"], "frozen_encoder_embeddings": True}}
    with (MODEL_DIR / "chat_intent_metadata.json").open("w", encoding="utf-8", newline="\n") as handle: json.dump(metadata, handle, ensure_ascii=False, sort_keys=True, indent=2)
    report = {"dataset_counts": {split: len(value) for split, value in sets.items()}, "class_distribution": {split: dict(sorted(Counter(row["intent"] for row in value).items())) for split, value in sets.items()}, "training_history": history, "best_epoch": best["epoch"], "test_metrics": metrics(sets["test"], test_predictions, labels), "test_inference_ms_per_message": round(latency, 2), "training_duration_seconds": round(time.perf_counter() - started, 2), "artifact": f"backend/nlp/models/{STATE_FILE}"}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    with REPORT.open("w", encoding="utf-8", newline="\n") as handle: json.dump(report, handle, ensure_ascii=False, sort_keys=True, indent=2)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--validate-only", action="store_true"); args = parser.parse_args()
    print(json.dumps({"valid": True, "rows": len(read_dataset())} if args.validate_only else train(), ensure_ascii=False, indent=2))
