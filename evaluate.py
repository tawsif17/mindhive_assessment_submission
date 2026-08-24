#!/usr/bin/env python3
"""Run grouped Task 3 evaluation and create frozen engineering outputs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from matcher import Matcher
from matcher.data import load_order_rows
from matcher.evaluation import (
    apply_operating_point,
    bootstrap_uncertainty,
    calibration_bins,
    calculate_metrics,
    compare_strategies,
    evaluated_line_to_csv,
    fit_final_ranker,
    grouped_out_of_fold_predictions,
    metric_breakdown,
    regression_gate_failures,
    select_operating_point,
    sweep_operating_points,
    write_csv,
    write_json,
    write_simple_svg,
)
from matcher.reporting import (
    build_eval_markdown,
    build_review_markdown,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data", help="Directory containing supplied CSV files")
    parser.add_argument("--out-dir", default="analysis/evaluation", help="Directory for evaluation files")
    parser.add_argument("--bootstrap-samples", type=int, default=2_000)
    parser.add_argument(
        "--baseline", default="analysis/regression_baseline.json",
        help="Committed release thresholds and training-data hash",
    )
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    data_dir = Path(arguments.data_dir)
    out_dir = Path(arguments.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Loading validated data...")
    rows = load_order_rows(data_dir / "order_lines_train.csv", require_label=True)
    matcher = Matcher.from_data_dir(data_dir)
    review_path = Path("analysis/manual_review_conclusions.json")
    review_conclusions = json.loads(review_path.read_text(encoding="utf-8"))
    if len(review_conclusions) != 20:
        raise ValueError("Exactly 20 completed review conclusions are required")
    review_ids = [conclusion["line_id"] for conclusion in review_conclusions]
    if len(set(review_ids)) != 20:
        raise ValueError("Review conclusion line IDs must be unique")
    training_ids = {row["line_id"] for row in rows}
    missing_review_ids = sorted(set(review_ids) - training_ids)
    if missing_review_ids:
        raise ValueError(f"Reviewed lines were not found in training data: {missing_review_ids}")
    label_path = Path("analysis/label_review_conclusions.json")
    label_conclusions = json.loads(label_path.read_text(encoding="utf-8"))
    label_issue_count = len(label_conclusions)
    if label_issue_count < 3:
        raise ValueError("At least three supported label issues are required")
    label_ids = [conclusion["line_id"] for conclusion in label_conclusions]
    if len(set(label_ids)) != label_issue_count:
        raise ValueError("Label-review line IDs must be unique")
    missing_label_ids = sorted(set(label_ids) - training_ids)
    if missing_label_ids:
        raise ValueError(f"Label-review lines were not found in training data: {missing_label_ids}")

    print("Comparing deterministic retrieval strategies...")
    strategies = compare_strategies(matcher, rows)
    write_json(out_dir / "strategy_comparison.json", strategies)

    print("Building grouped out-of-fold predictions...")
    out_of_fold = grouped_out_of_fold_predictions(matcher, rows, fold_count=5)
    points = sweep_operating_points(out_of_fold)
    selected_point, gate_passed = select_operating_point(points)
    if gate_passed:
        selected_lines = apply_operating_point(
            out_of_fold,
            selected_point["confidence_threshold"],
            selected_point["margin_threshold"],
        )
    else:
        selected_lines = apply_operating_point(out_of_fold, 1.01, 1.0)
        selected_point = {
            "confidence_threshold": 1.01,
            "margin_threshold": 1.0,
            "selection_policy": "review_only",
            **calculate_metrics(selected_lines),
        }
    selected_metrics = calculate_metrics(selected_lines)

    training_hash = hashlib.sha256(
        (data_dir / "order_lines_train.csv").read_bytes()
    ).hexdigest()
    baseline = json.loads(Path(arguments.baseline).read_text(encoding="utf-8"))
    gate_failures = regression_gate_failures(
        selected_metrics,
        baseline,
        training_hash,
        selected_point["selection_policy"],
    )
    if gate_failures:
        raise ValueError("Regression gates failed:\n- " + "\n- ".join(gate_failures))

    print("Measuring uncertainty and calibration...")
    uncertainty = bootstrap_uncertainty(
        selected_lines, sample_count=arguments.bootstrap_samples
    )
    calibration = calibration_bins(out_of_fold)
    tenant_results = metric_breakdown(selected_lines, "tenant")
    reason_results = metric_breakdown(selected_lines, "reason_code")
    segment_results = metric_breakdown(selected_lines, "segment")

    write_csv(out_dir / "operating_points.csv", points)
    write_csv(out_dir / "calibration.csv", calibration)
    write_csv(
        out_dir / "oof_predictions.csv",
        [evaluated_line_to_csv(line) for line in selected_lines],
    )
    write_simple_svg(
        out_dir / "precision_coverage.svg", points, "precision_auto",
        "Precision versus coverage", "AUTO precision",
    )
    write_simple_svg(
        out_dir / "net_cost.svg", points, "net_cost_seconds",
        "Net cost versus coverage", "Net cost in seconds",
    )

    frozen_config = {
        "status": "frozen_after_manual_review",
        "strategy": "hybrid",
        "confidence_threshold": selected_point["confidence_threshold"],
        "margin_threshold": selected_point["margin_threshold"],
        "selection_policy": selected_point["selection_policy"],
        "normal_uncertainty_gate_passed": (
            selected_point["selection_policy"] == "full_uncertainty_policy"
        ),
        "small_sample_risk_acknowledged_after_manual_review": (
            selected_point["selection_policy"] == "perfect_observed_small_sample"
        ),
        "precision_policy": {
            "normal_observed_precision": 0.98,
            "normal_wilson_lower_floor": 0.927,
            "fallback_observed_precision": 1.0,
        },
        "precision_wilson_floor": 0.927,
        "random_seed": 17,
        "training_rows": len(rows),
        "training_file_sha256": training_hash,
        "review_complete": True,
        "reviewed_lines": len(review_conclusions),
        "label_issues": label_issue_count,
        "holdout_run_allowed": True,
        "regression_gates_passed": True,
    }
    proposed_config = {
        **frozen_config,
        "status": "superseded_by_frozen_config",
        "holdout_run_allowed": False,
    }
    write_json(out_dir / "proposed_matcher_config.json", proposed_config)
    write_json(Path("matcher_config.json"), frozen_config)
    write_json(out_dir / "selected_metrics.json", {
        "operating_point_allowed": gate_passed,
        "normal_uncertainty_gate_passed": (
            selected_point["selection_policy"] == "full_uncertainty_policy"
        ),
        "small_sample_risk_acknowledged": (
            selected_point["selection_policy"] == "perfect_observed_small_sample"
        ),
        "selection_policy": selected_point["selection_policy"],
        "metrics": selected_metrics,
        "uncertainty": uncertainty,
        "tenant": tenant_results,
        "segment": segment_results,
        "reason_code": reason_results,
    })

    selected_by_id = {line.row["line_id"]: line for line in selected_lines}
    review_lines = [selected_by_id[line_id] for line_id in review_ids]
    invalid_review_lines = [
        line.row["line_id"] for line in review_lines
        if not line.gt_item_code
        or not line.top
        or line.top.item_code == line.gt_item_code
    ]
    if invalid_review_lines:
        raise ValueError(
            "Manual error review must contain 20 answerable top-candidate failures: "
            f"{invalid_review_lines}"
        )
    conclusions_by_id = {
        conclusion["line_id"]: conclusion for conclusion in review_conclusions
    }
    (out_dir / "manual_review_20.md").write_text(
        build_review_markdown(
            review_lines,
            matcher.data.all_items_by_code,
            conclusions_by_id,
        ),
        encoding="utf-8",
    )
    Path("EVAL.md").write_text(
        build_eval_markdown(
            strategy_results=strategies,
            selected_metrics=selected_metrics,
            selected_point=selected_point,
            uncertainty=uncertainty,
            tenant_results=tenant_results,
            reason_results=reason_results,
            segment_results=segment_results,
            calibration=calibration,
            review_conclusions=review_conclusions,
            label_conclusions=label_conclusions,
        ),
        encoding="utf-8",
    )

    # The final ranker is fitted to prove that the frozen build step works. The
    # holdout is not loaded by this command.
    print("Fitting the frozen ranker on all training rows...")
    fit_final_ranker(matcher, rows)
    print(json.dumps(selected_metrics, indent=2, sort_keys=True))
    print(f"Final report: {Path('EVAL.md').resolve()}")
    print(f"Manual review pack: {(out_dir / 'manual_review_20.md').resolve()}")
    print(f"Frozen config: {Path('matcher_config.json').resolve()}")
    print("Holdout generation was not run.")


if __name__ == "__main__":
    main()
