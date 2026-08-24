#!/usr/bin/env python3
"""Runs one sync scenario and checks three invariants. Stdlib only.

    python3 run_sync.py

This is a symptom reporter, not a test suite. It tells you that something is
wrong, not what. Part of Task 5 is replacing it with tests that fail for one
reason each and name that reason.
"""

from __future__ import annotations

from fake_erp import FakeErp
from sync_adapter import LocalStore, pull, push


def scenario():
    erp = FakeErp(seed=11, timeout_rate=0.25)
    erp.seed_records(60)
    store = LocalStore()

    pulled = pull(erp, store)

    # someone edits three items in our UI
    for eid in ("EXT-0003", "EXT-0011", "EXT-0042"):
        rec = store.records.get(eid)
        if rec:
            rec.payload = dict(rec.payload, price=999.0)
            rec.dirty = True

    # meanwhile the ERP moves on: a user edits one of the same items there
    erp.tick(120)
    erp.write("EXT-0011", {"name": "item 11", "price": 55.5, "uom": "Box"}, base_version=1)

    pushed = push(erp, store)
    pull(erp, store)
    return erp, store, pulled, pushed


def main():
    erp, store, pulled, pushed = scenario()
    print(f"pulled={pulled} pushed={pushed} "
          f"remote={len(erp.records)} local={len(store.records)} "
          f"conflicts={len(store.conflicts)}")

    failures = []

    # INV1: after a full sync, every remote record exists locally at the remote version
    missing = [eid for eid in erp.records if eid not in store.records]
    # A deliberate conflict keeps both versions, so version drift is only a
    # failure when it is not represented in the conflict queue.
    stale = [eid for eid, r in erp.records.items()
             if eid in store.records
             and eid not in store.conflicts
             and store.records[eid].remote_version != r.version]
    if missing:
        failures.append(f"INV1 missing locally: {len(missing)} records e.g. {missing[:5]}")
    if stale:
        failures.append(f"INV1 version drift: {len(stale)} records e.g. {stale[:5]}")

    # INV2: one logical local edit produces at most one remote write
    counts = {}
    for eid, _version, payload in erp.write_log:
        if payload.get("price") == 999.0:
            counts[eid] = counts.get(eid, 0) + 1
    dupes = {k: v for k, v in counts.items() if v > 1}
    if dupes:
        failures.append(f"INV2 duplicate writes: {dupes}")

    # INV3: a remote edit made after our local edit must not be silently lost
    remote_11 = erp.records["EXT-0011"].payload
    if remote_11.get("uom") != "Box":
        failures.append(f"INV3 remote edit clobbered: EXT-0011 payload is {remote_11}")
    if "EXT-0011" not in store.conflicts:
        failures.append("INV3 concurrent edit was not placed in the conflict queue")

    if failures:
        print("\nFAILURES")
        for f in failures:
            print(" -", f)
    else:
        print("\nall invariants hold for this scenario "
              "(that is not the same as the adapter being correct)")


if __name__ == "__main__":
    main()
