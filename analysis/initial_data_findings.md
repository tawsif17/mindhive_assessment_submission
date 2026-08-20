# Initial Data Findings

> The supplied data was checked with a read-only Python script. No source data was changed. No holdout label was used.

## At a glance

| Area | Main result | Engineering meaning |
|---|---:|---|
| Blank training labels | 125 of 420 (29.8%) | Strong refusal rules will be needed. |
| Barcode rule | 100.0% precision, 2.9% coverage | A safe first lane was shown. The sample was small. |
| Valid alias rule | 100.0% precision, 5.5% coverage | A safe second lane was shown. The sample was small. |
| Exact-name rule | 76.9% precision, 31.9% coverage | Name-only matching was not safe. |
| Active twin groups | 25 | Pack and UOM checks will be needed. |
| Aliases to disabled items | 70 | Disabled targets must be blocked. |
| UOM coverage | 100.0% | Pack checks can be supported by the supplied data. |
| Train/holdout shift | No large visible shift | The same first matcher design can be tested on both sets. |

## Catalogue findings

### Counts and item risks

| Measure | Acme | Nordic | Total |
|---|---:|---:|---:|
| Catalogue rows | 1,148 | 524 | 1,672 |
| Active rows | 1,125 | 509 | 1,634 |
| Disabled rows | 23 | 15 | 38 |
| Misc rows | 11 | 7 | 18 |
| Active twin groups | 15 | 10 | 25 |
| Duplicate name groups | 26 | 18 | 44 |
| Wrong item-code prefixes | 0 | 0 | 0 |

The active count was based on the `disabled` field. A misc row may still be marked as active.

A misc row does not describe a normal item. Examples included:

- Delivery fees
- Misc charges
- Samples that should not be sold
- Opening balances

These rows should be removed before matching is started.

An active twin shares its main visible name with another active item. Some twins were linked to different pack sizes. An automatic match should be refused when the pack cannot be proved.

### Duplicate identifiers

| Identifier check | Acme | Nordic | Total |
|---|---:|---:|---:|
| Duplicate item-code groups | 0 | 0 | 0 |
| Duplicate barcode groups | 22 | 16 | 38 |
| Barcode groups with two active rows | 8 | 8 | 16 |
| Duplicate part-number groups | 17 | 9 | 26 |
| Part-number groups with two active rows | 5 | 2 | 7 |

Some duplicate IDs were shared by a live item and an old item. Others were shared by two active twins.

> A barcode or part number should only be trusted when one active item remains.

## Alias findings

An alias is a customer SKU that has been linked to an item code.

### Alias quality

| Check | Result |
|---|---:|
| Total aliases | 776 |
| Acme aliases | 479 |
| Nordic aliases | 297 |
| Expired aliases | 26 (3.4%) |
| Stored collision groups | 26 |
| Current collision groups after date checks | 0 |
| Aliases to disabled items | 70 |
| Current aliases to disabled items | 70 |
| Aliases to missing items | 0 |
| Aliases to another tenant | 0 |
| Aliases to misc rows | 0 |

The latest order date was used as the audit date. This date was `2026-08-28`.

A collision is found when one tenant, customer, and customer SKU are linked to more than one item.

### Source and confidence

| Alias source | Rows |
|---|---:|
| Confirmed order | 348 |
| Manual import | 252 |
| Inferred match | 176 |

| Confidence value | Rows |
|---|---:|
| 1.00 | 427 |
| 0.72 | 173 |
| 0.55 | 176 |

An alias should not be trusted only because it exists. The following checks should be applied:

- The tenant should match.
- The customer should match.
- The date range should be valid.
- One active target should remain.
- The source and confidence should be checked.
- Any collision should be resolved.

## UOM findings

UOM means unit of measure. Examples include box, packet, kilogram, and piece.

| Check | Result |
|---|---:|
| UOM rows | 2,841 |
| Catalogue coverage | 1,672 of 1,672 (100.0%) |
| Items with one conversion row | 503 |
| Items with two conversion rows | 1,169 |
| Missing stock-UOM rows | 0 |
| Items with more than one stock-UOM row | 0 |
| Invalid conversion values | 0 |
| UOM rows linked to missing items | 0 |
| Catalogue and reference mismatches | 0 |
| Stored JSON and reference mismatches | 0 |

Full coverage was found for active and disabled items in both tenants.

The UOM data can support pack checks. It should be used after possible items have been found.

## Order-line findings

### Training labels by tenant

| Tenant | Training rows | Blank labels | Blank-label rate |
|---|---:|---:|---:|
| Acme | 260 | 86 | 33.1% |
| Nordic | 160 | 39 | 24.4% |
| **Total** | **420** | **125** | **29.8%** |

A valid item label was found in 295 rows. No valid item was given in the other 125 rows.

