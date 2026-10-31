"""Reproducible V2 AraBERT training; never reads the external challenge set."""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "training_data"))

import config
from scripts.train_chat_model import metrics
from training_data.dataset_v2 import LABELS, dataset_hash, read_jsonl


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=ROOT / "training_data" / "chat_intents_v2.jsonl")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "backend" / "nlp" / "models")
    parser.add_argument("--base-model", default=config.ARABERT_MODEL_NAME)
    parser.add_argument("--seed", type=int, default=20260920)
    parser.add_argument("--max-length", type=int, choices=(64, 96, 128), default=96)
    parser.add_argument("--batch-size", type=int, choices=(8, 16, 32), default=16)
    parser.add_argument("--head-learning-rate", type=float, default=0.003)
    parser.add_argument("--encoder-learning-rate", type=float, default=0.00002)
    parser.add_argument("--dropout", type=float, choices=(0.1, 0.2, 0.3), default=0.2)
    parser.add_argument("--weight-decay", type=float, choices=(0.0, 0.01), default=0.01)
    parser.add_argument("--unfreeze-last-layers", type=int, choices=(0, 1, 2, 3, 4), default=0)
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--patience", type=int, default=8)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def _validate(args):
    rows = read_jsonl(args.dataset, {"train", "validation"})
    if len(rows) != 1500 or {row["intent"] for row in rows} != set(LABELS):
        raise ValueError("V2 training requires the complete 15-label V2 corpus")
    return rows


def train(args, rows):
    try:
        import torch
        from torch.utils.data import DataLoader
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except ImportError as exc:
        raise RuntimeError("V2 training requires torch and transformers; no artifact was written.") from exc
    random.seed(args.seed); torch.manual_seed(args.seed)
    torch.use_deterministic_algorithms(True, warn_only=True)
    labels = list(LABELS); index = {label: position for position, label in enumerate(labels)}
    sets = {split: [row for row in rows if row["split"] == split] for split in ("train", "validation")}
    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    model = AutoModelForSequenceClassification.from_pretrained(args.base_model, num_labels=len(labels), ignore_mismatched_sizes=True)
    for parameter in model.parameters(): parameter.requires_grad = False
    for parameter in model.classifier.parameters(): parameter.requires_grad = True
    if args.unfreeze_last_layers:
        for layer in model.bert.encoder.layer[-args.unfreeze_last_layers:]:
            for parameter in layer.parameters(): parameter.requires_grad = True
    if hasattr(model, "dropout"):
        model.dropout.p = args.dropout
    trainable = [parameter for parameter in model.parameters() if parameter.requires_grad]
    optimizer = torch.optim.AdamW(trainable, lr=args.encoder_learning_rate if args.unfreeze_last_layers else args.head_learning_rate, weight_decay=args.weight_decay)

    def batches(rows_for_split, shuffle=False):
        return DataLoader(rows_for_split, batch_size=args.batch_size, shuffle=shuffle, generator=torch.Generator().manual_seed(args.seed))
    def evaluate(rows_for_split):
        model.eval(); predicted = []
        with torch.no_grad():
            for batch in batches(rows_for_split):
                tokens = tokenizer([row["text"] for row in batch], return_tensors="pt", truncation=True, max_length=args.max_length, padding=True)
                predicted.extend(labels[value] for value in torch.argmax(model(**tokens).logits, dim=-1).tolist())
        return metrics(rows_for_split, predicted, labels)

    best, history, stale, started = None, [], 0, time.perf_counter()
    for epoch in range(1, args.epochs + 1):
        model.train(); losses = []
        for batch in batches(sets["train"], shuffle=True):
            tokens = tokenizer([row["text"] for row in batch], return_tensors="pt", truncation=True, max_length=args.max_length, padding=True)
            target = torch.tensor([index[row["intent"]] for row in batch])
            optimizer.zero_grad(); loss = torch.nn.functional.cross_entropy(model(**tokens).logits, target)
            loss.backward(); torch.nn.utils.clip_grad_norm_(trainable, 1.0); optimizer.step(); losses.append(float(loss.item()))
        validation = evaluate(sets["validation"])
        history.append({"epoch": epoch, "loss": round(sum(losses) / len(losses), 4), "validation": validation})
        if best is None or validation["macro_f1"] > best["validation"]["macro_f1"]:
            trainable_names = {name for name, parameter in model.named_parameters() if parameter.requires_grad}
            best = {"epoch": epoch, "validation": validation, "state": {key: value.detach().cpu().clone() for key, value in model.state_dict().items() if any(key == name or key.startswith(name + ".") for name in trainable_names)}}
            stale = 0
        else:
            stale += 1
            if stale >= args.patience: break
    args.output_dir.mkdir(parents=True, exist_ok=True)
    state_file, metadata_file = "arabert_intent_delta_v2.pt", "chat_intent_metadata_v2.json"
    torch.save(best["state"], args.output_dir / state_file)
    metadata = {"format": "neyan-arabert-intent-delta-v2", "state_file": state_file, "base_model": args.base_model, "labels": labels, "dataset_version": "v2", "dataset_hash": dataset_hash(rows), "train_count": len(sets["train"]), "validation_count": len(sets["validation"]), "seed": args.seed, "best_epoch": best["epoch"], "max_sequence_length": args.max_length, "batch_size": args.batch_size, "head_learning_rate": args.head_learning_rate, "encoder_learning_rate": args.encoder_learning_rate if args.unfreeze_last_layers else None, "unfreeze_last_layers": args.unfreeze_last_layers, "dropout": args.dropout, "weight_decay": args.weight_decay, "validation_metrics": best["validation"], "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (args.output_dir / metadata_file).write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"metadata": metadata, "history": history, "duration_seconds": round(time.perf_counter() - started, 2)}


if __name__ == "__main__":
    arguments = parse_args(); validated_rows = _validate(arguments)
    if arguments.validate_only:
        print(json.dumps({"valid": True, "rows": len(validated_rows), "dataset_hash": dataset_hash(validated_rows)}, indent=2))
    else:
        print(json.dumps(train(arguments, validated_rows), ensure_ascii=True, indent=2))
