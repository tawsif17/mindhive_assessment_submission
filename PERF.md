# Task 4: Tenant Match Health Report

## Result

The replacement report returns all 8,666 expected rows. Every value in the 13 original columns is exactly equal to the supplied reference. It also adds nearest-rank `p95_latency_ms`.

Five full-window runs took 6.194 to 6.437 seconds, with a median of 6.326 seconds. The target was 10 seconds. The measured result is inside the budget by 3.674 seconds.

## Baseline estimate

I did not run the original query over the full 61-day window. I narrowed the original SQL and measured these slices:

| Slice | Output rows | Time |
|---|---:|---:|
| One day, one heavy tenant | 4 | 19.46 s |
| One day, one light tenant | 2 | 17.24 s |
| One day, two tenants | 8 | 23.32 s |
| Two days, one tenant | 8 | 24.42 s |
| One day, four tenants | 16 | 32.84 s |
| Four days, one tenant | 16 | 34.41 s |
| One day, all tenants | 144 | 144.09 s |
| Two days, all tenants | 293 | 270.40 s |

The small tenant slices are poor extrapolation points. Even the light tenant pays almost the same fixed ledger-scan cost as the heavy tenant. The all-tenant slices are more representative: adding the second day added 126.31 seconds. Extrapolating the first day plus 60 further days gives:

```text
144.09 + (60 × 126.31) = 7,722.7 seconds = 128.7 minutes
```

An output-group check gives a similar estimate. The second slice added 149 groups in 126.31 seconds, or 0.848 seconds per group. Applying that slope to 8,666 groups estimates about 7,368 seconds, within 5% of the day-based estimate. I therefore use **about 2.1 hours** as the baseline estimate on this machine.

The reference file records a 3,050-second run from its producing environment. I did not substitute that number for my estimate; the difference is consistent with machine and cache differences.

## Diagnosis

The original query produces one grouped output row and then runs correlated subqueries against the ledger for that row. The same large tables are scanned repeatedly. The previous-day item metric is worse because it contains an `EXISTS` lookup back into `match_event`.

I removed one metric at a time from the same one-tenant, one-day probe:

| Probe | Time | Change from 20.46 s |
|---|---:|---:|
| All metrics | 20.46 s | — |
| Without `repeat_items_prev_day` | 3.46 s | **17.00 s faster** |
| Without `lines_accepted` | 19.98 s | 0.48 s faster |
| Without `max_latency_ms` | 20.01 s | 0.45 s faster |
| Without `avg_latency_ms` | 20.08 s | 0.38 s faster |
| Without `accepted_disabled` | 20.29 s | 0.17 s faster |
| Other single-column removals | 20.59–21.10 s | within run noise |

The previous-day metric accounts for about 83% of this controlled probe. No other single metric dominates. That means removing one more column is not the general fix: the repeated correlated-query shape must be replaced.

## Fix

`starter/report_optimized.sql` uses a small pipeline of common table expressions:

1. Select report-window order lines once.
2. Attach match events once.
3. Aggregate tenant/channel/day and tenant/day metrics separately.
4. Reduce match events to distinct tenant/day/item rows before comparing consecutive days.
5. Join the small aggregate tables to produce the final report.

`starter/apply_report_indexes.py` creates one expression index on `(tenant_id, day, item_code)`. This directly supports the dominant previous-day item operation. Building it took 1.40 seconds and increased the database by 40,603,648 bytes (40.6 MB).

The p95 uses `CUME_DIST()` per tenant/day. The first latency whose cumulative fraction reaches 95% is the nearest-rank p95. A fixture test checks a six-value set where the expected p95 is the sixth value.

## Work deliberately left alone

- I did not add an `order_line` date index. That table has 120,000 rows and its scan was not the measured bottleneck.
- I kept `COUNT(DISTINCT ...)` where the original contract used it, even where current keys make it look redundant.
- I did not materialize dashboard results. The query is already inside budget, and materialization would make a dashboard described as live become stale.
- I did not redesign timestamp storage. Replacing text timestamps with a generated date column would require a hotter and riskier migration than this deadline justifies.

## Trade-offs

The new index adds one B-tree update for every match event. At roughly 40 events per order line, this increases write work on the busiest ledger table. It also adds 40.6 MB to a 120.5 MB test database. Before production rollout I would compare peak insert throughput and WAL growth with and without the index. I accept that cost here because one index removes the measured dominant report cost without changing freshness or query results.

## Ceiling at 50× volume

This fix does not hold at 50× volume. A simple linear projection puts a 6.326-second query above five minutes, and the p95 sort and distinct tenant/day/item set will consume much more temporary storage.

The next design is incremental daily aggregates. I would store tenant/channel/day counters, a tenant/day latency histogram for exact nearest-rank percentiles, and distinct tenant/day/item membership for previous-day intersections. Events would update these asynchronously with a visible freshness timestamp and reconciliation job. I did not build that now because it adds operational state, recovery logic, and a freshness contract to solve a problem that one query and one measured index already solve at current volume.

## Reproduce

```bash
python starter/make_perf_db.py --out data/perf.sqlite
python starter/apply_report_indexes.py --db data/perf.sqlite
cd starter
python bench_report.py check --db ../data/perf.sqlite --sql report_optimized.sql --repeat 5 --budget-s 10
```

The slice and ablation measurements are reproducible with:

```bash
python analysis/performance/measure_task4.py
```
