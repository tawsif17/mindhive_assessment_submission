"""Reproducible training evaluation for the order-line matcher.

No hidden generator field is used. All segments are created from fields that are
available when a real order line is matched.
"""

from __future__ import annotations

import csv
import json
import math
import random
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from sklearn.model_selection import GroupKFold

from .core import Matcher
from .model import ProbabilityRanker, fit_ranker_with_group_calibration
from .text import is_non_item_text, normalise_text
from .types import CandidateEvidence, MatchResult, OrderLine


COST_CORRECT_AUTO = -20
COST_ABSTENTION = 40
COST_WRONG_AUTO = 800
PREDICTION_COLUMNS = [
    "line_id", "item_code", "confidence", "decision", "reason_code", "candidates"
]


@dataclass
class EvaluatedLine:
    """One out-of-fold candidate result before or after a decision limit is applied."""

    row: dict[str, str]
    candidates: list[CandidateEvidence]
    latency_ms: float
    segment: str
    decision: str = "review"
    predicted_item_code: str = ""
    reason_code: str = "low_confidence"

    @property
    def gt_item_code(self) -> str:
        return self.row.get("gt_item_code", "").strip()

    @property
    def top(self) -> CandidateEvidence | None:
        return self.candidates[0] if self.candidates else None

    @property
    def confidence(self) -> float:
        return self.top.confidence if self.top else 0.0

    @property
    def margin(self) -> float:
        return self.top.margin if self.top else 0.0


def customer_group(row: dict[str, str]) -> str:
    """Return the group used to keep customers separated across folds."""
    return f"{row['tenant'].lower()}|{row['customer_id']}"


def candidate_training_rows(
    matcher: Matcher,
    rows: list[dict[str, str]],
) -> tuple[list[list[float]], list[int], list[str]]:
    """Create candidate-level features and labels from visible training rows."""
    features: list[list[float]] = []
    labels: list[int] = []
    groups: list[str] = []
    for row in rows:
        line = OrderLine.from_dict(row)
        candidates, _metadata = matcher.retrieve(line, strategy="hybrid", candidate_limit=20)
        ground_truth = row.get("gt_item_code", "").strip()
        for candidate in candidates:
            features.append(candidate.feature_values())
            labels.append(int(bool(ground_truth) and candidate.item_code == ground_truth))
            groups.append(customer_group(row))
    return features, labels, groups


def fit_final_ranker(matcher: Matcher, rows: list[dict[str, str]]) -> ProbabilityRanker:
    """Fit the final ranker on all training rows after evaluation."""
    features, labels, groups = candidate_training_rows(matcher, rows)
    return fit_ranker_with_group_calibration(features, labels, groups)


def grouped_out_of_fold_predictions(
    base_matcher: Matcher,
    rows: list[dict[str, str]],
    fold_count: int = 5,
) -> list[EvaluatedLine]:
    """Score every line with a model that did not fit its customer group."""
    groups = [customer_group(row) for row in rows]
    unique_groups = sorted(set(groups))
    if len(unique_groups) < fold_count:
        raise ValueError(f"At least {fold_count} customer groups are required")

    splitter = GroupKFold(n_splits=fold_count)
    indexes = list(range(len(rows)))
    output: dict[int, EvaluatedLine] = {}
    for train_indexes, validation_indexes in splitter.split(indexes, groups=groups):
        train_rows = [rows[index] for index in train_indexes]
        features, labels, candidate_groups = candidate_training_rows(base_matcher, train_rows)
        ranker = fit_ranker_with_group_calibration(features, labels, candidate_groups)
        fold_matcher = base_matcher.with_ranker(ranker)

        for row_index in validation_indexes:
            row = rows[row_index]
            line = OrderLine.from_dict(row)
            started = time.perf_counter()
            candidates, _metadata = fold_matcher.retrieve(
                line, strategy="hybrid", candidate_limit=20
            )
            latency_ms = (time.perf_counter() - started) * 1_000
            segment = assign_segment(row, candidates)
            output[row_index] = EvaluatedLine(row, candidates[:3], latency_ms, segment)
    return [output[index] for index in range(len(rows))]


