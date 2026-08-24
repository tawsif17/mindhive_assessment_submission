# Manual Review Pack — 20 Lines

> Status: complete. Each conclusion was checked against visible source evidence. Supplied labels were not changed in primary metrics.

Every case is an answerable out-of-fold line whose top-ranked candidate differs from the supplied item. The matcher abstained on all 20.

| Root-cause group | Lines | Count |
|---|---|---:|
| Variant parsing and tokenisation | `ACM-T-0002`, `ACM-T-0030`, `ACM-T-0043`, `ACM-T-0057`, `ACM-T-0084`, `ACM-T-0115`, `ACM-T-0209`, `ACM-T-0251` | 8 |
| Stale alias without a successor link | `ACM-T-0010`, `ACM-T-0011`, `ACM-T-0037`, `ACM-T-0051`, `ACM-T-0173`, `ACM-T-0200`, `ACM-T-0241`, `NRD-T-0065` | 8 |
| Ranking and retrieval tie | `ACM-T-0031`, `ACM-T-0185`, `ACM-T-0221`, `NRD-T-0030` | 4 |

## 1. `ACM-T-0002`

- Tenant: `acme`
- Customer: `CUST-003`
- Raw text: `Vermmont  PVC  Pipe  20mmC  lass  E`
- Visible fields: buyer SKU ``, barcode ``, UOM `unit`, quantity `24`, price ``
- Supplied label: `ACM-PVCP1070`
- Review outcome group: `Variant parsing and tokenisation`
- Current evaluated decision: `review` / `attribute_conflict`
- Top candidate: `ACM-PVCP0082` at 0.002

| Candidate | Name | Stock UOM | Confidence | RapidFuzz | Word TF-IDF | Char TF-IDF | Safety blocks |
|---|---|---|---:|---:|---:|---:|---|
| `ACM-PVCP0082` | Vermont PVC Pipe 20mm Class C | Length | 0.002 | 0.855 | 0.663 | 0.781 | attribute_conflict |
| `ACM-PVCP0615` | Vermont PVC Pipe 20mm Class D | Length | 0.002 | 0.855 | 0.663 | 0.782 | attribute_conflict |
| `ACM-PVCP1070` | Vermont PVC Pipe 20mm Class E | Length | 0.002 | 0.856 | 0.663 | 0.816 | attribute_conflict |

- Label assessment: `correct_label`
- Confirmed root cause: The split text 'C lass E' prevents reliable grade extraction. The Class C, D, and E variants receive the same score and item-code order puts Class C first.
- Confirmed cost class: `review_40_seconds_top_candidate_wrong`
- Accepted fix or no-code action: Repair split grade tokens before retrieval and score an extracted class as a required variant attribute.

## 2. `ACM-T-0030`

- Tenant: `acme`
- Customer: `CUST-002`
- Raw text: `Hitex PVCP ipe1 5mm Class E`
- Visible fields: buyer SKU ``, barcode ``, UOM ``, quantity `3`, price ``
- Supplied label: `ACM-PVCP0941`
- Review outcome group: `Variant parsing and tokenisation`
- Current evaluated decision: `review` / `attribute_conflict`
- Top candidate: `ACM-PVCP0023` at 0.003

| Candidate | Name | Stock UOM | Confidence | RapidFuzz | Word TF-IDF | Char TF-IDF | Safety blocks |
|---|---|---|---:|---:|---:|---:|---|
| `ACM-PVCP0023` | Hitex PVC Pipe 25mm Class E | Length | 0.003 | 0.855 | 0.387 | 0.711 | attribute_conflict |
| `ACM-PVCP0099` | Hitex PVC Pipe 32mm Class C | Length | 0.003 | 0.855 | 0.374 | 0.657 | attribute_conflict |
| `ACM-PVCP0119` | Hitex PVC Pipe 20mm Class C | Length | 0.003 | 0.855 | 0.378 | 0.667 | attribute_conflict |

- Label assessment: `correct_label`
- Confirmed root cause: The text joins 'Pipe' to the size and splits 15mm as '1 5mm'. The size parser loses 15mm, leaving several Hitex Class E pipes tied.
- Confirmed cost class: `review_40_seconds_top_candidate_wrong`
- Accepted fix or no-code action: Add bounded token repair for split numeric dimensions after a recognised product family.

