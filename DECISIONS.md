# Decision Log

This file records choices that could reasonably have gone another way. Each choice includes the evidence used and the event that would cause it to be reviewed.

## D-01 - Optimise cost at controlled coverage

**Context:** A wrong automatic match costs about 800 operator seconds. Human review costs 40 seconds. Correct automatic matching saves 20 seconds. The costs are not balanced.

**Options:** (a) maximise accuracy, (b) maximise automatic coverage, or (c) maximise coverage under a strict precision and safety policy.

**Chose:** Option (c). Coverage will be maximised while `AUTO` precision stays at or above 98%. The lower end of the 95% confidence range must stay above the 92.7% economic break-even point. Hard safety gates must also pass.

**Evidence:** The break-even point is `760 / 820 = 92.7%`. A 29.8% blank-label rate was found. The simple exact-name rule reached only 76.9% precision. High coverage without safe precision would increase cost.

**Reversal trigger:** The policy will be reviewed if wrong-match cost, review cost, review capacity, or customer risk changes.

## D-02 - Apply tenant isolation before retrieval

**Context:** A cross-tenant answer is a correctness failure. Filtering a global candidate list after retrieval would allow unsafe candidates into ranking and confidence estimates.

**Options:** (a) retrieve globally and filter later, or (b) build and search one tenant-scoped candidate pool.

**Chose:** Option (b). The tenant will be selected before identifier lookup or text retrieval.

**Evidence:** Separate Acme and Nordic catalogues were supplied. Their item-code prefixes were clean. This boundary can be enforced before any score is calculated.

**Reversal trigger:** No business trigger is planned. A shared search service may be used later only if tenant ownership is enforced inside every lookup and tested as a hard gate.

## D-03 - Separate candidate retrieval from automatic matching

**Context:** The correct item may be useful in the top three even when there is not enough proof for an automatic match. One universal threshold would mix retrieval quality with decision risk.

**Options:** (a) return only the top scored item, or (b) retrieve a ranked candidate set and use a separate decision layer.

**Chose:** Option (b). Retrieval will aim for recall@3. The decision layer will use confidence, score margin, and safety checks to choose `AUTO`, `REVIEW`, or `REJECT`.

**Evidence:** The output requires up to three candidates. The audit also found 25 active twin groups. A useful candidate list can exist when the first item is not safe enough to accept.

**Reversal trigger:** The choice will be reviewed only if review no longer uses candidate evidence and recall@3 is removed from the product contract.

## D-04 - Use active catalogue rows and gated aliases

**Context:** Identifier evidence can be strong, but the source data contains unsafe targets and old mappings.

**Options:** (a) trust every exact identifier and alias, (b) ignore aliases, or (c) use identifiers and aliases only after safety checks.

**Chose:** Option (c). Disabled and misc rows will be excluded. Aliases will be checked by tenant, customer, date, source, confidence, collision state, and target state.

**Evidence:** The audit found 38 disabled catalogue rows, 18 misc rows, 70 current aliases to disabled items, 26 expired aliases, and 26 stored collision groups. Sixteen barcode groups contained two active rows.

**Reversal trigger:** Alias checks may be simplified if a production contract guarantees one current, customer-scoped, active target and that contract is monitored.

## D-05 - Start with lexical retrieval

**Context:** The order lines are short. The full catalogue contains 1,672 rows. A local and explainable baseline can be built before a model is added.

**Options:** (a) start with embeddings, (b) start with lexical word and character matching, or (c) use identifiers only.

**Chose:** Option (b). Lexical retrieval will be built first. No embedding or LLM lane will be included in the first version.

**Evidence:** Mean order text length was about 29 characters in both training and holdout data. The two sets showed no large visible shift. Name-only matching was unsafe, so structured evidence and safety checks are still required.

**Reversal trigger:** An embedding lane will be reconsidered if out-of-fold tests show a clear gain in recall@3 or net cost without lower automatic precision or excessive latency.

## D-06 - Select thresholds from out-of-fold results

**Context:** Only 420 labelled training rows are available. A threshold selected on fitted predictions would give an overly positive result. One random split may also move sharply with this sample size.

