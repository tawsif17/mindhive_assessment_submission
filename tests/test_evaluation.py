from __future__ import annotations

import unittest

from sklearn.model_selection import GroupKFold

from matcher.evaluation import (
    COST_ABSTENTION,
    COST_CORRECT_AUTO,
    COST_WRONG_AUTO,
    EvaluatedLine,
    apply_operating_point,
    calibration_bins,
    calculate_metrics,
    customer_group,
    nearest_rank_percentile,
    regression_gate_failures,
    select_operating_point,
    sweep_operating_points,
    wilson_lower_bound,
)
from matcher.types import CandidateEvidence
from matcher.reporting import review_group


def make_evaluated_line(
    line_id: str,
    gt: str,
    candidate_code: str = "ACM-1",
    confidence: float = 0.99,
    margin: float = 0.20,
    safety_blocks: list[str] | None = None,
) -> EvaluatedLine:
    candidate = CandidateEvidence(
        item_code=candidate_code,
        item_name="Item",
        tenant="acme",
        confidence=confidence,
        score=confidence,
        margin=margin,
        safety_blocks=safety_blocks or [],
    )
    row = {
        "line_id": line_id,
        "tenant": "acme",
        "customer_id": f"CUST-{line_id}",
        "raw_text": "Item",
        "buyer_sku": "",
        "raw_barcode": "",
        "uom_text": "",
        "gt_item_code": gt,
    }
    return EvaluatedLine(row, [candidate], 2.0, "plain_text")


class MetricTests(unittest.TestCase):
    def test_cost_model_uses_exact_assessment_values(self) -> None:
        correct = make_evaluated_line("1", "ACM-1")
        wrong = make_evaluated_line("2", "ACM-2")
        abstain = make_evaluated_line("3", "ACM-1", confidence=0.2)
        decided = apply_operating_point([correct, wrong, abstain], 0.9, 0.1)
        metrics = calculate_metrics(decided)
        self.assertEqual(
            COST_CORRECT_AUTO + COST_WRONG_AUTO + COST_ABSTENTION,
            metrics["net_cost_seconds"],
        )
        self.assertEqual(1, metrics["correct_auto"])
        self.assertEqual(1, metrics["wrong_auto"])

    def test_recall_at_three_uses_review_candidates(self) -> None:
        line = make_evaluated_line("1", "ACM-2", confidence=0.2)
        line.candidates.append(
            CandidateEvidence("ACM-2", "Right item", "acme", confidence=0.1)
        )
        decided = apply_operating_point([line], 0.9, 0.1)
        metrics = calculate_metrics(decided)
        self.assertEqual(1.0, metrics["recall_at_3_answerable"])
        self.assertEqual(1.0, metrics["recall_at_3_reviewed"])

    def test_safety_block_prevents_auto(self) -> None:
        line = make_evaluated_line("1", "ACM-1", safety_blocks=["active_twin"])
        line.top.barcode_exact = True
        decided = apply_operating_point([line], 0.9, 0.1)
        self.assertEqual("review", decided[0].decision)
        self.assertEqual("active_twin", decided[0].reason_code)

    def test_unique_exact_identifier_bypasses_text_threshold(self) -> None:
        line = make_evaluated_line("1", "ACM-1", confidence=0.4, margin=0.0)
        line.top.barcode_exact = True
        decided = apply_operating_point([line], 1.0, 0.2)
        self.assertEqual("auto", decided[0].decision)
        self.assertEqual("barcode_unique", decided[0].reason_code)

    def test_nearest_rank_p95(self) -> None:
        self.assertEqual(95.0, nearest_rank_percentile([float(i) for i in range(1, 101)], 0.95))

    def test_wilson_lower_bound_needs_sample_support(self) -> None:
        self.assertLess(wilson_lower_bound(10, 10), 0.927)
        self.assertGreater(wilson_lower_bound(100, 100), 0.927)

    def test_calibration_bins_count_each_candidate_once(self) -> None:
        lines = [
            make_evaluated_line("1", "ACM-1", confidence=0.94),
            make_evaluated_line("2", "ACM-2", confidence=0.99),
        ]
        bins = calibration_bins(lines)
        self.assertEqual(2, sum(row["rows"] for row in bins))

    def test_operating_point_sweep_is_deterministic(self) -> None:
        lines = [make_evaluated_line(str(index), "ACM-1") for index in range(120)]
        first = sweep_operating_points(lines)
        second = sweep_operating_points(lines)
        self.assertEqual(first, second)
        selected, passed = select_operating_point(first)
        self.assertTrue(passed)
        self.assertGreaterEqual(selected["precision_auto"], 0.98)
        self.assertEqual("full_uncertainty_policy", selected["selection_policy"])

    def test_perfect_small_sample_uses_approved_fallback(self) -> None:
        lines = [make_evaluated_line(str(index), "ACM-1") for index in range(12)]
        selected, passed = select_operating_point(sweep_operating_points(lines))
        self.assertTrue(passed)
        self.assertEqual("perfect_observed_small_sample", selected["selection_policy"])
        self.assertEqual(1.0, selected["precision_auto"])
        self.assertLess(selected["precision_wilson_lower_95"], 0.927)

    def test_manual_review_uses_explicit_failure_group(self) -> None:
        conclusion = {"group": "ranking_tie"}
        self.assertEqual("ranking_tie", review_group(conclusion))

    def test_regression_gate_reports_metric_and_data_failures(self) -> None:
        baseline = {
            "training_file_sha256": "expected",
            "allowed_selection_policies": ["perfect_observed_small_sample"],
            "minimum_auto_precision": 1.0,
            "minimum_coverage": 0.05,
            "minimum_recall_at_3_answerable": 0.92,
            "minimum_blank_refusal_rate": 1.0,
            "maximum_wrong_auto": 0,
            "maximum_net_cost_seconds": 100,
            "maximum_cross_tenant_violations": 0,
            "maximum_safety_block_auto_violations": 0,
            "maximum_p95_latency_ms": 250.0,
        }
        metrics = {
            "precision_auto": 0.99,
            "coverage": 0.04,
            "recall_at_3_answerable": 0.93,
            "correct_refusal_rate_blank": 1.0,
            "wrong_auto": 1,
            "net_cost_seconds": 80,
            "cross_tenant_violations": 0,
            "safety_block_auto_violations": 0,
            "p95_latency_ms": 50.0,
        }
        failures = regression_gate_failures(
            metrics, baseline, "changed", "perfect_observed_small_sample"
        )
        self.assertTrue(any("training data hash" in failure for failure in failures))
        self.assertTrue(any("precision_auto" in failure for failure in failures))
        self.assertTrue(any("coverage" in failure for failure in failures))
        self.assertTrue(any("wrong_auto" in failure for failure in failures))

    def test_group_split_never_shares_customer_group(self) -> None:
        rows = [
            {"tenant": "acme", "customer_id": f"CUST-{index // 2}"}
            for index in range(20)
        ]
        groups = [customer_group(row) for row in rows]
        splitter = GroupKFold(n_splits=5)
        for train, validation in splitter.split(rows, groups=groups):
            train_groups = {groups[index] for index in train}
            validation_groups = {groups[index] for index in validation}
            self.assertFalse(train_groups.intersection(validation_groups))


if __name__ == "__main__":
    unittest.main()
