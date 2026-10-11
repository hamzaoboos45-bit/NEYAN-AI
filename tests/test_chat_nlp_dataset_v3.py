"""V3 data contracts: group ownership and final-holdout isolation."""
from __future__ import annotations

import json
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "training_data"))

from build_dataset_v3 import validate
from dataset_v2 import LABELS


def rows(name: str):
    return [json.loads(line) for line in (ROOT / "training_data" / name).read_text(encoding="utf-8").splitlines() if line.strip()]


class DatasetV3Tests(unittest.TestCase):
    def test_v3_counts_and_taxonomy_are_balanced(self):
        data, holdout = rows("chat_intents_v3.jsonl"), rows("chat_intents_final_holdout_v3.jsonl")
        self.assertEqual(len(data), 3450); self.assertEqual(len(holdout), 300)
        self.assertEqual(Counter(row["split"] for row in data), {"train": 3000, "validation": 450})
        self.assertEqual({row["intent"] for row in data + holdout}, set(LABELS))
        self.assertTrue(all(value == 20 for value in Counter(row["intent"] for row in holdout).values()))

    def test_family_never_crosses_train_validation_or_final_holdout(self):
        data, holdout = rows("chat_intents_v3.jsonl"), rows("chat_intents_final_holdout_v3.jsonl")
        family_splits = {}
        for row in data + holdout: family_splits.setdefault(row["family"], set()).add(row["split"])
        self.assertTrue(all(len(splits) == 1 for splits in family_splits.values()))

    def test_final_holdout_is_validated_against_training_and_retired_challenge(self):
        data, holdout = rows("chat_intents_v3.jsonl"), rows("chat_intents_final_holdout_v3.jsonl")
        self.assertEqual(validate(data, holdout), {"train": 3000, "validation": 450, "final_holdout": 300, "families": 105})