def assign_segment(
    row: dict[str, str], candidates: list[CandidateEvidence] | None = None
) -> str:
    """Assign one main segment using only values visible during matching."""
    if row.get("buyer_sku", "").strip() or row.get("raw_barcode", "").strip():
        return "identifier_present"
    raw_text = row.get("raw_text", "")
    if is_non_item_text(raw_text):
        return "non_item_like"
    normalised = normalise_text(raw_text)
    pack_words = {"box", "carton", "packet", "pack", "outer", "dozen"}
    if row.get("uom_text", "").strip() or pack_words.intersection(normalised.split()):
        return "pack_or_uom"
    if len(normalised.split()) <= 3:
        return "sparse_text"
    if candidates:
        top = candidates[0]
        if top.active_twin or top.margin < 0.03:
            return "ambiguous_candidates"
    if any(character in raw_text for character in ("/", "#", "_")) or "  " in raw_text:
        return "noisy_text"
    return "plain_text"


def apply_operating_point(
    lines: list[EvaluatedLine], confidence_threshold: float, margin_threshold: float
) -> list[EvaluatedLine]:
    """Apply answer/review/reject rules to already scored out-of-fold candidates."""
    decided: list[EvaluatedLine] = []
    for source in lines:
        line = EvaluatedLine(
            row=source.row,
            candidates=source.candidates,
            latency_ms=source.latency_ms,
            segment=source.segment,
        )
        if is_non_item_text(line.row.get("raw_text", "")):
            line.decision = "reject"
            line.reason_code = "not_an_item"
        elif not line.top:
            line.decision = "reject"
            line.reason_code = "no_candidate"
        elif line.top.safety_blocks:
            line.decision = "review"
            line.reason_code = line.top.safety_blocks[0]
        elif line.top.has_strong_identifier() or (
            line.confidence >= confidence_threshold and line.margin >= margin_threshold
        ):
            line.decision = "auto"
            line.predicted_item_code = line.top.item_code
            line.reason_code = reason_for_candidate(line.top)
        else:
            line.decision = "review"
            line.reason_code = (
                "low_margin" if line.margin < margin_threshold else "low_confidence"
            )
        decided.append(line)
    return decided


def reason_for_candidate(candidate: CandidateEvidence) -> str:
    if candidate.barcode_exact:
        return "barcode_unique"
    if candidate.alias_exact:
        return "alias_current_unique"
    if candidate.item_code_exact:
        return "item_code_exact"
    if candidate.part_number_exact:
        return "part_number_unique"
    return "text_high_margin"


def calculate_metrics(lines: list[EvaluatedLine]) -> dict[str, Any]:
    """Calculate the business, retrieval, safety, and latency metrics."""
    total = len(lines)
    automatic = [line for line in lines if line.decision == "auto"]
    correct_auto = [
        line for line in automatic
        if line.gt_item_code and line.predicted_item_code == line.gt_item_code
    ]
    wrong_auto = [line for line in automatic if line not in correct_auto]
    abstentions = [line for line in lines if line.decision != "auto"]
    blanks = [line for line in lines if not line.gt_item_code]
    blank_refusals = [line for line in blanks if line.decision != "auto"]
    answerable = [line for line in lines if line.gt_item_code]
    reviewed_answerable = [line for line in abstentions if line.gt_item_code]
    recall_hits = [
        line for line in answerable
        if line.gt_item_code in [candidate.item_code for candidate in line.candidates]
    ]
    reviewed_hits = [
        line for line in reviewed_answerable
        if line.gt_item_code in [candidate.item_code for candidate in line.candidates]
    ]
    cross_tenant = [
        line for line in automatic
        if not item_belongs_to_tenant(line.predicted_item_code, line.row["tenant"])
    ]
    blocked_auto = [
        line for line in automatic if line.top and line.top.safety_blocks
    ]
    latencies = sorted(line.latency_ms for line in lines)
    net_cost = (
        len(correct_auto) * COST_CORRECT_AUTO
        + len(wrong_auto) * COST_WRONG_AUTO
        + len(abstentions) * COST_ABSTENTION
    )
    precision = safe_divide(len(correct_auto), len(automatic))
    return {
        "rows": total,
        "precision_auto": precision,
        "precision_wilson_lower_95": wilson_lower_bound(len(correct_auto), len(automatic)),
        "coverage": safe_divide(len(automatic), total),
        "correct_auto": len(correct_auto),
        "wrong_auto": len(wrong_auto),
        "net_cost_seconds": net_cost,
        "abstentions": len(abstentions),
        "correct_refusal_rate_blank": safe_divide(len(blank_refusals), len(blanks)),
        "recall_at_3_answerable": safe_divide(len(recall_hits), len(answerable)),
        "recall_at_3_reviewed": safe_divide(len(reviewed_hits), len(reviewed_answerable)),
        "cross_tenant_violations": len(cross_tenant),
        "safety_block_auto_violations": len(blocked_auto),
        "p50_latency_ms": nearest_rank_percentile(latencies, 0.50),
        "p95_latency_ms": nearest_rank_percentile(latencies, 0.95),
        "max_latency_ms": max(latencies, default=0.0),
    }