## 3. `ACM-T-0043`

- Tenant: `acme`
- Customer: `CUST-004`
- Raw text: `Reemax PVC Pipe 25mm Cass E`
- Visible fields: buyer SKU ``, barcode ``, UOM `unit`, quantity `2`, price `132.41`
- Supplied label: `ACM-PVCP1075`
- Review outcome group: `Variant parsing and tokenisation`
- Current evaluated decision: `review` / `attribute_conflict`
- Top candidate: `ACM-PVCP0949` at 0.052

| Candidate | Name | Stock UOM | Confidence | RapidFuzz | Word TF-IDF | Char TF-IDF | Safety blocks |
|---|---|---|---:|---:|---:|---:|---|
| `ACM-PVCP0949` | Remax PVC Pipe 25mm Class C | Length | 0.052 | 0.855 | 0.747 | 0.725 | attribute_conflict |
| `ACM-PVCP0200` | Remax PVC Pipe 25mm Class D | Length | 0.004 | 0.855 | 0.747 | 0.726 | attribute_conflict |
| `ACM-PVCP0023` | Hitex PVC Pipe 25mm Class E | Length | 0.004 | 0.855 | 0.748 | 0.607 | attribute_conflict |

- Label assessment: `correct_label`
- Confirmed root cause: The misspelling 'Cass E' is not normalised to Class E. Price similarity then favours the wrong Class C variant.
- Confirmed cost class: `review_40_seconds_top_candidate_wrong`
- Accepted fix or no-code action: Normalise common grade misspellings and make an extracted grade conflict outweigh price similarity.

## 4. `ACM-T-0057`

- Tenant: `acme`
- Customer: `CUST-002`
- Raw text: `1) Hietx Cable Tie 300m Natural`
- Visible fields: buyer SKU ``, barcode ``, UOM ``, quantity `12`, price ``
- Supplied label: `ACM-CABL1080`
- Review outcome group: `Variant parsing and tokenisation`
- Current evaluated decision: `review` / `attribute_conflict`
- Top candidate: `ACM-CABL0239` at 0.003

| Candidate | Name | Stock UOM | Confidence | RapidFuzz | Word TF-IDF | Char TF-IDF | Safety blocks |
|---|---|---|---:|---:|---:|---:|---|
| `ACM-CABL0239` | Tolsen Cable Tie 300mm Natural | Packet | 0.003 | 0.855 | 0.717 | 0.821 | attribute_conflict |
| `ACM-CABL0245` | Remax Cable Tie 300mm Natural | Packet | 0.003 | 0.855 | 0.717 | 0.838 | attribute_conflict |
| `ACM-CABL0316` | Kanto Cable Tie 300mm Natural | Packet | 0.003 | 0.855 | 0.717 | 0.837 | attribute_conflict |

- Label assessment: `correct_label`
- Confirmed root cause: Both the brand and size are damaged: 'Hietx' and '300m' instead of Hitex and 300mm. Generic cable-tie text retrieves the right family but ranks another brand first.
- Confirmed cost class: `review_40_seconds_top_candidate_wrong`
- Accepted fix or no-code action: Use a tenant brand lexicon for conservative typo repair and treat 300m as a likely millimetre typo only within the cable-tie family.

## 5. `ACM-T-0084`

- Tenant: `acme`
- Customer: `CUST-008`
- Raw text: `urgent Kato Hose Clip 19-25m mSS304`
- Visible fields: buyer SKU ``, barcode ``, UOM `pcs`, quantity `2`, price ``
- Supplied label: `ACM-HOSE0857`
- Review outcome group: `Variant parsing and tokenisation`
- Current evaluated decision: `review` / `attribute_conflict`
- Top candidate: `ACM-HOSE0102` at 0.002

