from __future__ import annotations

import csv
import hashlib
import json
import unittest
from pathlib import Path


PREDICTION_COLUMNS = [
    "line_id", "item_code", "confidence", "decision", "reason_code", "candidates"
]


class FinalPredictionArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        with (cls.root / "predictions.csv").open(newline="", encoding="utf-8") as handle:
            cls.predictions = list(csv.DictReader(handle))
        with (cls.root / "data" / "order_lines_holdout.csv").open(
            newline="", encoding="utf-8-sig"
        ) as handle:
            cls.holdout = list(csv.DictReader(handle))

    def test_frozen_config_matches_training_file_and_completed_review(self) -> None:
        config = json.loads((self.root / "matcher_config.json").read_text(encoding="utf-8"))
        training_hash = hashlib.sha256(
            (self.root / "data" / "order_lines_train.csv").read_bytes()
        ).hexdigest()
        self.assertEqual("frozen_after_manual_review", config["status"])
        self.assertTrue(config["review_complete"])
        self.assertTrue(config["regression_gates_passed"])
        self.assertEqual(20, config["reviewed_lines"])
        self.assertEqual(training_hash, config["training_file_sha256"])

    def test_predictions_have_exact_rows_schema_and_tenant_scope(self) -> None:
        self.assertEqual(300, len(self.predictions))
        self.assertEqual(PREDICTION_COLUMNS, list(self.predictions[0]))
        source_by_id = {row["line_id"]: row for row in self.holdout}
        self.assertEqual(set(source_by_id), {row["line_id"] for row in self.predictions})
        for prediction in self.predictions:
            self.assertIn(prediction["decision"], {"auto", "review", "reject"})
            self.assertGreaterEqual(float(prediction["confidence"]), 0.0)
            self.assertLessEqual(float(prediction["confidence"]), 1.0)
            if prediction["decision"] != "auto":
                self.assertEqual("", prediction["item_code"])
            prefix = "ACM-" if source_by_id[prediction["line_id"]]["tenant"] == "acme" else "NRD-"
            codes = [prediction["item_code"]] if prediction["item_code"] else []
            codes.extend(
                pair.partition(":")[0]
                for pair in prediction["candidates"].split("|")
                if pair
            )
            self.assertTrue(all(code.startswith(prefix) for code in codes))


if __name__ == "__main__":
    unittest.main()
