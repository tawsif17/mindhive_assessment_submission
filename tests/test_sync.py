from __future__ import annotations

import unittest

from starter.sync.fake_erp import FakeErp, Record
from starter.sync.sync_adapter import (
    LocalRecord,
    LocalStore,
    erp_local_to_utc,
    idempotency_key,
    pull,
    push,
)


class SyncAdapterTests(unittest.TestCase):
    def test_pull_does_not_advance_cursor_when_batch_commit_fails(self) -> None:
        class FailingStore(LocalStore):
            def upsert(self, record: LocalRecord) -> None:
                super().upsert(record)
                raise RuntimeError("simulated database failure")

        erp = FakeErp(timeout_rate=0.0)
        erp.records["EXT-1"] = Record(
            "EXT-1", {"name": "one"}, 1, "2026-08-01 00:00:10"
        )
        store = FailingStore()

        with self.assertRaisesRegex(RuntimeError, "database failure"):
            pull(erp, store)

        self.assertIsNone(store.cursor)

    def test_pull_does_not_skip_records_tied_at_page_boundary(self) -> None:
        erp = FakeErp(timeout_rate=0.0)
        for index in range(25):
            external_id = f"EXT-{index:04d}"
            erp.records[external_id] = Record(
                external_id, {"name": external_id}, 1, "2026-08-01 00:00:00"
            )
        store = LocalStore()

        pulled = pull(erp, store, page_size=10)

        self.assertEqual(25, pulled)
        self.assertEqual(set(erp.records), set(store.records))

    def test_pull_overlap_catches_a_late_record_with_the_cursor_timestamp(self) -> None:
        erp = FakeErp(timeout_rate=0.0)
        erp.records["EXT-1"] = Record(
            "EXT-1", {"name": "first"}, 1, "2026-08-01 00:00:10"
        )
        store = LocalStore()
        pull(erp, store, page_size=10)
        erp.records["EXT-2"] = Record(
            "EXT-2", {"name": "late tie"}, 1, "2026-08-01 00:00:10"
        )

        pulled = pull(erp, store, page_size=10)

        self.assertEqual(1, pulled)
        self.assertIn("EXT-2", store.records)

    def test_timeout_after_commit_does_not_create_a_second_write(self) -> None:
        erp = FakeErp(timeout_rate=1.0)
        erp.records["EXT-1"] = Record(
            "EXT-1", {"price": 10.0}, 1, "2026-08-01 00:00:00"
        )
        store = LocalStore(
            records={
                "EXT-1": LocalRecord(
                    "EXT-1", {"price": 20.0}, 1, "2026-07-31 16:00:00", dirty=True
                )
            }
        )

        pushed = push(erp, store)

        self.assertEqual(1, pushed)
        self.assertEqual(1, len(erp.write_log))
        self.assertEqual(2, store.records["EXT-1"].remote_version)
        self.assertFalse(store.records["EXT-1"].dirty)

    def test_push_conflict_preserves_the_remote_edit(self) -> None:
        erp = FakeErp(timeout_rate=0.0)
        erp.records["EXT-1"] = Record(
            "EXT-1", {"price": 10.0, "uom": "Nos"}, 1, "2026-08-01 00:00:00"
        )
        store = LocalStore(
            records={
                "EXT-1": LocalRecord(
                    "EXT-1",
                    {"price": 999.0, "uom": "Nos"},
                    1,
                    "2026-07-31 16:00:00",
                    dirty=True,
                )
            }
        )
        erp.tick(1)
        erp.write("EXT-1", {"price": 10.0, "uom": "Box"}, base_version=1)
        writes_before_push = len(erp.write_log)

        pushed = push(erp, store)

        self.assertEqual(0, pushed)
        self.assertEqual(writes_before_push, len(erp.write_log))
        self.assertEqual("Box", erp.records["EXT-1"].payload["uom"])
        self.assertEqual(999.0, store.conflicts["EXT-1"].local_payload["price"])
        self.assertEqual("Box", store.conflicts["EXT-1"].remote_payload["uom"])

    def test_pull_conflict_keeps_dirty_local_and_remote_copies(self) -> None:
        erp = FakeErp(timeout_rate=0.0)
        erp.records["EXT-1"] = Record(
            "EXT-1", {"price": 10.0, "uom": "Box"}, 2, "2026-08-01 00:00:10"
        )
        local = LocalRecord(
            "EXT-1",
            {"price": 999.0, "uom": "Nos"},
            1,
            "2026-07-31 16:00:00",
            dirty=True,
        )
        store = LocalStore(records={"EXT-1": local})

        pull(erp, store)

        self.assertTrue(store.records["EXT-1"].dirty)
        self.assertEqual(999.0, store.records["EXT-1"].payload["price"])
        self.assertEqual("Box", store.conflicts["EXT-1"].remote_payload["uom"])

    def test_replayed_remote_version_does_not_clear_a_local_edit(self) -> None:
        erp = FakeErp(timeout_rate=0.0)
        erp.records["EXT-1"] = Record(
            "EXT-1", {"price": 10.0}, 1, "2026-08-01 00:00:10"
        )
        local = LocalRecord(
            "EXT-1", {"price": 20.0}, 1, "2026-07-31 16:00:10", dirty=True
        )
        store = LocalStore(
            records={"EXT-1": local}, cursor="2026-08-01 00:00:10"
        )

        pull(erp, store)

        self.assertTrue(local.dirty)
        self.assertEqual(20.0, local.payload["price"])

    def test_restart_after_remote_commit_recognises_the_existing_write(self) -> None:
        erp = FakeErp(timeout_rate=0.0)
        desired = {"price": 20.0}
        erp.records["EXT-1"] = Record(
            "EXT-1", desired, 2, "2026-08-01 00:00:10"
        )
        local = LocalRecord(
            "EXT-1", desired, 1, "2026-07-31 16:00:00", dirty=True
        )
        store = LocalStore(records={"EXT-1": local})

        pushed = push(erp, store)

        self.assertEqual(1, pushed)
        self.assertEqual([], erp.write_log)
        self.assertFalse(local.dirty)
        self.assertEqual(2, local.remote_version)

    def test_new_local_record_does_not_overwrite_an_unseen_remote_id(self) -> None:
        erp = FakeErp(timeout_rate=0.0)
        erp.records["EXT-1"] = Record(
            "EXT-1", {"name": "remote"}, 1, "2026-08-01 00:00:10"
        )
        local = LocalRecord(
            "EXT-1", {"name": "local"}, 0, "2026-07-31 16:00:00", dirty=True
        )
        store = LocalStore(records={"EXT-1": local})

        pushed = push(erp, store)

        self.assertEqual(0, pushed)
        self.assertEqual({"name": "remote"}, erp.records["EXT-1"].payload)
        self.assertEqual([], erp.write_log)
        self.assertEqual(
            "remote_id_exists_before_create", store.conflicts["EXT-1"].reason
        )

    def test_idempotency_key_is_stable_for_one_logical_edit(self) -> None:
        first = idempotency_key("EXT-1", {"price": 20.0}, 3)
        second = idempotency_key("EXT-1", {"price": 20.0}, 3)
        next_version = idempotency_key("EXT-1", {"price": 20.0}, 4)
        self.assertEqual(first, second)
        self.assertNotEqual(first, next_version)

    def test_erp_local_timestamp_is_stored_as_utc(self) -> None:
        self.assertEqual(
            "2026-07-31 16:00:00",
            erp_local_to_utc("2026-08-01 00:00:00"),
        )


if __name__ == "__main__":
    unittest.main()
