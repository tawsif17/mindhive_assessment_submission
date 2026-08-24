# Task 5: Two-Way ERP Sync

## Result

The supplied scenario now reports:

```text
pulled=60 pushed=2 remote=60 local=60 conflicts=1
all invariants hold for this scenario
```

The concurrent edit is not discarded. Both payloads are retained in `LocalStore.conflicts` for resolution.

## Defects and isolated tests

| Defect | Ticket | Exact mechanism | Isolating test | Restored invariant |
|---|---|---|---|---|
| Partial timestamp page skips records | MAIA-812 | The old code moved the cursor to the last timestamp in a 50-row page. The next request used strict `updated_at > cursor`, so further records sharing that second disappeared. | `test_pull_does_not_skip_records_tied_at_page_boundary` | A cursor advances only past a timestamp whose complete tie group was fetched. |
| Late arrival at the cursor second is invisible | MAIA-812 | A record committed after the pull with the same second as the stored cursor does not satisfy strict `>`. | `test_pull_overlap_catches_a_late_record_with_the_cursor_timestamp` | Each new run overlaps one second and deduplicates by version. |
| Cursor commits before local rows | Latent | The old pull stored the cursor before upserting the page. A crash could permanently move the cursor past records that were never committed locally. | `test_pull_does_not_advance_cursor_when_batch_commit_fails` | Record changes and cursor form one database transaction; the cursor never outruns durable rows. |
| Retry key changes on every attempt | MAIA-830 | `attempt` and `time.time()` were included in the idempotency key, so the ERP saw each retry as a new operation. | `test_idempotency_key_is_stable_for_one_logical_edit` | One logical edit has one key derived from ID, canonical payload, and base version. |
| 504 after commit is retried blindly | MAIA-830 | A timeout says nothing about commit status. The old code immediately wrote again, producing a second version and price-history entry. | `test_timeout_after_commit_does_not_create_a_second_write` | After an ambiguous response, read state before deciding to mutate again. |
| Conflict handler overwrites the ERP | MAIA-844 | On 409, the old code fetched the new remote version and immediately wrote the stale local payload against it. This turned compare-and-swap into last-writer-wins. | `test_push_conflict_preserves_the_remote_edit` | A real conflict performs no write and preserves both payloads. |
| Pull conflict uses incomparable timestamps | MAIA-844 | Local timestamps were labelled UTC while remote timestamps were +08:00 without an offset. The comparison could silently choose either copy. | `test_pull_conflict_keeps_dirty_local_and_remote_copies` | Remote version detects concurrency; timestamps never resolve it. |
| Replayed rows can clear local dirty state | Latent | A replay of the same remote version could replace a dirty local record when the timestamp comparison chose the remote copy. | `test_replayed_remote_version_does_not_clear_a_local_edit` | A remote version at or below the local base version is a no-op. |
| Crash after remote commit can write again after restart | Latent | If the ERP committed but local clean-state did not, restart reached the conflict path and overwrote again. The 60-second key window is not enough for delayed restart. | `test_restart_after_remote_commit_recognises_the_existing_write` | Matching payload at a newer remote version acknowledges the earlier logical write without another mutation. |
| New local ID can overwrite an unseen remote ID | Latent | `base_version=None` is unconditional in the vendor API. A local create colliding with an existing remote ID replaced it without a 409. | `test_new_local_record_does_not_overwrite_an_unseen_remote_id` | Create checks remote existence first; collision becomes a conflict. |
| ERP local time is stored as UTC | Latent | The old adapter copied a +08:00 value into `updated_at_utc` without conversion, shifting audit time by eight hours. | `test_erp_local_timestamp_is_stored_as_utc` | Stored audit timestamps are converted from known ERP local time to UTC. |

The latent defects surface under less common timing: process death between two commits, a sync delayed beyond the idempotency window, a local create before its remote counterpart is pulled, a late same-second transaction, or a dirty record replayed during overlap.

## How the fixed pull works

The ERP cursor only has whole seconds, so a normal `page[-1].updated_at` cursor is unsafe. `complete_timestamp_page` handles this explicitly:

1. Request the configured page size.
2. If the page is full, remember its final timestamp.
3. Double the request limit until every record at that timestamp is present.
4. Apply that complete timestamp group and its cursor together.
5. On the next scheduled run, overlap the previous second and ignore versions already applied.

The growing request is a workaround for the vendor's missing tie-breaker. It is correct for the supplied API, but a very large same-second burst can require a large response. This is one reason the cursor contract is the first vendor request below.

## How the fixed push works

Each dirty record is its own recoverable operation:

1. Build one stable idempotency key from external ID, payload, and base version.
2. Write with compare-and-swap using the known remote version.
3. On 504, read the record. If the intended payload is present at a newer version, mark the logical write complete.
4. On 409 with different content, do not write. Save local and remote copies in the conflict queue.
5. Commit the returned remote version and clean state locally.

If the process dies after step 2 but before step 5, the next run recognises the already-committed payload. This remains correct after the vendor's 60-second idempotency window expires.

## Vendor contract requested, in priority order

1. **Opaque composite change cursor.** The page token must order by at least `(updated_at, external_id)` and represent a stable snapshot. Until then, use complete timestamp groups plus overlap.
2. **Durable operation status and idempotency.** Keep keys for at least 24 hours and provide `GET /operations/{key}`. Until then, use a stable key and read-after-timeout verification.
3. **Mandatory version preconditions, including create.** Reject missing or stale base versions. Until then, check existence before create and use compare-and-swap for updates.
4. **Offset-aware UTC timestamps.** Return RFC 3339 values such as `2026-08-01T00:00:00+08:00`. Until then, convert from the documented +08:00 zone and never use time for conflict ordering.
5. **Per-record batch results or transactions.** Return a durable status for every record. Until then, commit local state per record and safely replay unfinished records.

## Operation at 500 tenants

A run every five minutes means an average of 1.67 tenant runs must start each second. The first failure is likely scheduling and ERP rate-limit pressure, followed by a growing dirty/conflict backlog. A same-second burst can also force the adaptive pull limit upward.

I would use a durable queue, one lease per tenant, bounded global and per-vendor concurrency, exponential backoff with jitter, and a dead-letter queue. A fencing token prevents two workers from syncing the same tenant concurrently.

The minimum alerts are:

- cursor age and oldest dirty-record age;
- run duration versus the five-minute interval;
- records pulled/pushed and page-limit expansion;
- 409, 504, retry, and conflict rates;
- tenants with overlapping or failed leases;
- local/remote version drift from a sampled reconciliation job;
- duplicate logical writes detected by operation key.

These signals detect loss, duplication, conflict growth, and scheduler saturation before a customer report.

## Run

```bash
python -m unittest tests.test_sync -v
cd starter/sync
python run_sync.py
```
