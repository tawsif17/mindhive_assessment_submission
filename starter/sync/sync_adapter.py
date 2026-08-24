#!/usr/bin/env python3
"""Crash-safe two-way sync between the local item store and the vendor ERP.

The adapter treats remote versions as the ordering authority. Timestamps are
kept for audit/display only because the ERP returns local time without an
offset and several records can share one second.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

try:  # Supports both `python run_sync.py` and package imports in tests.
    from .fake_erp import ErpConflict, ErpTimeout, FakeErp, Record
except ImportError:  # pragma: no cover - exercised by the command-line script
    from fake_erp import ErpConflict, ErpTimeout, FakeErp, Record


ERP_TIMEZONE = timezone(timedelta(hours=8))
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass
class LocalRecord:
    external_id: str
    payload: dict
    remote_version: int
    updated_at_utc: str
    dirty: bool = False


@dataclass(frozen=True)
class SyncConflict:
    """Both copies retained when automatic conflict resolution is unsafe."""

    external_id: str
    local_payload: dict
    remote_payload: dict
    local_base_version: int
    remote_version: int
    reason: str


@dataclass
class LocalStore:
    """Small in-memory model of the records and sync metadata in Postgres.

    `apply_pull_batch` represents one database transaction: record changes,
    conflicts, and the cursor commit together. In production these fields must
    be updated in one Postgres transaction as well.
    """

    records: dict[str, LocalRecord] = field(default_factory=dict)
    cursor: str | None = None
    applied_log: list[tuple[str, int]] = field(default_factory=list)
    conflicts: dict[str, SyncConflict] = field(default_factory=dict)

    def upsert(self, record: LocalRecord) -> None:
        self.records[record.external_id] = record
        self.applied_log.append((record.external_id, record.remote_version))

    def record_conflict(self, local: LocalRecord, remote: Record, reason: str) -> None:
        self.conflicts[local.external_id] = SyncConflict(
            external_id=local.external_id,
            local_payload=dict(local.payload),
            remote_payload=dict(remote.payload),
            local_base_version=local.remote_version,
            remote_version=remote.version,
            reason=reason,
        )

    def apply_pull_batch(
        self,
        records: list[LocalRecord],
        conflicts: list[tuple[LocalRecord, Record, str]],
        cursor: str,
    ) -> None:
        """Atomically apply one complete timestamp page and its cursor."""
        for record in records:
            self.upsert(record)
            self.conflicts.pop(record.external_id, None)
        for local, remote, reason in conflicts:
            self.record_conflict(local, remote, reason)
        self.cursor = cursor


def erp_local_to_utc(value: str) -> str:
    """Convert the ERP's offset-less +08:00 timestamp to a UTC string."""
    local_time = datetime.strptime(value, TIMESTAMP_FORMAT).replace(tzinfo=ERP_TIMEZONE)
    return local_time.astimezone(timezone.utc).strftime(TIMESTAMP_FORMAT)


def previous_second(value: str) -> str:
    """Move a cursor back one second so late records tied on time are replayed."""
    parsed = datetime.strptime(value, TIMESTAMP_FORMAT)
    return (parsed - timedelta(seconds=1)).strftime(TIMESTAMP_FORMAT)


