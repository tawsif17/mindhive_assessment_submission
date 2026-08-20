# Initial Data Findings

## Summary

The supplied data was checked with a read-only Python script.


The following main findings were made:

- A blank label was found in 29.8% of the training rows.
- Safe use was shown by the tested barcode and alias rules.
- Unsafe use was shown by the tested exact-name rule.
- Active twins and duplicate IDs were found in both catalogues.
- Seventy aliases were linked to disabled items.
- Full UOM coverage was found.
- No large visible shift was found between training and holdout data.

## Catalogue findings

### Row counts

A total of 1,148 Acme rows was found.

A total of 524 Nordic rows was found.

A total of 1,672 catalogue rows was found.

For Acme, 1,125 rows were active. A total of 23 rows were disabled.

For Nordic, 509 rows were active. A total of 15 rows were disabled.

The active count was based on the `disabled` field only. Misc rows may still be marked as active.

### Misc rows

A misc row is a row that does not describe a normal item.

Eleven misc rows were found in Acme.

Seven misc rows were found in Nordic.

Examples included delivery fees, misc charges, samples, and opening balances.

These rows should be removed before item matching is started.

### Active twins

A twin is an active item that shares its main visible name with another active item.

Fifteen twin groups were found in Acme.

Ten twin groups were found in Nordic.

Some twins were linked to different pack sizes.

An automatic match should not be made when the pack cannot be proved.

### Duplicate IDs

No duplicate item code was found.

Twenty-two duplicate barcode groups were found in Acme.

Eight of these groups contained two active rows.

Sixteen duplicate barcode groups were found in Nordic.

Eight of these groups contained two active rows.

Seventeen duplicate part-number groups were found in Acme.

Five of these groups contained two active rows.

Nine duplicate part-number groups were found in Nordic.

Two of these groups contained two active rows.

Twenty-six duplicate name groups were found in Acme.

Eighteen duplicate name groups were found in Nordic.

Some duplicate IDs were shared by a live item and an old item.

Some duplicate IDs were shared by two active twins.

A barcode or part number should only be trusted when one active item remains.

No wrong tenant prefix was found in an item code.

## Alias findings

An alias is a customer SKU that has been linked to an item code.

A total of 776 alias rows was found.

Of these rows, 479 were linked to Acme. A total of 297 were linked to Nordic.

The latest order date was used as the audit date. This date was 2026-08-28.

Twenty-six expired aliases were found. This was 3.4% of all aliases.

Twenty-six stored alias collision groups were found.

A collision means that one tenant, customer, and customer SKU were linked to more than one item.

No current collision was found after the date rules were applied.

Seventy aliases were linked to disabled items.

All 70 disabled-item aliases were still current on the audit date.

No alias was linked to a missing item.

No alias was linked to another tenant.

No alias was linked to a misc row.

The following source counts were found:

- A total of 348 aliases came from confirmed orders.
- A total of 252 aliases came from manual imports.
- A total of 176 aliases came from inferred matches.

The following confidence counts were found:

- A value of 1.0 was found in 427 rows.
- A value of 0.72 was found in 173 rows.
- A value of 0.55 was found in 176 rows.

An alias should not be trusted only because it exists.

The tenant, customer, date, target state, source, and collision state should be checked.

## UOM findings

UOM means unit of measure. Examples include box, packet, kilogram, and piece.

A total of 2,841 UOM rows was found.

UOM data was found for all 1,672 catalogue rows.

Full coverage was also found for active and disabled items in both tenants.

One conversion row was found for 503 items.

Two conversion rows were found for 1,169 items.

No item was missing a stock-UOM row.

No item had more than one stock-UOM row.

No invalid conversion value was found.

No UOM row was linked to a missing item.

No difference was found between a catalogue stock UOM and its stock-UOM reference row.

No difference was found between the stored UOM JSON and the UOM reference file.

The UOM data can be used for pack checks.

The UOM data should not be used to choose between items until a possible item has been found.

## Order-line findings

### Training rows

A total of 420 training rows was found.

A label was found in 295 rows. This was 70.2% of the data.

A blank label was found in 125 rows. This was 29.8% of the data.

A blank label means that no item should be returned without strong proof.

For Acme, 260 training rows were found. A blank label was found in 86 rows.

The Acme blank-label rate was 33.1%.

For Nordic, 160 training rows were found. A blank label was found in 39 rows.

The Nordic blank-label rate was 24.4%.

No training label was linked to a missing item.

No training label was linked to another tenant.

No training label was linked to a disabled item.

No training label was linked to a misc row.

A total of 101 training rows came from email PDFs.

A total of 110 training rows came from portal CSV files.

A total of 99 training rows came from voice notes.