| Candidate | Name | Stock UOM | Confidence | RapidFuzz | Word TF-IDF | Char TF-IDF | Safety blocks |
|---|---|---|---:|---:|---:|---:|---|
| `ACM-HOSE0102` | Kanto Hose Clip 19-25mm Zinc | Pcs | 0.002 | 0.855 | 0.726 | 0.726 | attribute_conflict |
| `ACM-HOSE0106` | Hitex Hose Clip 19-25mm SS304 | Pcs | 0.002 | 0.855 | 0.722 | 0.694 | active_twin, attribute_conflict |
| `ACM-HOSE0136` | Bosco Hose Clip 19-25mm SS304 | Pcs | 0.002 | 0.855 | 0.722 | 0.690 | attribute_conflict |

- Label assessment: `correct_label`
- Confirmed root cause: The range and material are split as '19-25m mSS304', and Kanto is typed as Kato. The matcher keeps the correct family and size but ranks the Zinc variant above SS304.
- Confirmed cost class: `review_40_seconds_top_candidate_wrong`
- Accepted fix or no-code action: Repair split millimetre and material tokens before structured comparison and use conservative brand correction.

## 6. `ACM-T-0115`

- Tenant: `acme`
- Customer: `CUST-003`
- Raw text: `Hitex/Self/Drilling/Screw/#10/x/1-1/2''/Zinc/Plated/x12`
- Visible fields: buyer SKU ``, barcode ``, UOM `ctn`, quantity `2`, price `10847.04`
- Supplied label: `ACM-SELF0945`
- Review outcome group: `Variant parsing and tokenisation`
- Current evaluated decision: `review` / `attribute_conflict`
- Top candidate: `ACM-SELF0457` at 0.264

| Candidate | Name | Stock UOM | Confidence | RapidFuzz | Word TF-IDF | Char TF-IDF | Safety blocks |
|---|---|---|---:|---:|---:|---:|---|
| `ACM-SELF0457` | Hitex Self Drilling Screw #12 x 2" Zinc Plated | Packet | 0.264 | 0.855 | 0.672 | 0.923 | attribute_conflict |
| `ACM-SELF0945` | Hitex Self Drilling Screw #10 x 1-1/2" Zinc Plated | Packet | 0.264 | 0.855 | 0.840 | 0.933 | attribute_conflict |
| `ACM-SELF0966` | Hitex Self Drilling Screw #10 x 1" Zinc Plated | Packet | 0.264 | 0.855 | 0.840 | 0.924 | attribute_conflict |

- Label assessment: `correct_label`
- Confirmed root cause: Slash-heavy text and the fractional inch mark prevent the #10 by 1-1/2 inch dimensions from separating cleanly. Multiple zinc-plated screws tie at the top.
- Confirmed cost class: `review_40_seconds_top_candidate_wrong`
- Accepted fix or no-code action: Parse screw gauge and fractional length before punctuation normalisation.

## 7. `ACM-T-0209`

- Tenant: `acme`
- Customer: `CUST-002`
- Raw text: `pls send Masking Tape 24mm High Temp`
- Visible fields: buyer SKU ``, barcode ``, UOM `pcs`, quantity `20`, price ``
- Supplied label: `ACM-MASK0286B`
- Review outcome group: `Variant parsing and tokenisation`
- Current evaluated decision: `review` / `attribute_conflict`
- Top candidate: `ACM-MASK0032` at 0.003

| Candidate | Name | Stock UOM | Confidence | RapidFuzz | Word TF-IDF | Char TF-IDF | Safety blocks |
|---|---|---|---:|---:|---:|---:|---|
| `ACM-MASK0032` | Kanto Masking Tape 24mm High Temp | Roll | 0.003 | 0.900 | 0.833 | 0.894 | attribute_conflict |
| `ACM-MASK0141` | Remax Masking Tape 24mm High Temp | Roll | 0.003 | 0.900 | 0.833 | 0.894 | attribute_conflict |
| `ACM-MASK0237` | Bosco Masking Tape 24mm High Temp | Roll | 0.003 | 0.900 | 0.834 | 0.897 | attribute_conflict |

- Label assessment: `correct_label`
- Confirmed root cause: The line gives product, width, and grade but omits brand and bulk status. Several active 24mm high-temperature tapes are equally compatible, so item-code order selects Kanto instead of the labelled Tolsen bulk row.
- Confirmed cost class: `review_40_seconds_top_candidate_wrong`
- Accepted fix or no-code action: Keep this class in review and require brand or a trusted customer identifier; code cannot infer the omitted bulk variant safely.

