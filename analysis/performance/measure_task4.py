#!/usr/bin/env python3
"""Measure Task 4 without running the original full-window report.

The script uses small, explicit probes:

* scaling probes run the original query for one day and a few tenants;
* ablation probes run one tenant/day and remove one output metric at a time;
* component probes time the two expensive building blocks in the rewrite.

The SQL splitter only needs to understand the top-level SELECT list in the
shipped query. It tracks parenthesis depth so commas inside subqueries are not
mistaken for column separators.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import time
from pathlib import Path


METRIC_ALIASES = [
    "lines_accepted",
    "candidates_considered",
    "avg_accept_score",
    "max_latency_ms",
    "avg_latency_ms",
    "distinct_customers",
    "repeat_items_prev_day",
    "accepted_disabled",
]


def split_outer_select(sql: str) -> tuple[list[str], str]:
    """Return top-level SELECT expressions and the remaining outer query."""
    select_start = sql.upper().index("SELECT") + len("SELECT")
    depth = 0
    expression_start = select_start
    expressions: list[str] = []
    index = select_start
    while index < len(sql):
        character = sql[index]
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif character == "," and depth == 0:
            expressions.append(sql[expression_start:index].strip())
            expression_start = index + 1
        elif depth == 0 and sql[index:index + 4].upper() == "FROM":
            expressions.append(sql[expression_start:index].strip())
            return expressions, sql[index:]
        index += 1
    raise ValueError("Could not find the outer FROM clause")


def build_probe(
    baseline_sql: str,
    *,
    date_from: str,
    date_to: str,
    tenants: list[str],
    omit_alias: str | None = None,
) -> str:
    """Narrow the shipped query and optionally remove one metric."""
    # Remove line comments before splitting because some comments contain
    # commas that are not SQL column separators.
    sql_without_comments = "\n".join(
        line.split("--", 1)[0] for line in baseline_sql.splitlines()
    )
    expressions, remainder = split_outer_select(sql_without_comments)
    if omit_alias:
        marker = f"AS {omit_alias}".upper()
        expressions = [part for part in expressions if marker not in part.upper()]
    narrowed = "SELECT\n    " + ",\n    ".join(expressions) + "\n" + remainder
    narrowed = narrowed.replace("'2026-05-01'", f"'{date_from}'")
    narrowed = narrowed.replace("'2026-06-30'", f"'{date_to}'")
    tenant_values = ", ".join(f"'{tenant}'" for tenant in tenants)
    narrowed = narrowed.replace(
        "GROUP BY t.tenant_id",
        f"AND ol.tenant_id IN ({tenant_values})\nGROUP BY t.tenant_id",
        1,
    )
    return narrowed


def time_query(connection: sqlite3.Connection, sql: str, repeat: int = 1) -> dict:
    """Run a read-only query and return stable timing and row-count fields."""
    times: list[float] = []
    row_count = 0
    for _ in range(repeat):
        started = time.perf_counter()
        row_count = len(connection.execute(sql).fetchall())
        times.append(time.perf_counter() - started)
    return {
        "rows": row_count,
        "min_s": min(times),
        "median_s": statistics.median(times),
        "max_s": max(times),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/perf.sqlite")
    parser.add_argument("--baseline-sql", default="starter/report_query.sql")
    parser.add_argument("--out", default="analysis/performance/measurements.json")
    arguments = parser.parse_args()

    baseline_sql = Path(arguments.baseline_sql).read_text(encoding="utf-8")
    connection = sqlite3.connect(arguments.db)
    output_path = Path(arguments.out)
    existing = (
        json.loads(output_path.read_text(encoding="utf-8"))
        if output_path.exists()
        else {}
    )

    # Same number of output groups, sharply different source volume.
    scaling_cases = {
        "one_day_heavy_tenant": ("2026-05-01", "2026-05-01", ["T001"]),
        "one_day_light_tenant": ("2026-05-01", "2026-05-01", ["T040"]),
        "one_day_two_tenants": ("2026-05-01", "2026-05-01", ["T001", "T002"]),
        "one_day_four_tenants": (
            "2026-05-01", "2026-05-01", ["T001", "T002", "T003", "T004"]
        ),
        "two_days_one_tenant": ("2026-05-01", "2026-05-02", ["T001"]),
        "four_days_one_tenant": ("2026-05-01", "2026-05-04", ["T001"]),
        "one_day_all_tenants": (
            "2026-05-01",
            "2026-05-01",
            [f"T{number:03d}" for number in range(1, 41)],
        ),
        "two_days_all_tenants": (
            "2026-05-01",
            "2026-05-02",
            [f"T{number:03d}" for number in range(1, 41)],
        ),
    }
    scaling = dict(existing.get("scaling", {}))
    for name, (date_from, date_to, tenants) in scaling_cases.items():
        if name in scaling:
            continue
        scaling[name] = time_query(
            connection,
            build_probe(
                baseline_sql,
                date_from=date_from,
                date_to=date_to,
                tenants=tenants,
            ),
        )
        print(f"scaling {name}: {scaling[name]}", flush=True)

    full_probe = build_probe(
        baseline_sql,
        date_from="2026-05-01",
        date_to="2026-05-01",
        tenants=["T001"],
    )
    ablations = dict(existing.get("ablations", {}))
    if "all_metrics" not in ablations:
        ablations["all_metrics"] = time_query(connection, full_probe)
        print(f"ablation all_metrics: {ablations['all_metrics']}", flush=True)
    for alias in METRIC_ALIASES:
        result_name = f"without_{alias}"
        if result_name in ablations:
            continue
        probe = build_probe(
            baseline_sql,
            date_from="2026-05-01",
            date_to="2026-05-01",
            tenants=["T001"],
            omit_alias=alias,
        )
        ablations[result_name] = time_query(connection, probe)
        print(
            f"ablation without_{alias}: {ablations[result_name]}",
            flush=True,
        )

    connection.close()
    result = {"scaling": scaling, "ablations": ablations}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
