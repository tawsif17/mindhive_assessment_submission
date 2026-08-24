from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from starter.apply_report_indexes import INDEX_NAME, apply_index
from starter.make_perf_db import DDL


class ReportQueryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]
        self.connection = sqlite3.connect(":memory:")
        self.connection.executescript(DDL)
        self.connection.execute("INSERT INTO tenant VALUES ('T001', 'Tenant 1', 'growth')")
        self.connection.executemany(
            "INSERT INTO item VALUES (?, ?, ?, ?, ?)",
            [
                ("T001", "A", "Active A", "Group", 0),
                ("T001", "B", "Disabled B", "Group", 1),
                ("T001", "C", "Active C", "Group", 0),
            ],
        )
        self.connection.executemany(
            "INSERT INTO order_line VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("L0", "T001", "C0", "email_pdf", "2026-04-30T10:00:00Z", "old"),
                ("L1", "T001", "C1", "email_pdf", "2026-05-01T10:00:00Z", "one"),
                ("L2", "T001", "C2", "email_pdf", "2026-05-01T11:00:00Z", "two"),
                ("L3", "T001", "C1", "whatsapp", "2026-05-01T12:00:00Z", "three"),
            ],
        )
        events = [
            (1, "T001", "L0", "A", "lexical", 0.8, 1, 1, 5, "2026-04-30T10:00:00Z"),
            (2, "T001", "L1", "A", "lexical", 0.9, 1, 1, 10, "2026-05-01T10:00:00Z"),
            (3, "T001", "L1", "C", "rerank", 0.5, 2, 0, 20, "2026-05-01T10:00:00Z"),
            (4, "T001", "L2", "B", "alias", 0.8, 1, 1, 30, "2026-05-01T11:00:00Z"),
            (5, "T001", "L3", "C", "dense", 0.7, 1, 0, 40, "2026-05-01T12:00:00Z"),
            (6, "T001", "L3", "A", "lexical", 0.6, 2, 0, 50, "2026-05-01T12:00:00Z"),
            (7, "T001", "L3", "B", "rerank", 0.4, 3, 0, 60, "2026-05-01T12:00:00Z"),
        ]
        self.connection.executemany(
            "INSERT INTO match_event VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", events
        )

    def tearDown(self) -> None:
        self.connection.close()

    def test_optimized_query_preserves_baseline_and_adds_nearest_rank_p95(self) -> None:
        baseline_sql = (self.root / "starter" / "report_query.sql").read_text()
        optimized_sql = (self.root / "starter" / "report_optimized.sql").read_text()
        self.connection.row_factory = sqlite3.Row
        baseline = [dict(row) for row in self.connection.execute(baseline_sql)]
        optimized = [dict(row) for row in self.connection.execute(optimized_sql)]

        baseline_columns = list(baseline[0])
        normalized_baseline = [tuple(row[column] for column in baseline_columns) for row in baseline]
        normalized_optimized = [tuple(row[column] for column in baseline_columns) for row in optimized]
        self.assertEqual(normalized_baseline, normalized_optimized)
        self.assertEqual([60, 60], [row["p95_latency_ms"] for row in optimized])

    def test_report_index_migration_is_idempotent(self) -> None:
        # apply_index needs a file-backed database so file growth can be measured.
        import tempfile

        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "report.sqlite"
            connection = sqlite3.connect(database)
            connection.executescript(DDL)
            connection.close()
            apply_index(str(database))
            apply_index(str(database))
            connection = sqlite3.connect(database)
            names = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index'"
                )
            }
            connection.close()
            self.assertIn(INDEX_NAME, names)


if __name__ == "__main__":
    unittest.main()