## 8. `ACM-T-0251`

- Tenant: `acme`
- Customer: `CUST-008`
- Raw text: `Vermont Ball Valve 1-1/4" SS304 x12`
- Visible fields: buyer SKU ``, barcode ``, UOM `carton`, quantity `1`, price `15422.0`
- Supplied label: `ACM-BALL0778`
- Review outcome group: `Variant parsing and tokenisation`
- Current evaluated decision: `review` / `attribute_conflict`
- Top candidate: `ACM-BALL0741` at 0.264

| Candidate | Name | Stock UOM | Confidence | RapidFuzz | Word TF-IDF | Char TF-IDF | Safety blocks |
|---|---|---|---:|---:|---:|---:|---|
| `ACM-BALL0741` | Vermont Ball Valve 1" SS304 | Nos | 0.264 | 0.855 | 0.804 | 0.892 | attribute_conflict |
| `ACM-BALL0778` | Vermont Ball Valve 1-1/4" SS304 | Nos | 0.264 | 0.855 | 0.804 | 0.903 | attribute_conflict |
| `ACM-BALL0954` | Vermont Ball Valve 3/4" SS304 | Nos | 0.060 | 0.855 | 0.804 | 0.877 | attribute_conflict |

- Label assessment: `correct_label`
- Confirmed root cause: The 1-1/4 inch fraction is not distinguished strongly enough from 1 inch. The outer-price note also makes raw price comparison unsuitable.
- Confirmed cost class: `review_40_seconds_top_candidate_wrong`
- Accepted fix or no-code action: Canonicalise mixed fractions and apply pack conversion before using a price feature.

## 9. `ACM-T-0010`

- Tenant: `acme`
- Customer: `CUST-001`
- Raw text: `Vermont  GI  Wire  Soft`
- Visible fields: buyer SKU `001245731`, barcode ``, UOM ``, quantity `5`, price ``
- Supplied label: `ACM-GIWI0811`
- Review outcome group: `Stale alias without a successor link`
- Current evaluated decision: `review` / `alias_disabled_target`
- Top candidate: `ACM-GIWI0516` at 0.043

| Candidate | Name | Stock UOM | Confidence | RapidFuzz | Word TF-IDF | Char TF-IDF | Safety blocks |
|---|---|---|---:|---:|---:|---:|---|
| `ACM-GIWI0516` | Vermont GI Wire #16 Soft | Kg | 0.043 | 0.855 | 0.649 | 0.864 | alias_disabled_target |
| `ACM-GIWI0557` | Vermont GI Wire #14 Soft | Kg | 0.043 | 0.855 | 0.649 | 0.857 | alias_disabled_target |
| `ACM-GIWI0774` | Vermont GI Wire #20 Soft | Kg | 0.043 | 0.855 | 0.660 | 0.871 | alias_disabled_target |

- Label assessment: `correct_label`
- Confirmed root cause: The trusted buyer SKU points to ACM-GIWI0811-OLD, but the data has no explicit successor link. The visible text omits wire gauge, so active #16 and #18 variants cannot be separated.
- Confirmed cost class: `review_40_seconds_top_candidate_wrong`
- Accepted fix or no-code action: Request an explicit supersedes relation and migrate the alias after approval; do not infer a successor from the code suffix.

## 10. `ACM-T-0011`

- Tenant: `acme`
- Customer: `CUST-001`
- Raw text: `need Kanto Grinder Disc Grinding`
- Visible fields: buyer SKU `001959523`, barcode ``, UOM ``, quantity `12`, price ``
- Supplied label: `ACM-ANGL0886`
- Review outcome group: `Stale alias without a successor link`
- Current evaluated decision: `review` / `alias_disabled_target`
- Top candidate: `ACM-ANGL0716` at 0.045

