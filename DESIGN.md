# Matcher Design

## 1. Objective and operating policy

This system should not maximise accuracy. A wrong automatic match can ship the wrong goods. Its cost is much higher than the cost of human review.

The supplied cost model is:

| Outcome | Cost in operator seconds |
|---|---:|
| Correct automatic match | -20 |
| Human review | +40 |
| Wrong automatic match | +800 |

For a proposed automatic match, the expected cost is:

```text
auto_cost = p(correct) * -20 + p(wrong) * 800
```

Review costs 40 seconds. Automatic matching becomes cheaper than review when the chance of being correct is above about 92.7%.

This break-even point is an economic floor. It is not the release target. The first operating policy will maximise coverage while all these rules are met:

- Precision on `AUTO` is at least 98%.
- The lower end of the 95% confidence range stays above the 92.7% economic floor. This range shows how uncertain the measured precision is.
- No cross-tenant, disabled-item, or misc-row automatic match is made.
- Net cost is used to choose between score limits that pass the safety rules.

The uncertainty rule remains the normal policy. A small-sample fallback was accepted after the error review. It is used only when no point passes the uncertainty rule. The fallback requires 100% observed out-of-fold precision. It also requires zero hard safety violations and p95 latency below 250 ms. The Wilson result is still reported. This accepts more uncertainty. It does not accept a known wrong automatic match.

The final score limit will be selected from out-of-fold training results. Each row will be predicted by a version that was not fitted on that row. The limit will not be selected from the same predictions used to fit scoring values.

The order-operations owner will own the precision and review policy. Engineering will measure the options and apply the approved setting. The policy should be reviewed when error costs, review capacity, or customer risk changes.

## 2. Pipeline and stage contracts

```text
raw order line
      |
      v
normalisation and field parsing
      |
      v
tenant-scoped active catalogue
      |
      v
strong identifier evidence
      |
      v
candidate retrieval
      |
      v
structured evidence and scoring
      |
      v
safety checks
      |
      v
confidence and score margin
      |
      v
AUTO / REVIEW / REJECT
```

| Stage | Contract |
|---|---|
| Normalisation | Text, codes, barcode, size, pack, and UOM fields are parsed in a fixed way. The original input is kept. |
| Tenant catalogue | Only rows owned by the input tenant are loaded. Disabled and misc rows are excluded from normal search indexes. |
| Identifier evidence | Barcode, item code, part number, and trusted customer aliases are checked. A strong identifier can answer directly only when one safe active target remains. |
| Candidate retrieval | Text and structured fields are used to find likely items. The correct item should be placed in the top three where possible. |
| Candidate scoring | Brand, family, size, pack, UOM, price, text, and alias quality are compared. Scores are kept as evidence, not treated as truth. |
| Safety checks | Cross-tenant targets, disabled items, misc rows, conflicting IDs, active twins, weak aliases, and small score gaps are blocked. |
| Decision | Confidence and the gap between the first two candidates are checked. A stable reason code and up to three candidates are returned. |

Candidate retrieval and automatic matching are separate problems. Retrieval should aim for high recall in the top three. The decision stage should be conservative about choosing the first item.

`AUTO` requires either one unique strong identifier or one safe candidate above both probabilistic limits. Duplicate identifiers, stale aliases, disabled targets, and conflicts always block the identifier lane. `REVIEW` is used when useful candidates remain but the proof is weak. `REJECT` is used for clear non-item text or when no useful candidate is found.

The same input and catalogue version must always produce the same output. Ties will be sorted by stable fields such as item code. No network call will be used during matching.

## 3. Expensive failure modes

Six failure modes were selected from the data audit.

| Failure | Audit evidence | Control |
|---|---|---|
| 1. A code from another tenant is returned. | Tenant ownership is a hard rule. | Tenant filtering is applied before retrieval. A global candidate pool is never used. |
| 2. A disabled or old item is returned. | 38 disabled rows and 70 current aliases to disabled items were found. | Active-target checks are applied to every lane. Old items are not returned automatically. |
| 3. The wrong twin or pack is returned. | 25 active twin groups and 16 duplicate-barcode groups with two active rows were found. | Pack, UOM, duplicate-ID, and score-gap checks are applied. Review is used when the choice is not proved. |
| 4. A dirty alias is trusted. | 26 expired aliases, 26 stored collision groups, 176 inferred aliases, and 349 aliases below confidence 1.0 were found. | Tenant, customer, date, source, confidence, collision, and target state are checked. |
| 5. A fee or other non-item is matched. | 18 misc catalogue rows and a 29.8% blank-label rate were found. | Misc rows are removed. Clear non-item lines are rejected. Weak cases are reviewed. |
| 6. A visible name is treated as proof. | The simple exact-name rule reached only 76.9% precision and made 31 false matches. | Name evidence cannot create an automatic match by itself. Size, pack, UOM, and score margin must support it. |

These failures are not equally common. They are all expensive because they can create a confident wrong answer.

## 4. Cold start

A new tenant must work with an empty alias table. Its main path will use:

- The tenant catalogue
- Unique active barcodes and part numbers
- Normalised catalogue text
- Brand, family, size, pack, and UOM evidence

Coverage will probably be lower for a new tenant. Safety rules will remain unchanged.

A mature tenant may add a trusted alias lane. Alias history can improve coverage, but it is not required for basic matching. Low-quality aliases will not be allowed to weaken the catalogue-only path.

## 5. Embeddings and LLMs

No embedding or LLM lane will be included in the first version.

A lexical baseline will be measured first. Lexical matching compares words and character parts. It is suitable for the short order lines and the 1,672 supplied catalogue rows. It is also local, fast, stable, and easy to explain.

An embedding lane may be tested after lexical retrieval. It will be kept only if out-of-fold results show better recall@3 or lower net cost without lower automatic-match precision or excessive latency. It will never bypass tenant or safety checks. The lexical path will remain available when a model is missing or stale.

## 6. Delivery boundary

The first version will be delivered in a short fixed window. The following work is outside that boundary:

- Network-based inference
- Online learning from every operator action
- Large distributed search systems
- Full production monitoring infrastructure
- Automatic repair of catalogue and alias data
- Source-document OCR and voice transcription
- Embeddings without measured gain

Later work will require production evidence. This includes real error costs, review limits, catalogue-change rates, alias-error rates, delayed labels, and traffic by tenant. These facts should be measured before a larger system is built.
