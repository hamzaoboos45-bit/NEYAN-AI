"""Reproducible NLP V2 AraBERT training.

This script NEVER reads the external challenge set. Model selection is based
only on the validation split inside chat_intents_v2.jsonl.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "training_data"))

import config
from scripts.train_chat_model import metrics
from training_data.dataset_v2 import LABELS, dataset_hash, read_jsonl


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        type=Path,
        default=ROOT / "training_data" / "chat_intents_v2.jsonl",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "backend" / "nlp" / "models",
    )
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
    labels = {row["intent"] for row in rows}
    split_counts = Counter(row["split"] for row in rows)

    if len(rows) != 1500:
        raise ValueError(f"V2 training requires 1500 rows; found {len(rows)}")
    if labels != set(LABELS):
        missing = sorted(set(LABELS) - labels)
        extra = sorted(labels - set(LABELS))
        raise ValueError(f"V2 label mismatch; missing={missing}, extra={extra}")
    if split_counts["train"] != 1200 or split_counts["validation"] != 300:
        raise ValueError(
            "V2 split mismatch; expected train=1200 and validation=300, "
            f"found train={split_counts['train']} validation={split_counts['validation']}"
        )
    return rows


def _seed_everything(seed, torch):
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)
    if hasattr(torch.backends, "cudnn"):
        torch.backends.cudnn.benchmark = False


def train(args, rows):
    try:
        import torch
        import transformers
        from torch.utils.data import DataLoader
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except ImportError as exc:
        raise RuntimeError(
            "V2 training requires torch and transformers; no artifact was written."
        ) from exc

    _seed_everything(args.seed, torch)

    labels = list(LABELS)
    label_index = {label: position for position, label in enumerate(labels)}
    sets = {
        split: [row for row in rows if row["split"] == split]
        for split in ("train", "validation")
    }

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Training device: {device}", file=sys.stderr, flush=True)
    if device.type == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}", file=sys.stderr, flush=True)

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.base_model,
        num_labels=len(labels),
        ignore_mismatched_sizes=True,
    )

    # Freeze the whole pretrained model first.
    for parameter in model.parameters():
        parameter.requires_grad = False

    # Always train the task head.
    for parameter in model.classifier.parameters():
        parameter.requires_grad = True

    # Optionally fine-tune only the last N encoder layers.
    if args.unfreeze_last_layers:
        for layer in model.bert.encoder.layer[-args.unfreeze_last_layers:]:
            for parameter in layer.parameters():
                parameter.requires_grad = True

    if hasattr(model, "dropout"):
        model.dropout.p = args.dropout

    model = model.to(device)

    head_parameters = [
        parameter
        for parameter in model.classifier.parameters()
        if parameter.requires_grad
    ]

    encoder_parameters = [
        parameter
        for name, parameter in model.named_parameters()
        if parameter.requires_grad and not name.startswith("classifier.")
    ]

    optimizer_groups = [
        {
            "params": head_parameters,
            "lr": args.head_learning_rate,
        }
    ]
    if encoder_parameters:
        optimizer_groups.append(
            {
                "params": encoder_parameters,
                "lr": args.encoder_learning_rate,
            }
        )

    trainable = head_parameters + encoder_parameters
    optimizer = torch.optim.AdamW(
        optimizer_groups,
        weight_decay=args.weight_decay,
    )

    def batches(rows_for_split, *, shuffle=False, seed_offset=0):
        # Critical: preserve each dataset item as a dict. PyTorch's default
        # collate function converts list[dict] into dict[list], which breaks
        # row["text"] iteration.
        generator = torch.Generator().manual_seed(args.seed + seed_offset)
        return DataLoader(
            rows_for_split,
            batch_size=args.batch_size,
            shuffle=shuffle,
            generator=generator,
            collate_fn=lambda items: items,
        )

    def tokenize_batch(batch):
        tokens = tokenizer(
            [row["text"] for row in batch],
            return_tensors="pt",
            truncation=True,
            max_length=args.max_length,
            padding=True,
        )
        return {key: value.to(device) for key, value in tokens.items()}

    def evaluate(rows_for_split):
        model.eval()
        predicted = []
        with torch.no_grad():
            for batch in batches(rows_for_split):
                tokens = tokenize_batch(batch)
                logits = model(**tokens).logits
                predicted.extend(
                    labels[index]
                    for index in torch.argmax(logits, dim=-1).cpu().tolist()
                )
        return metrics(rows_for_split, predicted, labels)

    best = None
    history = []
    stale = 0
    started = time.perf_counter()

    for epoch in range(1, args.epochs + 1):
        model.train()
        losses = []

        for batch in batches(
            sets["train"],
            shuffle=True,
            seed_offset=epoch,
        ):
            tokens = tokenize_batch(batch)
            target = torch.tensor(
                [label_index[row["intent"]] for row in batch],
                dtype=torch.long,
                device=device,
            )

            optimizer.zero_grad(set_to_none=True)
            logits = model(**tokens).logits
            loss = torch.nn.functional.cross_entropy(logits, target)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(trainable, 1.0)
            optimizer.step()
            losses.append(float(loss.detach().cpu().item()))

        validation = evaluate(sets["validation"])
        epoch_result = {
            "epoch": epoch,
            "loss": round(sum(losses) / max(1, len(losses)), 4),
            "validation": validation,
        }
        history.append(epoch_result)

        print(
            json.dumps(
                {
                    "epoch": epoch,
                    "loss": epoch_result["loss"],
                    "validation_accuracy": validation["accuracy"],
                    "validation_macro_f1": validation["macro_f1"],
                    "validation_weighted_f1": validation["weighted_f1"],
                },
                ensure_ascii=True,
            ),
            file=sys.stderr,
            flush=True,
        )

        if best is None or validation["macro_f1"] > best["validation"]["macro_f1"]:
            trainable_names = {
                name
                for name, parameter in model.named_parameters()
                if parameter.requires_grad
            }
            current_state = model.state_dict()
            best = {
                "epoch": epoch,
                "validation": validation,
                "state": {
                    name: current_state[name].detach().cpu().clone()
                    for name in trainable_names
                },
            }
            stale = 0
        else:
            stale += 1
            if stale >= args.patience:
                print(
                    f"Early stopping after epoch {epoch}; "
                    f"best epoch was {best['epoch']}.",
                    file=sys.stderr,
                    flush=True,
                )
                break

    if best is None:
        raise RuntimeError("Training completed without a valid best checkpoint.")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    state_file = "arabert_intent_delta_v2.pt"
    metadata_file = "chat_intent_metadata_v2.json"

    torch.save(best["state"], args.output_dir / state_file)

    duration_seconds = round(time.perf_counter() - started, 2)
    metadata = {
        "format": "neyan-arabert-intent-delta-v2",
        "state_file": state_file,
        "base_model": args.base_model,
        "labels": labels,
        "dataset_version": "v2",
        "dataset_hash": dataset_hash(rows),
        "train_count": len(sets["train"]),
        "validation_count": len(sets["validation"]),
        "seed": args.seed,
        "best_epoch": best["epoch"],
        "max_sequence_length": args.max_length,
        "batch_size": args.batch_size,
        "head_learning_rate": args.head_learning_rate,
        "encoder_learning_rate": (
            args.encoder_learning_rate if args.unfreeze_last_layers else None
        ),
        "unfreeze_last_layers": args.unfreeze_last_layers,
        "dropout": args.dropout,
        "weight_decay": args.weight_decay,
        "validation_metrics": best["validation"],
        "device": str(device),
        "torch_version": torch.__version__,
        "transformers_version": transformers.__version__,
        "trainable_parameter_count": sum(
            parameter.numel() for parameter in trainable
        ),
        "training_duration_seconds": duration_seconds,
        "created_at_utc": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(),
        ),
    }

    (args.output_dir / metadata_file).write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "metadata": metadata,
        "history": history,
        "artifact": str(args.output_dir / state_file),
        "metadata_file": str(args.output_dir / metadata_file),
    }


if __name__ == "__main__":
    arguments = parse_args()
    validated_rows = _validate(arguments)

    if arguments.validate_only:
        print(
            json.dumps(
                {
                    "valid": True,
                    "rows": len(validated_rows),
                    "train": sum(row["split"] == "train" for row in validated_rows),
                    "validation": sum(
                        row["split"] == "validation" for row in validated_rows
                    ),
                    "dataset_hash": dataset_hash(validated_rows),
                },
                indent=2,
            )
        )
    else:
        print(
            json.dumps(
                train(arguments, validated_rows),
                ensure_ascii=True,
                indent=2,
            )
        )