| Candidate | Name | Stock UOM | Confidence | RapidFuzz | Word TF-IDF | Char TF-IDF | Safety blocks |
|---|---|---|---:|---:|---:|---:|---|
| `ACM-ANGL0716` | Kanto Angle Grinder Disc 4" Grinding | Packet | 0.045 | 0.855 | 0.681 | 0.866 | alias_disabled_target |
| `ACM-ANGL0788` | Kanto Angle Grinder Disc 5" Grinding | Packet | 0.045 | 0.855 | 0.681 | 0.862 | alias_disabled_target |
| `ACM-ANGL0886` | Kanto Angle Grinder Disc 7" Grinding | Packet | 0.045 | 0.855 | 0.681 | 0.862 | alias_disabled_target |

- Label assessment: `correct_label`
- Confirmed root cause: The buyer SKU points to the disabled 7-inch item while the text omits disc size. Active grinding discs tie across sizes.
- Confirmed cost class: `review_40_seconds_top_candidate_wrong`
- Accepted fix or no-code action: Repair the stale alias through a catalogue successor mapping; keep review until the mapping is confirmed.

## 11. `ACM-T-0037`

- Tenant: `acme`
- Customer: `CUST-006`
- Raw text: `Vermont - Valve`
- Visible fields: buyer SKU `006508136`, barcode ``, UOM `unit`, quantity `20`, price ``
- Supplied label: `ACM-BALL0954`
- Review outcome group: `Stale alias without a successor link`
- Current evaluated decision: `review` / `alias_disabled_target`
- Top candidate: `ACM-BALL0146` at 0.017

| Candidate | Name | Stock UOM | Confidence | RapidFuzz | Word TF-IDF | Char TF-IDF | Safety blocks |
|---|---|---|---:|---:|---:|---:|---|
| `ACM-BALL0146` | Vermont Ball Valve 1" Brass | Nos | 0.017 | 0.570 | 0.448 | 0.742 | alias_disabled_target |
| `ACM-BALL0165` | Vermont Ball Valve 3/4" PVC | Nos | 0.017 | 0.570 | 0.465 | 0.777 | alias_disabled_target |
| `ACM-BALL0208` | Vermont Ball Valve 2" PVC | Nos | 0.017 | 0.570 | 0.465 | 0.787 | alias_disabled_target |

- Label assessment: `correct_label`
- Confirmed root cause: The alias identifies a disabled 3/4-inch SS304 valve, while the visible text contains neither size nor material. Lexical ranking has no evidence for the active replacement.
- Confirmed cost class: `review_40_seconds_top_candidate_wrong`
- Accepted fix or no-code action: Use a vendor-supplied successor relation to repair the alias; no text-only rule can select the replacement safely.

## 12. `ACM-T-0051`

- Tenant: `acme`
- Customer: `CUST-007`
- Raw text: `pls send Kanto Helmet Ratchet`
- Visible fields: buyer SKU `007895118`, barcode ``, UOM `pcs`, quantity `2`, price ``
- Supplied label: `ACM-SAFE0579`
- Review outcome group: `Stale alias without a successor link`
- Current evaluated decision: `review` / `alias_disabled_target`
- Top candidate: `ACM-SAFE0360` at 0.032

| Candidate | Name | Stock UOM | Confidence | RapidFuzz | Word TF-IDF | Char TF-IDF | Safety blocks |
|---|---|---|---:|---:|---:|---:|---|
| `ACM-SAFE0360` | Kanto Safety Helmet White Ratchet | Nos | 0.032 | 0.855 | 0.499 | 0.769 | alias_disabled_target |
| `ACM-SAFE0375` | Kanto Safety Helmet Red Ratchet | Nos | 0.032 | 0.855 | 0.497 | 0.788 | alias_disabled_target |
| `ACM-SAFE0863` | Kanto Safety Helmet Blue Ratchet | Nos | 0.032 | 0.855 | 0.501 | 0.779 | alias_disabled_target |

- Label assessment: `correct_label`
- Confirmed root cause: The stale alias contains the missing Yellow attribute, but its target is disabled. The order text only says Kanto Helmet Ratchet, leaving colour variants tied.
- Confirmed cost class: `review_40_seconds_top_candidate_wrong`
- Accepted fix or no-code action: Preserve the block and add an audited old-to-new item mapping before transferring the alias.

## 13. `ACM-T-0173`