**Options:** (a) tune and report on all fitted rows, (b) use one random train-test split, or (c) use repeated or grouped out-of-fold predictions and report uncertainty.

**Chose:** Option (c). Score values and decision limits will be selected from out-of-fold predictions. Each row will be predicted by a version that was not fitted on that row. Precision, coverage, net cost, and their uncertainty will be reported.

**Evidence:** The training set contains 295 item labels and 125 blank labels. Acme and Nordic also have different blank-label rates. Repeated or grouped checks will reduce dependence on one small split.

**Reversal trigger:** A fixed and much larger production test set may replace repeated out-of-fold checks when it is kept separate from all fitting and threshold work.

## D-07 - Keep the lexical hybrid for ranked candidates

**Context:** Exact rules, RapidFuzz, word TF-IDF, character TF-IDF, and a hybrid were measured. Exact rules had low coverage. RapidFuzz also missed many useful candidates.

**Options:** (a) use one text method, (b) combine exact and lexical evidence, or (c) add embeddings.

**Chose:** Option (b). Exact evidence, RapidFuzz, word TF-IDF, and character TF-IDF are combined. Their values are kept as separate evidence. A small ranker orders the combined set.

**Evidence:** Character and word TF-IDF each reached 93.6% recall@3 on answerable rows. RapidFuzz reached 59.0%. The grouped hybrid ranker reached 93.2% recall@3. Repeated evaluation runs kept p95 matching time well below the 250 ms limit; `EVAL.md` records the submitted run.

**Reversal trigger:** The retrieval mix will be changed if a simpler lane matches its recall@3 and safety results, or if a tested new lane gives a clear net-cost gain.

## D-08 - Keep automatic matching disabled at the draft checkpoint

**Context:** An automatic lane should not be released only because its observed precision looks high. The amount of supporting test data also matters.

**Options:** (a) release the best observed point, (b) weaken the uncertainty gate, or (c) keep automatic matching disabled until the stated gates pass.

**Chose:** Option (c). The draft config blocks automatic matching. Review candidates are still returned.

**Evidence:** The safest measured point made 12 automatic matches and all 12 were correct. Its Wilson 95% lower bound was 75.7%. This was below the 92.7% economic floor. No tested point passed every gate.

**Reversal trigger:** The choice will be reviewed after the 20-line manual review, a general matcher fix, or more independent labelled data. The supplied labels will not be changed in primary metrics.

## D-09 - Allow a perfect observed small-sample fallback

**Context:** The normal policy requires the Wilson 95% lower bound to stay above the 92.7% economic floor. A small automatic lane can be correct on every observed row and still fail this rule.

**Options:** (a) keep every small lane blocked, (b) release the lowest-cost point even when it has known errors, or (c) allow only a point with 100% observed out-of-fold precision.

**Chose:** Option (c). The normal Wilson policy is tried first. If it fails, the highest-coverage point with no observed wrong automatic match may be used. All tenant, item-state, ambiguity, and latency gates remain.

**Evidence:** The draft found a perfect automatic lane with too few rows for the Wilson gate. Review also found that several supplied blank labels were false blanks. Keeping all automatic matching disabled would provide no operating value.

**Reversal trigger:** The fallback will be removed when enough independent labelled data exists to apply the normal uncertainty rule, or if a wrong automatic match is found in the fallback lane.

## D-10 - Let independent catalogue evidence clear a weak alias block

**Context:** A weak or inferred alias was treated as a hard block even when complete catalogue evidence supported the same item. This caused safe candidates to be reviewed.

**Options:** (a) always block weak aliases, (b) trust weak aliases directly, or (c) allow independent catalogue evidence to prove the item without trusting the alias.

**Chose:** Option (c). Brand, all visible numbers, word evidence, and character evidence must agree. A weak alias cannot create an automatic match by itself.

**Evidence:** `ACM-T-0008` and `ACM-T-0184` had the correct top item with matching visible attributes. Incomplete inferred-alias lines such as `ACM-T-0090` and `ACM-T-0253` remain blocked.

**Reversal trigger:** The rule will be tightened if production errors show that independent catalogue evidence is not strong enough, or simplified if alias quality is enforced by contract.

