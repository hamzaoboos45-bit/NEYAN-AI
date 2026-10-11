"""V3.1 development-data contracts; intentionally never opens the sealed holdout."""
from __future__ import annotations

import json
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "training_data"))

from dataset_v2 import LABELS, normalize_for_overlap

DATASET = ROOT / "training_data" / "chat_intents_v3_1.jsonl"


def rows() -> list[dict]:
    return [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]


class DatasetV31Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = rows()

    def test_exact_balanced_dataset_contract(self):
        self.assertEqual(len(self.rows), 3450)
        self.assertEqual(Counter(row["split"] for row in self.rows), {"train": 3000, "validation": 450})
        self.assertEqual({row["intent"] for row in self.rows}, set(LABELS))
        for intent in LABELS:
            self.assertEqual(sum(row["intent"] == intent and row["split"] == "train" for row in self.rows), 200)
            self.assertEqual(sum(row["intent"] == intent and row["split"] == "validation" for row in self.rows), 30)

    def test_family_diversity_and_split_isolation(self):
        for intent in LABELS:
            train = {row["family"] for row in self.rows if row["intent"] == intent and row["split"] == "train"}
            validation = {row["family"] for row in self.rows if row["intent"] == intent and row["split"] == "validation"}
            self.assertGreaterEqual(len(train), 10)
            self.assertGreaterEqual(len(validation), 3)
            self.assertFalse(train & validation)

    def test_no_normalized_text_duplicate_across_splits(self):
        normalized = [normalize_for_overlap(row["text"]) for row in self.rows]
        self.assertEqual(len(normalized), len(set(normalized)))

    def test_v31_generator_and_trainer_do_not_reference_sealed_final_holdout(self):
        sealed_name = "chat_intents_final_holdout_v3.jsonl"
        sources = [
            ROOT / "training_data" / "build_dataset_v3_1.py",
            ROOT / "scripts" / "train_chat_model_v2.py",
            ROOT / "scripts" / "train_chat_model_v3.py",
        ]
        for source in sources:
            self.assertNotIn(sealed_name, source.read_text(encoding="utf-8"), source.name)