- Tenant: `acme`
- Customer: `CUST-005`
- Raw text: `Vermont Ball Valve 3/4"`
- Visible fields: buyer SKU `005676456`, barcode ``, UOM `ea`, quantity `1`, price ``
- Supplied label: `ACM-BALL0954`
- Review outcome group: `Stale alias without a successor link`
- Current evaluated decision: `review` / `alias_disabled_target`
- Top candidate: `ACM-BALL0165` at 0.613

| Candidate | Name | Stock UOM | Confidence | RapidFuzz | Word TF-IDF | Char TF-IDF | Safety blocks |
|---|---|---|---:|---:|---:|---:|---|
| `ACM-BALL0165` | Vermont Ball Valve 3/4" PVC | Nos | 0.613 | 0.900 | 0.692 | 0.892 | alias_disabled_target |
| `ACM-BALL0802` | Vermont Ball Valve 3/4" Brass | Nos | 0.514 | 0.900 | 0.666 | 0.841 | alias_disabled_target |
| `ACM-BALL0682` | Vermont Ball Valve 1-1/4" PVC | Nos | 0.110 | 0.855 | 0.692 | 0.854 | attribute_conflict, alias_disabled_target |

- Label assessment: `correct_label`
- Confirmed root cause: The text fixes the 3/4-inch size but omits material. The stale alias points to the disabled SS304 row, while lexical evidence ranks the active PVC variant first.
- Confirmed cost class: `review_40_seconds_top_candidate_wrong`
- Accepted fix or no-code action: Require an explicit successor mapping for the stale alias; material must not be copied from a disabled target without that contract.

## 14. `ACM-T-0200`

- Tenant: `acme`
- Customer: `CUST-007`
- Raw text: `Kanto Ratchet`
- Visible fields: buyer SKU `007428936`, barcode ``, UOM ``, quantity `20`, price ``
- Supplied label: `ACM-SAFE0579`
- Review outcome group: `Stale alias without a successor link`
- Current evaluated decision: `review` / `alias_disabled_target`
- Top candidate: `ACM-SAFE0375` at 0.140

| Candidate | Name | Stock UOM | Confidence | RapidFuzz | Word TF-IDF | Char TF-IDF | Safety blocks |
|---|---|---|---:|---:|---:|---:|---|
| `ACM-SAFE0375` | Kanto Safety Helmet Red Ratchet | Nos | 0.140 | 0.570 | 0.382 | 0.623 | alias_disabled_target |
| `ACM-SAFE0360` | Kanto Safety Helmet White Ratchet | Nos | 0.129 | 0.570 | 0.384 | 0.608 | alias_disabled_target |
| `ACM-SAFE0863` | Kanto Safety Helmet Blue Ratchet | Nos | 0.129 | 0.570 | 0.385 | 0.615 | alias_disabled_target |

- Label assessment: `correct_label`
- Confirmed root cause: The order text omits both product detail and helmet colour. The disabled alias contains the missing Yellow variant, so active helmet colours remain tied after the alias is blocked.
- Confirmed cost class: `review_40_seconds_top_candidate_wrong`
- Accepted fix or no-code action: Repair the alias through a confirmed successor mapping and otherwise keep human review.

## 15. `ACM-T-0241`

- Tenant: `acme`
- Customer: `CUST-001`
- Raw text: `need Kanto Angle Disc 7"`
- Visible fields: buyer SKU `001722076`, barcode ``, UOM `packet`, quantity `12`, price ``
- Supplied label: `ACM-ANGL0886`
- Review outcome group: `Stale alias without a successor link`
- Current evaluated decision: `review` / `alias_disabled_target`
- Top candidate: `ACM-ANGL0051` at 0.316

| Candidate | Name | Stock UOM | Confidence | RapidFuzz | Word TF-IDF | Char TF-IDF | Safety blocks |
|---|---|---|---:|---:|---:|---:|---|
| `ACM-ANGL0051` | Kanto Angle Grinder Disc 7" Flap | Packet | 0.316 | 0.855 | 0.524 | 0.709 | alias_disabled_target |
| `ACM-ANGL0767` | Kanto Angle Grinder Disc 7" Cutting | Packet | 0.117 | 0.855 | 0.524 | 0.665 | alias_disabled_target |
| `ACM-ANGL0886` | Kanto Angle Grinder Disc 7" Grinding | Packet | 0.117 | 0.855 | 0.524 | 0.676 | alias_disabled_target |