## D-11 - Normalise unit and each as piece UOM values

**Context:** Catalogue piece units use names such as `Pcs`. Order lines also use `unit`, `each`, and `ea` for the same basic unit.

**Options:** (a) treat every spelling as different, (b) map common piece words, or (c) ignore UOM conflicts.

**Chose:** Option (b). Common piece words are normalised to `piece`. A piece request still conflicts with packet or length stock units.

**Evidence:** The false conflict on `ACM-T-0038` used `unit` against `Pcs`. The packet and length conflicts on `ACM-T-0142`, `ACM-T-0212`, and `ACM-T-0218` remain unsafe after normalisation.

**Reversal trigger:** The mapping will be moved to tenant data if tenants use these words with different business meanings.

## D-12 - Separate unique identifiers from the text threshold

**Context:** A global probability threshold left unique active barcodes and one trusted alias in review even after identifier collisions and unsafe targets had been removed.

**Options:** (a) keep the global threshold for every lane, (b) lower the text threshold, or (c) let a unique safe identifier answer directly while retaining the text threshold.

**Chose:** Option (c). Unique tenant-scoped item codes, barcodes, part numbers, and trusted aliases can create an automatic match. Duplicate identifiers, weak aliases, stale targets, disabled items, and cross-lane conflicts remain blocked.

**Evidence:** Ten additional out-of-fold lines had a unique safe identifier; all ten matched the supplied item. The final point increased from 14 to 24 correct automatic matches, raised coverage from 3.3% to 5.7%, and reduced estimated cost from 15,960 to 15,360 seconds without changing recall@3.

**Reversal trigger:** The lane will be disabled or narrowed if a confirmed identifier match is wrong or if identifier uniqueness is no longer guaranteed within a tenant snapshot.

## D-13 - Enforce the evaluation baseline in code

**Context:** Documented release thresholds do not stop a regression unless the evaluation command exits unsuccessfully.

**Options:** (a) inspect the report manually, (b) test only schema and safety properties, or (c) commit a metric baseline and enforce it during evaluation.

**Chose:** Option (c). The baseline pins the training hash and minimum precision, coverage, recall@3, and blank refusal rate, plus maximum cost, latency, wrong autos, and safety violations.

**Evidence:** `evaluate.py` now exits non-zero when a metric crosses the committed limit. Unit tests cover metric and training-hash failures.

**Reversal trigger:** A baseline changes only with a reviewed data or policy change recorded in this log.

## D-14 - Add one report index instead of materializing the dashboard

**Context:** The grouped rewrite was correct but took 12–13 seconds without an index. The 10-second budget still had to be met without making a live dashboard stale.

**Options:** (a) materialize the report, (b) add several covering indexes, or (c) add one index for the measured previous-day item bottleneck.

**Chose:** Option (c). The migration adds `(tenant_id, day, item_code)` on `match_event`. The report remains a live query.

**Evidence:** Removing `repeat_items_prev_day` cut a controlled probe from 20.46 to 3.46 seconds. The one index reduced the full rewrite from 12–13 seconds to a 6.326-second median. It costs 40.6 MB in the supplied database.

**Reversal trigger:** Replace it with incremental aggregates if ledger insert latency or WAL growth breaches its production budget, or if report volume grows enough to push the indexed query back over 10 seconds.

## D-15 - Preserve concurrent sync edits as explicit conflicts

**Context:** The adapter has no field-level base snapshot, so it cannot tell whether concurrent local and ERP changes are safely mergeable. The old 409 handler overwrote the ERP with the local payload.

**Options:** (a) local wins, (b) remote wins, (c) merge dictionaries, or (d) preserve both and require resolution.

**Chose:** Option (d). Version changes create a conflict record containing both payloads. Push skips unresolved conflicts.

**Evidence:** The supplied scenario changes price locally and UOM remotely. Blind local-wins loses the UOM; remote-wins loses the price; a dictionary merge has no base value to distinguish independent edits from competing edits. Preserving both is the only lossless option under the current contract.

**Reversal trigger:** Add automatic field-level merge only after the store retains the common base payload and each field has an approved merge policy.