No training label was linked to:

- A missing item
- Another tenant
- A disabled item
- A misc row

### Training channels

| Channel | Rows | Share |
|---|---:|---:|
| Email PDF | 101 | 24.0% |
| Portal CSV | 110 | 26.2% |
| Voice note | 99 | 23.6% |
| WhatsApp | 110 | 26.2% |

## Training and holdout comparison

### Tenant mix

| Tenant | Training | Holdout |
|---|---:|---:|
| Acme | 260 (61.9%) | 190 (63.3%) |
| Nordic | 160 (38.1%) | 110 (36.7%) |

### Channel mix

| Channel | Training | Holdout |
|---|---:|---:|
| Email PDF | 101 (24.0%) | 74 (24.7%) |
| Portal CSV | 110 (26.2%) | 64 (21.3%) |
| Voice note | 99 (23.6%) | 82 (27.3%) |
| WhatsApp | 110 (26.2%) | 80 (26.7%) |

### Available signals

| Signal | Training | Holdout |
|---|---:|---:|
| Buyer SKU | 64 (15.2%) | 43 (14.3%) |
| Barcode | 13 (3.1%) | 13 (4.3%) |
| UOM | 215 (51.2%) | 159 (53.0%) |
| Unit price | 184 (43.8%) | 129 (43.0%) |
| Notes | 36 (8.6%) | 25 (8.3%) |
| Quantity | 411 (97.9%) | 292 (97.3%) |

Most lines cannot be solved by an alias or barcode alone.

### Text and date shape

| Measure | Training | Holdout |
|---|---:|---:|
| Mean text length | 29.2 characters | 28.9 characters |
| Median text length | 29 characters | 29 characters |
| Mean token count | 5.4 | 5.3 |
| Median token count | 5.0 | 5.0 |
| Date range | 2026-04-01 to 2026-08-28 | 2026-04-01 to 2026-08-28 |

No rate changed by five percentage points or more. No clear visible data shift was found.

> Holdout labels were not accessed or created.

## Matcher findings

Three simple rules were tested on training data.

- **Precision** is the share of returned matches that were correct.
- **Coverage** is the share of all rows that received a match.

| Rule | Matches | Correct | False | Precision | Coverage | Use |
|---|---:|---:|---:|---:|---:|---|
| Unique active barcode | 12 | 12 | 0 | 100.0% | 2.9% | Safe first lane |
| Valid customer alias | 23 | 23 | 0 | 100.0% | 5.5% | Safe second lane |
| Unique normalized name | 134 | 103 | 31 | 76.9% | 31.9% | Review only |

The barcode and alias samples were small. More tests will be needed before release.

The exact-name rule was not safe for automatic matching. Name evidence should be joined with size, pack, UOM, and score-gap evidence.

### Labels marked for review

| Review group | Rows |
|---|---:|
| Blank label with one active barcode match | 0 |
| Blank label with one active exact-name match | 22 |
| Blank label with a twin or pack risk | 9 |

These rows were marked for review only. A label error was not assumed.

## Evaluation needs

The following release checks should be added:

- Precision and coverage should be measured together.
- The cost of a false automatic match should be included.
- Results should be split by tenant and input type.
- Zero cross-tenant matches should be required.
- Zero automatic matches to disabled or misc rows should be required.
- Barcode, alias, and text rules should be measured on their own.
- Confidence values should be checked against real results.

Higher coverage should not be accepted when precision falls below the safe level.

## Report findings

| Check | Result |
|---|---:|
| Reference rows | 8,666 |
| Tenants | 40 |
| Channels | 4 |
| Days | 61 |
| Stored baseline time | 3,050 seconds |
| Missing `avg_accept_score` values | 35 |
| Missing values in other stored columns | 0 |
| `p95_latency_ms` present | No |

The stored baseline time was about 50 minutes and 50 seconds.

The query should be changed so that each large table is grouped once. The current result should be kept for all existing columns. The new p95 value should be tested on small known cases.

## Next steps

1. Tenant filters should be applied before item search.
2. Disabled and misc rows should be removed before matching.
3. Unique active barcode matches should be used as the first safe rule.
4. Valid customer aliases should be used as the second safe rule.
5. Name-only matches should be sent for review.
6. Human review should be used when two active items remain.
7. Clear non-item lines should be rejected.
8. Top choices should still be returned when an automatic match is refused.
9. Tenant indexes should be kept separate as the catalogue grows.
10. Alias changes should be checked before they are added to future matching data.

## Run command

The audit can be run from the repository root:

```text
python analysis/initial_data_audit.py
```

## Limits of the audit

- Only the supplied public data was read.
- No holdout label was used.
- No final text matching model was tested.
- No score limit was selected.
- No production traffic was available.
- The simple rules were used only to guide the next build step.