- Label assessment: `correct_label`
- Confirmed root cause: The line contains brand and 7-inch size but omits Grinding. The stale alias points to the disabled Grinding row, and the active Flap row ranks first on visible text.
- Confirmed cost class: `review_40_seconds_top_candidate_wrong`
- Accepted fix or no-code action: Use a maintained successor relation to recover the grade; do not let a disabled alias silently fill an omitted attribute.

## 16. `NRD-T-0065`

- Tenant: `nordic`
- Customer: `CUST-003`
- Raw text: `Fjordal Breast Whole`
- Visible fields: buyer SKU `003508914`, barcode ``, UOM ``, quantity `2`, price `122.5`
- Supplied label: `NRD-CHIC0324`
- Review outcome group: `Stale alias without a successor link`
- Current evaluated decision: `review` / `alias_disabled_target`
- Top candidate: `NRD-CHIC0452` at 0.500

| Candidate | Name | Stock UOM | Confidence | RapidFuzz | Word TF-IDF | Char TF-IDF | Safety blocks |
|---|---|---|---:|---:|---:|---:|---|
| `NRD-CHIC0452` | Fjordal Chicken Breast Whole 1kg | Kg | 0.500 | 0.855 | 0.659 | 0.801 | alias_disabled_target |
| `NRD-CHIC0324` | Fjordal Chicken Breast Whole 2kg | Kg | 0.370 | 0.855 | 0.659 | 0.800 | alias_disabled_target |
| `NRD-CHIC0217` | Fjordal Chicken Breast Whole 10kg | Kg | 0.086 | 0.855 | 0.573 | 0.786 | alias_disabled_target |

- Label assessment: `correct_label`
- Confirmed root cause: The stale alias points to the disabled 2kg item, while the visible line omits pack size. Price is close for both 1kg and 2kg rows and ranks 1kg first.
- Confirmed cost class: `review_40_seconds_top_candidate_wrong`
- Accepted fix or no-code action: Transfer the alias only through an explicit old-to-new mapping and keep pack-ambiguous text in review.

## 17. `ACM-T-0031`

- Tenant: `acme`
- Customer: `CUST-005`
- Raw text: `need Bosco Nitrile Glove S Blue`
- Visible fields: buyer SKU ``, barcode ``, UOM ``, quantity `3`, price ``
- Supplied label: `ACM-NITR0655`
- Review outcome group: `Ranking and retrieval tie`
- Current evaluated decision: `review` / `low_confidence`
- Top candidate: `ACM-NITR0470` at 0.017

| Candidate | Name | Stock UOM | Confidence | RapidFuzz | Word TF-IDF | Char TF-IDF | Safety blocks |
|---|---|---|---:|---:|---:|---:|---|
| `ACM-NITR0470` | Bosco Nitrile Glove L Blue | Box | 0.017 | 0.865 | 0.759 | 0.926 | - |
| `ACM-NITR0569` | Bosco Nitrile Glove M Blue | Box | 0.017 | 0.865 | 0.759 | 0.935 | - |
| `ACM-NITR0655` | Bosco Nitrile Glove S Blue | Box | 0.017 | 0.900 | 0.759 | 0.958 | - |

- Label assessment: `correct_label`
- Confirmed root cause: The single-letter glove size S is not weighted as a structured size. Small, medium, and large blue Bosco gloves tie and catalogue order puts L first.
- Confirmed cost class: `review_40_seconds_top_candidate_wrong`
- Accepted fix or no-code action: Extract S, M, L, and XL only inside size-bearing product families and require exact size agreement.

## 18. `ACM-T-0185`

- Tenant: `acme`
- Customer: `CUST-003`
- Raw text: `Safety Helmet Standard`
- Visible fields: buyer SKU `003516998`, barcode ``, UOM `ea`, quantity `20`, price `193.37`
- Supplied label: `ACM-SAFE0725`
- Review outcome group: `Ranking and retrieval tie`
- Current evaluated decision: `review` / `low_confidence`
- Top candidate: `ACM-SAFE0523` at 0.002

