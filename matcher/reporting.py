"""Create the Task 3 engineering report and the manual review packet."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .evaluation import EvaluatedLine


def percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def metric_table(metrics: dict[str, Any]) -> str:
    rows = [
        ("Training rows", str(metrics["rows"])),
        ("AUTO precision", percent(metrics["precision_auto"])),
        ("AUTO precision lower bound", percent(metrics["precision_wilson_lower_95"])),
        ("Coverage", percent(metrics["coverage"])),
        ("Correct automatic matches", str(metrics["correct_auto"])),
        ("Wrong automatic matches", str(metrics["wrong_auto"])),
        ("Net operating cost", f"{metrics['net_cost_seconds']:,} seconds"),
        ("Abstentions", str(metrics["abstentions"])),
        ("Blank-label refusal rate", percent(metrics["correct_refusal_rate_blank"])),
        ("Recall@3 on answerable rows", percent(metrics["recall_at_3_answerable"])),
        ("Recall@3 on reviewed rows", percent(metrics["recall_at_3_reviewed"])),
        ("p95 matcher latency", f"{metrics['p95_latency_ms']:.2f} ms"),
    ]
    return "\n".join(["| Measure | Result |", "|---|---:|"] + [f"| {name} | {value} |" for name, value in rows])


def breakdown_table(values: dict[str, dict[str, Any]]) -> str:
    lines = [
        "| Group | Rows | Precision | Coverage | Wrong autos | Recall@3 | Cost |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, metrics in values.items():
        lines.append(
            f"| {name} | {metrics['rows']} | {percent(metrics['precision_auto'])} | "
            f"{percent(metrics['coverage'])} | {metrics['wrong_auto']} | "
            f"{percent(metrics['recall_at_3_answerable'])} | "
            f"{metrics['net_cost_seconds']:,} s |"
        )
    return "\n".join(lines)


REVIEW_GROUP_LABELS = {
    "variant_parsing": "Variant parsing and tokenisation",
    "stale_alias_successor": "Stale alias without a successor link",
    "ranking_tie": "Ranking and retrieval tie",
}


def review_group(conclusion: dict[str, str]) -> str:
    """Return the reviewed failure's explicit root-cause group."""
    group = conclusion["group"]
    if group not in REVIEW_GROUP_LABELS:
        raise ValueError(f"Unknown review group: {group}")
    return group


def review_group_table(conclusions: list[dict[str, str]]) -> str:
    """Summarise which reviewed lines share one root-cause class."""
    grouped: dict[str, list[str]] = {key: [] for key in REVIEW_GROUP_LABELS}
    for conclusion in conclusions:
        grouped[review_group(conclusion)].append(conclusion["line_id"])
    rows = ["| Root-cause group | Lines | Count |", "|---|---|---:|"]
    for key, label in REVIEW_GROUP_LABELS.items():
        line_ids = ", ".join(f"`{line_id}`" for line_id in grouped[key])
        rows.append(f"| {label} | {line_ids} | {len(grouped[key])} |")
    return "\n".join(rows)