def idempotency_key(external_id: str, payload: dict, base_version: int) -> str:
    """Return one stable key for one logical write, across retries/restarts."""
    canonical = json.dumps(
        {"id": external_id, "payload": payload, "base_version": base_version},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def complete_timestamp_page(
    erp: FakeErp, since: str | None, initial_limit: int
) -> list[Record]:
    """Fetch a page without cutting through a second-resolution timestamp.

    The vendor cursor has no tie-breaker. If a full page ends at timestamp T,
    the request limit is doubled until every row at T is present. Rows after T
    can wait for the next page. This avoids skipping tied rows without assuming
    a maximum number of changes per second.
    """
    limit = max(1, initial_limit)
    page = erp.list_changes(since=since, limit=limit)
    if len(page) < limit:
        return page

    boundary = page[-1].updated_at
    while True:
        limit *= 2
        expanded = erp.list_changes(since=since, limit=limit)
        if len(expanded) < limit:
            return expanded
        if expanded[-1].updated_at > boundary:
            return [record for record in expanded if record.updated_at <= boundary]


def pull(erp: FakeErp, store: LocalStore, page_size: int = 50) -> int:
    """Pull every complete remote timestamp page into the local store."""
    pulled = 0
    # The one-second overlap catches a record that committed late with the same
    # timestamp as the previous high-water mark. Version checks deduplicate it.
    query_cursor = previous_second(store.cursor) if store.cursor else None

    while True:
        page = complete_timestamp_page(erp, query_cursor, page_size)
        if not page:
            break

        upserts: list[LocalRecord] = []
        conflicts: list[tuple[LocalRecord, Record, str]] = []
        for remote in page:
            local = store.records.get(remote.external_id)
            if local and remote.version <= local.remote_version:
                continue  # replay or stale vendor row
            if local and local.dirty:
                conflicts.append((local, remote, "remote_changed_while_local_dirty"))
                continue
            upserts.append(
                LocalRecord(
                    external_id=remote.external_id,
                    payload=dict(remote.payload),
                    remote_version=remote.version,
                    updated_at_utc=erp_local_to_utc(remote.updated_at),
                    dirty=False,
                )
            )
            pulled += 1

        new_cursor = page[-1].updated_at
        store.apply_pull_batch(upserts, conflicts, new_cursor)
        # After the first overlapped page, strict `>` pagination is safe because
        # complete_timestamp_page never commits a partial timestamp boundary.
        query_cursor = new_cursor
    return pulled


def is_acknowledged_write(local: LocalRecord, remote: Record | None) -> bool:
    """Recognise a write that committed before its response or local commit."""
    return bool(
        remote
        and remote.version > local.remote_version
        and remote.payload == local.payload
    )


def accept_remote_ack(local: LocalRecord, remote: Record, store: LocalStore) -> None:
    """Mark a logical write complete without issuing another ERP mutation."""
    local.remote_version = remote.version
    local.updated_at_utc = erp_local_to_utc(remote.updated_at)
    local.dirty = False
    store.conflicts.pop(local.external_id, None)
    store.upsert(local)


def push(erp: FakeErp, store: LocalStore, max_attempts: int = 3) -> int:
    """Push dirty records without duplicate or blind conflict-overwrite writes."""
    pushed = 0
    for local in list(store.records.values()):
        if not local.dirty or local.external_id in store.conflicts:
            continue

        # A create has no base version, and the vendor interprets that as an
        # unconditional write. Check first so an unseen remote record with the
        # same ID is never overwritten.
        if local.remote_version <= 0:
            current = erp.get(local.external_id)
            if is_acknowledged_write(local, current):
                accept_remote_ack(local, current, store)
                pushed += 1
                continue
            if current:
                store.record_conflict(local, current, "remote_id_exists_before_create")
                continue

        key = idempotency_key(local.external_id, local.payload, local.remote_version)
        base_version = local.remote_version if local.remote_version > 0 else None
        for _attempt in range(max_attempts):
            try:
                remote = erp.write(
                    local.external_id,
                    local.payload,
                    base_version=base_version,
                    idempotency_key=key,
                )
            except ErpTimeout:
                current = erp.get(local.external_id)
                if is_acknowledged_write(local, current):
                    accept_remote_ack(local, current, store)
                    pushed += 1
                    break
                if current and current.version != local.remote_version:
                    store.record_conflict(local, current, "ambiguous_timeout_then_remote_change")
                    break
                continue
            except ErpConflict:
                current = erp.get(local.external_id)
                if is_acknowledged_write(local, current):
                    accept_remote_ack(local, current, store)
                    pushed += 1
                elif current:
                    store.record_conflict(local, current, "remote_changed_before_push")
                break
            else:
                accept_remote_ack(local, remote, store)
                pushed += 1
                break
    return pushed


def sync(erp: FakeErp, store: LocalStore) -> dict[str, int]:
    """Run pull before push so remote conflicts are visible before writing."""
    return {"pulled": pull(erp, store), "pushed": push(erp, store)}
