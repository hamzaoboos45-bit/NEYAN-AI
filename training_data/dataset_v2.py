"""Shared validation for the versioned, no-PII Arabic intent corpora.

This module deliberately has no ML dependency: data quality checks must run
before a model, GPU, or network download is available.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


LABELS = (
    "availability_inquiry",
    "book_trip",
    "cancel_booking",
    "cancellation",
    "company_information",
    "complaint",
    "confirmation",
    "general_conversation",
    "goodbye",
    "greeting",
    "help",
    "maintenance_request",
    "price_inquiry",
    "trip_information",
    "trip_search",
)

_DIACRITICS = re.compile(r"[\u064B-\u065F\u0670]")
_PUNCTUATION = re.compile(r"[^\w\s]")
_SPACE = re.compile(r"\s+")
_PII = re.compile(
    r"(?:\+?\d[\d\s-]{6,}\d)|(?:[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})"
)


def normalize_for_overlap(text: str) -> str:
    """Normalize only surface variation; do not remove negation or numbers."""
    value = _DIACRITICS.sub("", text or "").lower()

    value = value.translate(
        str.maketrans(
            {
                "أ": "ا",
                "إ": "ا",
                "آ": "ا",
                "ى": "ي",
                "ة": "ه",
            }
        )
    )

    value = _PUNCTUATION.sub(" ", value)
    return _SPACE.sub(" ", value).strip()


def dataset_hash(rows: list[dict]) -> str:
    """Return a SHA-256 hash of the dataset rows."""
    payload = "\n".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True)
        for row in rows
    )

    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_jsonl(path: Path, allowed_splits: set[str]) -> list[dict]:
    """Load and validate a JSONL dataset."""
    rows = []

    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue

            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{path.name}:{line_number} is not JSON"
                ) from exc

            allowed_fields = {
                "text",
                "intent",
                "split",
                "family",
                "source",
            }

            if set(row) - allowed_fields:
                raise ValueError(
                    f"{path.name}:{line_number} has unsupported fields"
                )

            if (
                not isinstance(row.get("text"), str)
                or not normalize_for_overlap(row["text"])
            ):
                raise ValueError(
                    f"{path.name}:{line_number} has blank text"
                )

            if (
                row.get("intent") not in LABELS
                or row.get("split") not in allowed_splits
            ):
                raise ValueError(
                    f"{path.name}:{line_number} has invalid intent or split"
                )

            if _PII.search(row["text"]):
                raise ValueError(
                    f"{path.name}:{line_number} contains possible PII"
                )

            rows.append(row)

    if not rows:
        raise ValueError(f"{path.name} is empty")

    return rows


def token_similarity(left: str, right: str) -> float:
    """Calculate Jaccard similarity between normalized token sets."""
    left_words = set(normalize_for_overlap(left).split())
    right_words = set(normalize_for_overlap(right).split())

    return len(left_words & right_words) / max(
        1,
        len(left_words | right_words),
    )


def validate_isolation(
    train_validation: list[dict],
    challenge: list[dict],
    near_duplicate_threshold: float = 0.92,
) -> dict:
    """Reject exact/normalized/family leakage and flag suspicious near pairs."""
    all_rows = (
        [("v2", row) for row in train_validation]
        + [("challenge", row) for row in challenge]
    )

    by_normalized: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    by_family: dict[str, set[str]] = defaultdict(set)

    for corpus, row in all_rows:
        by_normalized[normalize_for_overlap(row["text"])].append(
            (corpus, row)
        )

        if row.get("family"):
            by_family[row["family"]].add(
                corpus + ":" + row["split"]
            )

    duplicates = {
        key: value
        for key, value in by_normalized.items()
        if len(value) > 1
    }

    family_leaks = {
        key: value
        for key, value in by_family.items()
        if len(value) > 1
    }

    if duplicates:
        raise ValueError(
            f"normalized duplicate leakage: {list(duplicates)[:3]}"
        )

    if family_leaks:
        raise ValueError(
            f"family leakage: {list(family_leaks)[:3]}"
        )

    suspicious = []

    for left in train_validation:
        for right in challenge:
            score = token_similarity(
                left["text"],
                right["text"],
            )

            if score >= near_duplicate_threshold:
                suspicious.append(
                    {
                        "score": round(score, 3),
                        "train": left["text"],
                        "challenge": right["text"],
                    }
                )

    if suspicious:
        raise ValueError(
            f"near-duplicate challenge leakage: {suspicious[:2]}"
        )

    counts = {
        split: dict(
            sorted(
                Counter(
                    row["intent"]
                    for row in train_validation
                    if row["split"] == split
                ).items()
            )
        )
        for split in ("train", "validation")
    }

    challenge_counts = dict(
        sorted(
            Counter(row["intent"] for row in challenge).items()
        )
    )

    missing_split_coverage = any(
        counts[split].get(label, 0) == 0
        for split in counts
        for label in LABELS
    )

    insufficient_challenge_coverage = any(
        challenge_counts.get(label, 0) < 10
        for label in LABELS
    )

    if missing_split_coverage or insufficient_challenge_coverage:
        raise ValueError("missing per-intent split coverage")

    return {
        "v2_hash": dataset_hash(train_validation),
        "challenge_hash": dataset_hash(challenge),
        "split_counts": counts,
        "challenge_counts": challenge_counts,
        "near_duplicate_threshold": near_duplicate_threshold,
    }