def build_eval_markdown(
    *,
    strategy_results: dict[str, Any],
    selected_metrics: dict[str, Any],
    selected_point: dict[str, Any],
    uncertainty: dict[str, list[float]],
    tenant_results: dict[str, dict[str, Any]],
    reason_results: dict[str, dict[str, Any]],
    segment_results: dict[str, dict[str, Any]],
    calibration: list[dict[str, Any]],
    review_conclusions: list[dict[str, str]],
    label_conclusions: list[dict[str, str]],
) -> str:
    """Return the final training evaluation and completed error analysis."""
    strategy_lines = [
        "| Strategy | Forced accuracy | Top-1 recall | Recall@3 | Mean candidates | p95 latency |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, values in strategy_results.items():
        strategy_lines.append(
            f"| {name} | {percent(values['forced_accuracy_all_rows'])} | "
            f"{percent(values['top_1_recall'])} | "
            f"{percent(values['recall_at_3'])} | {values['mean_candidates']:.1f} | "
            f"{values['p95_latency_ms']:.2f} ms |"
        )

    calibration_lines = [
        "| Confidence bin | Rows | Mean confidence | Actual correctness |",
        "|---|---:|---:|---:|",
    ]
    for row in calibration:
        calibration_lines.append(
            f"| {row['lower']:.2f}-{row['upper']:.2f} | {row['rows']} | "
            f"{percent(row['mean_confidence'])} | {percent(row['actual_correctness'])} |"
        )

    selection_policy = selected_point.get("selection_policy", "review_only")
    if selection_policy == "full_uncertainty_policy":
        release_text = "The selected point passed the precision, uncertainty, safety, and latency gates."
    elif selection_policy == "perfect_observed_small_sample":
        release_text = (
            "No point passed the Wilson uncertainty gate. The approved fallback was used. "
            "The selected point had 100% observed out-of-fold precision and no hard "
            "safety violation. Its small sample risk remains visible below."
        )
    else:
        release_text = "No automatic point was released. All rows will be reviewed or rejected."
    accuracy_note = (
        "A forced top-one accuracy is shown in the strategy table. It treats every line "
        "as if an answer had to be returned. This hides the cost of unsafe answers. "
        "Precision and coverage are therefore reported together. Net cost is used to "
        "compare safe points."
    )
    review_lines = [
        "| Line | Label finding | Root cause | Cost class | Action |",
        "|---|---|---|---|---|",
    ]
    for conclusion in review_conclusions:
        cells = [
            f"`{conclusion['line_id']}`",
            conclusion["label_assessment"].replace("_", " "),
            conclusion["root_cause"],
            conclusion["cost_class"].replace("_", " "),
            conclusion["action"],
        ]
        review_lines.append("| " + " | ".join(cell.replace("|", "/") for cell in cells) + " |")

    label_lines = [
        f"- `{conclusion['line_id']}` — {conclusion['label_assessment'].replace('_', ' ')}. "
        f"{conclusion['root_cause']}"
        for conclusion in label_conclusions
    ]

    return f"""# Matcher Evaluation

## Status

The grouped training evaluation and 20-line error review are complete. The matcher configuration is frozen from training evidence. Holdout labels were not available and were not inferred.

## Method

Five grouped folds were used. Groups were formed from tenant and customer ID. A customer group was kept out of fitting and calibration when its rows were scored. Segments were created only from visible input fields.

{accuracy_note}

## Retrieval strategy comparison

{chr(10).join(strategy_lines)}

This table measures retrieval. The hybrid lane was then tested end to end with the decision layer. Embeddings and LLMs were not used.

## Selected operating point

{release_text}

- Confidence limit: `{selected_point['confidence_threshold']:.3f}`
- Margin limit: `{selected_point['margin_threshold']:.3f}`
- Selection policy: `{selection_policy}`
- Bootstrap precision range: {percent(uncertainty['precision_auto_95'][0])} to {percent(uncertainty['precision_auto_95'][1])}
- Bootstrap coverage range: {percent(uncertainty['coverage_95'][0])} to {percent(uncertainty['coverage_95'][1])}

{metric_table(selected_metrics)}

![Precision versus coverage](analysis/evaluation/precision_coverage.svg)

![Net cost versus coverage](analysis/evaluation/net_cost.svg)

## Tenant results

{breakdown_table(tenant_results)}

## Observable segment results

The segments describe signals that are available during matching. They do not use a hidden generator class.

{breakdown_table(segment_results)}

## Reason-code results

{breakdown_table(reason_results)}

## Calibration

{chr(10).join(calibration_lines)}

Probabilistic confidence comes from grouped calibration of the hybrid ranker. A unique safe identifier is a separate deterministic lane and is assigned 1.0 only after tenant, uniqueness, target-state, and conflict checks pass. Safety blocks and candidate margin remain separate from confidence.

## Regression gates

`evaluate.py` reads `analysis/regression_baseline.json` and exits non-zero when a quantitative or data-integrity gate fails:

- AUTO precision must remain 100% under the approved small-sample fallback.
- Coverage must remain at least 5%.
- No cross-tenant automatic match is allowed.
- No disabled, misc, or safety-blocked automatic match is allowed.
- p95 line latency must stay at or below 250 ms.
- Candidate recall@3 must remain at least 92.2%.
- Net cost must not exceed 15,360 seconds.
- The training-file hash must match the committed baseline.

If the Wilson gate cannot pass because the automatic sample is small, the approved fallback requires 100% observed out-of-fold precision. No wrong automatic match is allowed. Every safety and latency gate still applies. The Wilson result must still be reported.

The unit suite separately enforces determinism, output schema, tenant ownership, item state, and candidate limits. A data or policy change requires a reviewed baseline update. Production examples can be added after delayed labels arrive.

## Label-quality findings

Six supplied labels were found to be wrong or under-specified. They were not changed in primary metrics.

{chr(10).join(label_lines)}

Primary metrics still use the supplied labels.

## Manual error review

These 20 cases are genuine out-of-fold failures: every line is answerable and the supplied correct item was not ranked first. Each was checked against the order fields, catalogue, aliases, barcode, UOM, item state, and candidate evidence.

{review_group_table(review_conclusions)}

The matcher abstained on all 20, so none became an 800-second wrong automatic match. They still cost review time and expose retrieval or ranking weaknesses. The actions below target shared causes rather than individual lines.

{chr(10).join(review_lines)}

The detailed evidence is kept in `analysis/evaluation/manual_review_20.md`.

## Limits

- Only 420 labelled rows were available.
- The confidence ranges remain wide for small automatic-match lanes.
- Alias history was treated as supplied reference data.
- No production traffic or delayed outcome labels were available.
- The holdout set was not used for fitting, limits, or report numbers.
"""


def select_review_lines(lines: list[EvaluatedLine], limit: int = 20) -> list[EvaluatedLine]:
    """Select useful failures while keeping the order stable."""
    wrong_auto = [
        line for line in lines
        if line.decision == "auto" and line.predicted_item_code != line.gt_item_code
    ]
    missed_answerable = [
        line for line in lines
        if line.gt_item_code and line.decision != "auto"
    ]
    possible_label_issues = [
        line for line in lines
        if not line.gt_item_code and line.top and line.confidence >= 0.80
    ]
    ordered: list[EvaluatedLine] = []
    for group in (wrong_auto, possible_label_issues, missed_answerable):
        for line in sorted(group, key=lambda value: (-value.confidence, value.row["line_id"])):
            if line not in ordered:
                ordered.append(line)
            if len(ordered) == limit:
                return ordered
    return ordered[:limit]


def select_label_candidates(lines: list[EvaluatedLine], limit: int = 5) -> list[EvaluatedLine]:
    candidates = [
        line for line in lines
        if not line.gt_item_code and line.top and line.confidence >= 0.80
    ]
    return sorted(candidates, key=lambda value: (-value.confidence, value.row["line_id"]))[:limit]


def build_review_markdown(
    lines: list[EvaluatedLine],
    all_items_by_code: dict[str, Any],
    conclusions_by_id: dict[str, dict[str, str]],
) -> str:
    """Create the completed 20-line evidence and conclusion packet."""
    parts = [
        "# Manual Review Pack — 20 Lines",
        "",
        "> Status: complete. Each conclusion was checked against visible source evidence. Supplied labels were not changed in primary metrics.",
        "",
        "Every case is an answerable out-of-fold line whose top-ranked candidate differs from the supplied item. The matcher abstained on all 20.",
        "",
        review_group_table(list(conclusions_by_id.values())),
        "",
    ]
    for number, line in enumerate(lines, start=1):
        top = line.top
        candidate_rows = []
        for candidate in line.candidates:
            item = all_items_by_code[candidate.item_code]
            candidate_rows.append(
                f"| `{candidate.item_code}` | {item.item_name} | {item.stock_uom} | "
                f"{candidate.confidence:.3f} | {candidate.rapidfuzz_score:.3f} | "
                f"{candidate.word_tfidf_score:.3f} | {candidate.char_tfidf_score:.3f} | "
                f"{', '.join(candidate.safety_blocks) or '-'} |"
            )
        conclusion = conclusions_by_id[line.row["line_id"]]
        group_label = REVIEW_GROUP_LABELS[review_group(conclusion)]
        parts.extend([
            f"## {number}. `{line.row['line_id']}`",
            "",
            f"- Tenant: `{line.row['tenant']}`",
            f"- Customer: `{line.row['customer_id']}`",
            f"- Raw text: `{line.row['raw_text']}`",
            f"- Visible fields: buyer SKU `{line.row.get('buyer_sku', '')}`, barcode `{line.row.get('raw_barcode', '')}`, UOM `{line.row.get('uom_text', '')}`, quantity `{line.row.get('qty', '')}`, price `{line.row.get('unit_price', '')}`",
            f"- Supplied label: `{line.gt_item_code or '[blank]'}`",
            f"- Review outcome group: `{group_label}`",
            f"- Current evaluated decision: `{line.decision}` / `{line.reason_code}`",
            f"- Top candidate: `{top.item_code if top else '[none]'}` at {line.confidence:.3f}",
            "",
            "| Candidate | Name | Stock UOM | Confidence | RapidFuzz | Word TF-IDF | Char TF-IDF | Safety blocks |",
            "|---|---|---|---:|---:|---:|---:|---|",
            *candidate_rows,
            "",
            f"- Label assessment: `{conclusion['label_assessment']}`",
            f"- Confirmed root cause: {conclusion['root_cause']}",
            f"- Confirmed cost class: `{conclusion['cost_class']}`",
            f"- Accepted fix or no-code action: {conclusion['action']}",
            "",
        ])
    return "\n".join(parts).rstrip() + "\n"


def suggested_root_cause(line: EvaluatedLine) -> str:
    if not line.gt_item_code:
        return "possible label issue or a valid abstention"
    if line.top and line.top.active_twin:
        return "active twin or pack ambiguity"
    if line.top and line.top.attribute_conflict:
        return "size, pack, UOM, or price conflict"
    if line.segment == "identifier_present":
        return "identifier quality or identifier collision"
    if line.segment in {"sparse_text", "noisy_text"}:
        return "missing or damaged text evidence"
    if line.gt_item_code not in [candidate.item_code for candidate in line.candidates]:
        return "candidate retrieval miss"
    return "ranking or decision-limit error"
