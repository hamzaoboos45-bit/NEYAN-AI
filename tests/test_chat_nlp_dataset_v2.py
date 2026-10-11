"""Data-integrity gates for the V2 Arabic intent corpus."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "training_data"))

from dataset_v2 import LABELS, read_jsonl, validate_isolation


def _datasets():
    train_validation = read_jsonl(ROOT / "training_data" / "chat_intents_v2.jsonl", {"train", "validation"})
    challenge = read_jsonl(ROOT / "training_data" / "chat_intents_challenge_test.jsonl", {"challenge"})
    return train_validation, challenge


class DatasetV2Tests(unittest.TestCase):
    def test_v2_has_stratified_100_examples_per_existing_intent(self):
        rows, _ = _datasets()
        self.assertEqual(len(rows), 1500)
        for label in LABELS:
            self.assertEqual(sum(row["intent"] == label and row["split"] == "train" for row in rows), 80)
            self.assertEqual(sum(row["intent"] == label and row["split"] == "validation" for row in rows), 20)

    def test_v2_challenge_set_is_external_balanced_and_leakage_checked(self):
        rows, challenge = _datasets()
        report = validate_isolation(rows, challenge)
        self.assertEqual(len(challenge), 150)
        self.assertTrue(all(report["challenge_counts"][label] == 10 for label in LABELS))
        self.assertNotEqual(report["v2_hash"], report["challenge_hash"])

    def test_v2_uses_only_the_existing_runtime_intent_taxonomy(self):
        rows, challenge = _datasets()
        self.assertEqual({row["intent"] for row in rows + challenge}, set(LABELS))
