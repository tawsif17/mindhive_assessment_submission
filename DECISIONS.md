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