def metric_breakdown(lines: list[EvaluatedLine], field: str) -> dict[str, dict[str, Any]]:
    """Calculate compact metrics for tenant, reason code, or observable segment."""
    groups: dict[str, list[EvaluatedLine]] = defaultdict(list)
    for line in lines:
        if field == "tenant":
            value = line.row["tenant"]
        elif field == "segment":
            value = line.segment
        elif field == "reason_code":
            value = line.reason_code
        else:
            raise ValueError(f"Unknown breakdown field: {field}")
        groups[value].append(line)
    output: dict[str, dict[str, Any]] = {}
    for value, group in sorted(groups.items()):
        metrics = calculate_metrics(group)
        output[value] = {
            key: metrics[key]
            for key in (
                "rows", "precision_auto", "coverage", "wrong_auto",
                "net_cost_seconds", "recall_at_3_answerable"
            )
        }
    return output


def sweep_operating_points(lines: list[EvaluatedLine]) -> list[dict[str, Any]]:
    """Measure a fixed grid of confidence and margin limits."""
    confidence_values = [
        0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.925, 0.95,
        0.96, 0.97, 0.98, 0.985, 0.99, 0.995, 1.0,
    ]
    margin_values = [0.00, 0.02, 0.05, 0.08, 0.10, 0.15, 0.20]
    points: list[dict[str, Any]] = []
    for confidence in confidence_values:
        for margin in margin_values:
            metrics = calculate_metrics(apply_operating_point(lines, confidence, margin))
            points.append({
                "confidence_threshold": confidence,
                "margin_threshold": margin,
                **metrics,
            })
    return points


def select_operating_point(points: list[dict[str, Any]]) -> tuple[dict[str, Any], bool]:
    """Select the normal policy first, then the approved perfect-result fallback."""
    passing = [
        point for point in points
        if point["precision_auto"] >= 0.98
        and point["precision_wilson_lower_95"] > 0.927
        and point["p95_latency_ms"] <= 250.0
        and point["cross_tenant_violations"] == 0
        and point["safety_block_auto_violations"] == 0
    ]
    if passing:
        selected = min(
            passing,
            key=lambda point: (
                point["net_cost_seconds"],
                -point["recall_at_3_answerable"],
                -point["coverage"],
                point["confidence_threshold"],
                point["margin_threshold"],
            ),
        )
        return {**selected, "selection_policy": "full_uncertainty_policy"}, True

    # A small-sample fallback was approved after the draft review. It does not
    # allow known errors. Every hard safety and latency gate still applies.
    perfect_observed = [
        point for point in points
        if point["correct_auto"] > 0
        and point["precision_auto"] == 1.0
        and point["wrong_auto"] == 0
        and point["p95_latency_ms"] <= 250.0
        and point["cross_tenant_violations"] == 0
        and point["safety_block_auto_violations"] == 0
    ]
    if perfect_observed:
        selected = max(
            perfect_observed,
            key=lambda point: (
                point["coverage"],
                -point["net_cost_seconds"],
                point["recall_at_3_answerable"],
                point["confidence_threshold"],
                -point["margin_threshold"],
            ),
        )
        return {**selected, "selection_policy": "perfect_observed_small_sample"}, True

    return {
        "confidence_threshold": 1.01,
        "margin_threshold": 1.0,
        "selection_policy": "review_only",
    }, False


def calibration_bins(lines: list[EvaluatedLine]) -> list[dict[str, Any]]:
    """Compare top-candidate confidence with observed correctness."""
    limits = [(0.00, 0.50), (0.50, 0.70), (0.70, 0.80), (0.80, 0.90),
              (0.90, 0.95), (0.95, 0.98), (0.98, 1.000001)]
    output: list[dict[str, Any]] = []
    for lower, upper in limits:
        members = [
            line for line in lines
            if line.top and lower <= line.confidence < upper
        ]
        correct = [
            line for line in members
            if line.gt_item_code and line.top and line.top.item_code == line.gt_item_code
        ]
        output.append({
            "lower": lower,
            "upper": min(upper, 1.0),
            "rows": len(members),
            "mean_confidence": statistics.fmean(line.confidence for line in members) if members else 0.0,
            "actual_correctness": safe_divide(len(correct), len(members)),
        })
    return output


