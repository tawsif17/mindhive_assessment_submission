#!/usr/bin/env python3
"""Generate holdout predictions only from a manually frozen matcher config."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from matcher import Matcher, OrderLine
from matcher.data import load_order_rows
from matcher.evaluation import PREDICTION_COLUMNS, fit_final_ranker


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--out", default="predictions.csv")
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    config = json.loads(Path(arguments.config).read_text(encoding="utf-8"))
    if config.get("status") != "frozen_after_manual_review":
        raise SystemExit(
            "Holdout generation is blocked. The config must be frozen after manual review."
        )
    if not config.get("holdout_run_allowed", False):
        raise SystemExit("Holdout generation is blocked by the matcher config.")
    if not config.get("review_complete", False):
        raise SystemExit("Holdout generation is blocked until review is complete.")

    data_dir = Path(arguments.data_dir)
    training_path = data_dir / "order_lines_train.csv"
    training_hash = hashlib.sha256(training_path.read_bytes()).hexdigest()
    if training_hash != config.get("training_file_sha256"):
        raise SystemExit("Training data hash does not match the frozen config.")
    training_rows = load_order_rows(training_path, require_label=True)
    holdout_rows = load_order_rows(data_dir / "order_lines_holdout.csv", require_label=False)
    base_matcher = Matcher.from_data_dir(data_dir)
    ranker = fit_final_ranker(base_matcher, training_rows)
    matcher = base_matcher.with_ranker(
        ranker,
        confidence_threshold=float(config["confidence_threshold"]),
        margin_threshold=float(config["margin_threshold"]),
    )
    predictions = [
        matcher.match(OrderLine.from_dict(row)).to_prediction_row()
        for row in holdout_rows
    ]
    repeated_predictions = [
        matcher.match(OrderLine.from_dict(row)).to_prediction_row()
        for row in holdout_rows
    ]
    if predictions != repeated_predictions:
        raise ValueError("Repeated holdout matching produced different output")
    validate_predictions(predictions, holdout_rows, matcher)
    output_path = Path(arguments.out)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PREDICTION_COLUMNS)
        writer.writeheader()
        writer.writerows(predictions)
    print(f"Wrote {len(predictions)} rows to {output_path}")


def validate_predictions(
    predictions: list[dict[str, str]],
    source_rows: list[dict[str, str]],
    matcher: Matcher,
) -> None:
    """Apply the final holdout schema and safety checks before writing."""
    if len(predictions) != 300 or len(predictions) != len(source_rows):
        raise ValueError("Holdout output must contain exactly 300 rows")
    if len({row["line_id"] for row in predictions}) != len(predictions):
        raise ValueError("Holdout line IDs must be unique")
    source_by_id = {row["line_id"]: row for row in source_rows}
    for prediction in predictions:
        if list(prediction) != PREDICTION_COLUMNS:
            raise ValueError("Prediction columns do not match the required schema")
        if prediction["decision"] not in {"auto", "review", "reject"}:
            raise ValueError(f"Invalid decision: {prediction['decision']}")
        if prediction["decision"] != "auto" and prediction["item_code"]:
            raise ValueError("Non-auto predictions must have a blank item code")
        confidence = float(prediction["confidence"])
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("Prediction confidence must be between zero and one")
        if len([value for value in prediction["candidates"].split("|") if value]) > 3:
            raise ValueError("At most three candidates may be returned")
        source_tenant = source_by_id[prediction["line_id"]]["tenant"].lower()
        for candidate_pair in [
            value for value in prediction["candidates"].split("|") if value
        ]:
            candidate_code, separator, score_text = candidate_pair.partition(":")
            if not separator:
                raise ValueError("Candidate values must use item_code:score format")
            score = float(score_text)
            if not 0.0 <= score <= 1.0:
                raise ValueError("Candidate scores must be between zero and one")
            candidate_item = matcher.data.all_items_by_code[candidate_code]
            if (
                candidate_item.tenant != source_tenant
                or candidate_item.disabled
                or candidate_item.is_misc
            ):
                raise ValueError(
                    f"Unsafe candidate was returned: {prediction['line_id']}"
                )
        if prediction["decision"] == "auto":
            item = matcher.data.all_items_by_code[prediction["item_code"]]
            if item.tenant != source_tenant or item.disabled or item.is_misc:
                raise ValueError(f"Unsafe automatic match: {prediction['line_id']}")


if __name__ == "__main__":
    main()