| Candidate | Name | Stock UOM | Confidence | RapidFuzz | Word TF-IDF | Char TF-IDF | Safety blocks |
|---|---|---|---:|---:|---:|---:|---|
| `ACM-SAFE0523` | Remax Safety Helmet Blue Standard | Nos | 0.002 | 0.855 | 0.633 | 0.865 | - |
| `ACM-SAFE0581` | Stallion Safety Helmet White Standard | Nos | 0.002 | 0.855 | 0.631 | 0.837 | - |
| `ACM-SAFE0019` | Bosco Safety Helmet White Ratchet | Nos | 0.000 | 0.855 | 0.000 | 0.000 | - |

- Label assessment: `correct_label`
- Confirmed root cause: A 0.55-confidence alias points to the labelled Kanto Yellow helmet, but it is too weak for automatic use and contributes too little to ranking. Generic helmet text ranks unrelated brands above it.
- Confirmed cost class: `review_40_seconds_top_candidate_wrong`
- Accepted fix or no-code action: Let weak aliases improve candidate ranking while retaining the automatic-match block until independent attributes confirm the target.

## 19. `ACM-T-0221`

- Tenant: `acme`
- Customer: `CUST-007`
- Raw text: `remax pvc pipe 40mm class c`
- Visible fields: buyer SKU ``, barcode ``, UOM ``, quantity `24`, price ``
- Supplied label: `ACM-PVCP1002`
- Review outcome group: `Ranking and retrieval tie`
- Current evaluated decision: `review` / `low_confidence`
- Top candidate: `ACM-PVCP0076` at 0.585

| Candidate | Name | Stock UOM | Confidence | RapidFuzz | Word TF-IDF | Char TF-IDF | Safety blocks |
|---|---|---|---:|---:|---:|---:|---|
| `ACM-PVCP0076` | Remax PVC Pipe 40mm Class E | Length | 0.585 | 0.884 | 0.854 | 0.889 | - |
| `ACM-PVCP1002` | Remax PVC Pipe 40mm Class C | Length | 0.585 | 0.900 | 0.854 | 0.922 | - |
| `ACM-PVCP1073` | Remax PVC Pipe 40mm Class D | Length | 0.585 | 0.884 | 0.854 | 0.889 | - |

- Label assessment: `correct_label`
- Confirmed root cause: The line explicitly contains Class C, but Class C and Class E candidates receive equal scores. Item-code order places Class E first.
- Confirmed cost class: `review_40_seconds_top_candidate_wrong`
- Accepted fix or no-code action: Represent PVC class as a structured categorical feature instead of relying on general token similarity.

## 20. `NRD-T-0030`

- Tenant: `nordic`
- Customer: `CUST-008`
- Raw text: `urgent Hablerg Puff Pasry Block 5kg`
- Visible fields: buyer SKU ``, barcode ``, UOM ``, quantity `2`, price `360.39`
- Supplied label: `NRD-PUFF0459`
- Review outcome group: `Ranking and retrieval tie`
- Current evaluated decision: `review` / `low_confidence`
- Top candidate: `NRD-PUFF0254` at 0.039

| Candidate | Name | Stock UOM | Confidence | RapidFuzz | Word TF-IDF | Char TF-IDF | Safety blocks |
|---|---|---|---:|---:|---:|---:|---|
| `NRD-PUFF0254` | Fjordal Puff Pastry Block 5kg | Packet | 0.039 | 0.855 | 0.479 | 0.660 | - |
| `NRD-PUFF0459` | Halberg Puff Pastry Block 5kg | Packet | 0.039 | 0.855 | 0.479 | 0.730 | - |
| `NRD-PUFF0098` | Cape Bay Puff Pastry Block 5kg | Packet | 0.008 | 0.855 | 0.445 | 0.673 | - |

- Label assessment: `correct_label`
- Confirmed root cause: Halberg is misspelled as Hablerg. Product form and pack match several brands, and price similarity incorrectly moves Fjordal above the labelled Halberg row.
- Confirmed cost class: `review_40_seconds_top_candidate_wrong`
- Accepted fix or no-code action: Apply conservative matching against the tenant brand lexicon before price contributes to ranking.