def compare_strategies(matcher: Matcher, rows: list[dict[str, str]]) -> dict[str, Any]:
    """Compare deterministic retrieval lanes before choosing the hybrid ranker."""
    strategies = ["exact", "rapidfuzz", "word_tfidf", "char_tfidf", "hybrid"]
    results: dict[str, Any] = {}
    for strategy in strategies:
        answerable = 0
        top_one_hits = 0
        top_three_hits = 0
        candidate_counts: list[int] = []
        latencies: list[float] = []
        for row in rows:
            started = time.perf_counter()
            candidates, _metadata = matcher.retrieve(
                OrderLine.from_dict(row), strategy=strategy, candidate_limit=20
            )
            latencies.append((time.perf_counter() - started) * 1_000)
            gt = row.get("gt_item_code", "").strip()
            candidate_counts.append(len(candidates))
            if gt:
                answerable += 1
                if candidates and candidates[0].item_code == gt:
                    top_one_hits += 1
                if gt in [candidate.item_code for candidate in candidates[:3]]:
                    top_three_hits += 1
        results[strategy] = {
            "answerable_rows": answerable,
            "top_1_recall": safe_divide(top_one_hits, answerable),
            "forced_accuracy_all_rows": safe_divide(top_one_hits, len(rows)),
            "recall_at_3": safe_divide(top_three_hits, answerable),
            "mean_candidates": statistics.fmean(candidate_counts),
            "p95_latency_ms": nearest_rank_percentile(sorted(latencies), 0.95),
        }
    return results


def bootstrap_uncertainty(
    lines: list[EvaluatedLine], sample_count: int = 2_000, seed: int = 1729
) -> dict[str, list[float]]:
    """Return fixed-seed 95% intervals from customer-group bootstrap samples."""
    grouped: dict[str, list[EvaluatedLine]] = defaultdict(list)
    for line in lines:
        grouped[customer_group(line.row)].append(line)
    group_names = sorted(grouped)
    random_source = random.Random(seed)
    precision_values: list[float] = []
    coverage_values: list[float] = []
    cost_values: list[float] = []
    for _index in range(sample_count):
        sampled_names = [random_source.choice(group_names) for _name in group_names]
        sample = [line for name in sampled_names for line in grouped[name]]
        metrics = calculate_metrics(sample)
        precision_values.append(metrics["precision_auto"])
        coverage_values.append(metrics["coverage"])
        cost_values.append(float(metrics["net_cost_seconds"]))
    return {
        "precision_auto_95": quantile_interval(precision_values),
        "coverage_95": quantile_interval(coverage_values),
        "net_cost_seconds_95": quantile_interval(cost_values),
    }


def quantile_interval(values: list[float]) -> list[float]:
    ordered = sorted(values)
    if not ordered:
        return [0.0, 0.0]
    return [ordered[int(0.025 * (len(ordered) - 1))], ordered[int(0.975 * (len(ordered) - 1))]]


def wilson_lower_bound(successes: int, total: int, z: float = 1.96) -> float:
    """Return the lower end of a two-sided Wilson proportion interval."""
    if total == 0:
        return 0.0
    proportion = successes / total
    denominator = 1.0 + z * z / total
    centre = proportion + z * z / (2.0 * total)
    adjustment = z * math.sqrt(
        proportion * (1.0 - proportion) / total + z * z / (4.0 * total * total)
    )
    return (centre - adjustment) / denominator


def nearest_rank_percentile(values: list[float], proportion: float) -> float:
    """Return a nearest-rank percentile from sorted values."""
    if not values:
        return 0.0
    rank = max(1, math.ceil(proportion * len(values)))
    return float(values[rank - 1])


def safe_divide(numerator: int | float, denominator: int | float) -> float:
    return float(numerator / denominator) if denominator else 0.0