A total of 110 training rows came from WhatsApp.

### Available signals

A buyer SKU was found in 64 training rows. This was 15.2% of the rows.

A barcode was found in 13 training rows. This was 3.1% of the rows.

A UOM value was found in 215 training rows. This was 51.2% of the rows.

A unit price was found in 184 training rows. This was 43.8% of the rows.

Notes were found in 36 training rows. This was 8.6% of the rows.

Most lines cannot be solved by an alias or barcode alone.

## Training and holdout comparison

A total of 300 holdout rows was found.

The tenant shares were close in both files.

Acme made up 61.9% of training rows and 63.3% of holdout rows.

Nordic made up 38.1% of training rows and 36.7% of holdout rows.

The channel shares were also close.

Email PDFs made up 24.0% of training rows and 24.7% of holdout rows.

Portal CSV files made up 26.2% of training rows and 21.3% of holdout rows.

Voice notes made up 23.6% of training rows and 27.3% of holdout rows.

WhatsApp made up 26.2% of training rows and 26.7% of holdout rows.

No rate changed by five percentage points or more.

Buyer SKUs were found in 15.2% of training rows and 14.3% of holdout rows.

Barcodes were found in 3.1% of training rows and 4.3% of holdout rows.

UOM values were found in 51.2% of training rows and 53.0% of holdout rows.

Prices were found in 43.8% of training rows and 43.0% of holdout rows.

Notes were found in 8.6% of training rows and 8.3% of holdout rows.

The mean text length was 29.2 characters in training data.

The mean text length was 28.9 characters in holdout data.

The median text length was 29 characters in both files.

The mean token count was 5.4 in training data and 5.3 in holdout data.

The same date range was found in both files. The range was 2026-04-01 to 2026-08-28.

No clear visible data shift was found.

Holdout labels were not accessed or created.

## Matcher findings

Three simple rules were tested on the training data.

Precision means the share of returned matches that were correct.

Coverage means the share of all rows that received a match.

### Unique active barcode rule

A match was made for 12 rows.

All 12 matches were correct.

Precision was measured at 100.0%.

Coverage was measured at 2.9%.

This result was strong. The sample was small.

Only a barcode linked to one active item should be accepted.

### Valid customer alias rule

A match was made for 23 rows.

All 23 matches were correct.

Precision was measured at 100.0%.

Coverage was measured at 5.5%.

This result was strong. The sample was small.

An expired, colliding, disabled, or wrong-customer alias should be blocked.

### Unique normalized name rule

A match was made for 134 rows.

Only 103 matches were correct.

Thirty-one false matches were made.

Precision was measured at 76.9%.

Coverage was measured at 31.9%.

The exact-name rule was not safe for automatic matching.

Name evidence should be joined with size, pack, UOM, and score-gap evidence.

### Labels marked for review

No blank label had one active barcode match.

Twenty-two blank labels had one active exact-name match without a known twin.

Nine blank labels had an exact-name match with a twin or pack risk.

These rows were marked for review only.

A label error was not assumed.

## Evaluation needs

Precision and coverage should be measured together.

The cost of a false automatic match should be included.

Results should be split by tenant and input type.

Zero cross-tenant matches should be required.

Zero automatic matches to disabled or misc rows should be required.

Barcode, alias, and text rules should be measured on their own.

Confidence values should be checked against real results.

The name rule should not be accepted because it has higher coverage.

## Report findings

A total of 8,666 reference rows was found.

Data from 40 tenants was found.

Data from four channels was found.

Data from 61 days was found.

The stored baseline time was 3,050 seconds. This was about 50 minutes and 50 seconds.

Thirty-five missing values were found in `avg_accept_score`.

No missing value was found in the other stored columns.

The required `p95_latency_ms` column was not present.

The query should be changed so that each large table is grouped once.

The old result should be kept exactly for all current columns.

The new p95 value should be tested on small known cases.

## Next steps

Tenant filters should be applied before item search.

Disabled and misc rows should be removed before matching.

Unique active barcode matches should be used as the first safe rule.

Valid customer aliases should be used as another safe rule.

Name-only matches should be sent for review until safer rules are proved.

Human review should be used when two active items remain.

Clear non-item lines should be rejected.

Top candidates should still be returned when an automatic match is refused.

Tenant indexes should be kept separate as the catalogue grows.

Alias changes should be checked before they are added to future matching data.

## Run command

The audit can be run from the repository root:

```text
python analysis/initial_data_audit.py
```

## Limits of the audit

Only the supplied public data was read.

No holdout label was used.

No final text matching model was tested.

No score limit was selected.

No production traffic was available.

The simple matching rules were used only to guide the next build step.
