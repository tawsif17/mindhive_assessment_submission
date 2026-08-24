#!/usr/bin/env python3
"""Create the one persistent index used by the Task 4 report.

Run this once after building or migrating the database:

    python apply_report_indexes.py --db ../data/perf.sqlite

The expression matches the report's tenant/day/item access pattern. Keeping
the migration in a small script makes the clean-machine run reproducible with
Python alone; no sqlite3 command-line program is required.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import time


INDEX_NAME = "idx_match_event_tenant_day_item"
INDEX_SQL = f"""
CREATE INDEX IF NOT EXISTS {INDEX_NAME}
ON match_event(tenant_id, substr(created_at, 1, 10), item_code)
"""


def apply_index(database_path: str) -> dict[str, float | int]:
    """Create the idempotent index and report its one-time storage cost."""
    size_before = os.path.getsize(database_path)
    connection = sqlite3.connect(database_path)
    started = time.perf_counter()
    try:
        connection.execute(INDEX_SQL)
        connection.commit()
    finally:
        connection.close()
    elapsed = time.perf_counter() - started
    size_after = os.path.getsize(database_path)
    return {
        "elapsed_s": elapsed,
        "size_before_bytes": size_before,
        "size_after_bytes": size_after,
        "size_growth_bytes": size_after - size_before,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="../data/perf.sqlite")
    arguments = parser.parse_args()
    result = apply_index(arguments.db)
    print(
        f"{INDEX_NAME}: {result['elapsed_s']:.2f}s, "
        f"database growth {result['size_growth_bytes'] / 1_000_000:.1f} MB"
    )


if __name__ == "__main__":
    main()