def regression_gate_failures(
    metrics: dict[str, Any],
    baseline: dict[str, Any],
    training_file_sha256: str,
    selection_policy: str,
) -> list[str]:
    """Return release-gate failures against the committed baseline."""
    failures: list[str] = []
    if training_file_sha256 != baseline["training_file_sha256"]:
        failures.append("training data hash changed")
    if selection_policy not in baseline["allowed_selection_policies"]:
        failures.append(f"selection policy is not allowed: {selection_policy}")

    minimums = {
        "precision_auto": baseline["minimum_auto_precision"],
        "coverage": baseline["minimum_coverage"],
        "recall_at_3_answerable": baseline["minimum_recall_at_3_answerable"],
        "correct_refusal_rate_blank": baseline["minimum_blank_refusal_rate"],
    }
    maximums = {
        "wrong_auto": baseline["maximum_wrong_auto"],
        "net_cost_seconds": baseline["maximum_net_cost_seconds"],
        "cross_tenant_violations": baseline["maximum_cross_tenant_violations"],
        "safety_block_auto_violations": baseline["maximum_safety_block_auto_violations"],
        "p95_latency_ms": baseline["maximum_p95_latency_ms"],
    }
    for name, limit in minimums.items():
        if metrics[name] < limit:
            failures.append(f"{name} {metrics[name]:.6f} is below {limit:.6f}")
    for name, limit in maximums.items():
        if metrics[name] > limit:
            failures.append(f"{name} {metrics[name]:.6f} exceeds {limit:.6f}")
    return failures


def item_belongs_to_tenant(item_code: str, tenant: str) -> bool:
    prefixes = {"acme": "ACM-", "nordic": "NRD-"}
    return item_code.startswith(prefixes.get(tenant.lower(), "__UNKNOWN__"))


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if columns is None:
        columns = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_simple_svg(
    path: Path,
    points: list[dict[str, Any]],
    y_field: str,
    title: str,
    y_label: str,
) -> None:
    """Write a dependency-free line chart as SVG."""
    width, height = 760, 460
    left, right, top, bottom = 80, 30, 50, 70
    plot_width = width - left - right
    plot_height = height - top - bottom
    compact: dict[float, float] = {}
    for point in points:
        coverage = float(point["coverage"])
        value = float(point[y_field])
        if coverage not in compact or (
            y_field == "precision_auto" and value > compact[coverage]
        ) or (y_field != "precision_auto" and value < compact[coverage]):
            compact[coverage] = value
    ordered = sorted(compact.items())
    y_values = [value for _coverage, value in ordered] or [0.0]
    y_min = 0.0 if y_field == "precision_auto" else min(0.0, min(y_values))
    y_max = 1.0 if y_field == "precision_auto" else max(y_values)
    if y_max == y_min:
        y_max = y_min + 1.0

    def x_position(value: float) -> float:
        return left + value * plot_width

    def y_position(value: float) -> float:
        return top + (y_max - value) / (y_max - y_min) * plot_height

    polyline = " ".join(f"{x_position(x):.1f},{y_position(y):.1f}" for x, y in ordered)
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="760" height="460" viewBox="0 0 760 460">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="380" y="28" text-anchor="middle" font-family="Arial" font-size="18">{title}</text>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" stroke="#333"/>',
        f'<line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}" stroke="#333"/>',
        f'<polyline points="{polyline}" fill="none" stroke="#1261a0" stroke-width="2"/>',
        f'<text x="380" y="445" text-anchor="middle" font-family="Arial" font-size="13">Coverage</text>',
        f'<text x="18" y="230" transform="rotate(-90 18 230)" text-anchor="middle" font-family="Arial" font-size="13">{y_label}</text>',
    ]
    for tick in range(6):
        x_value = tick / 5
        x = x_position(x_value)
        lines.append(f'<text x="{x:.1f}" y="410" text-anchor="middle" font-family="Arial" font-size="11">{x_value:.1f}</text>')
        y_value = y_min + (y_max - y_min) * tick / 5
        y = y_position(y_value)
        lines.append(f'<text x="72" y="{y+4:.1f}" text-anchor="end" font-family="Arial" font-size="11">{y_value:.2f}</text>')
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def evaluated_line_to_csv(line: EvaluatedLine) -> dict[str, Any]:
    top = line.top
    return {
        "line_id": line.row["line_id"],
        "tenant": line.row["tenant"],
        "customer_id": line.row["customer_id"],
        "segment": line.segment,
        "gt_item_code": line.gt_item_code,
        "decision": line.decision,
        "item_code": line.predicted_item_code,
        "confidence": f"{line.confidence:.6f}",
        "margin": f"{line.margin:.6f}",
        "reason_code": line.reason_code,
        "candidates": "|".join(
            f"{candidate.item_code}:{candidate.confidence:.6f}"
            for candidate in line.candidates[:3]
        ),
        "top_evidence": json.dumps(top.to_dict(), sort_keys=True) if top else "{}",
        "latency_ms": f"{line.latency_ms:.3f}",
    }
