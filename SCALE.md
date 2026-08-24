# Task 6: Scale and Rollout

## First limit

The first failure is catalogue-index memory and rebuild time, not average request throughput. The current process eagerly creates word and character TF-IDF matrices for every tenant. That is small for the supplied 1,672 catalogue rows, but four million rows plus character 3–5 grams can consume many gigabytes and make process startup or tenant refresh unacceptably slow.

The traffic average is only about 1.74 lines per second (`150,000 / 86,400`), although peak traffic will be higher. The measured matcher p95 is below 70 ms on the assessment data. This does not prove 40,000-row tenant latency, but it suggests loading and rebuilding all 500 indexes fails before average request CPU.

I would keep tenant isolation as the physical boundary. Indexes would be versioned per tenant, loaded lazily, and cached under a memory budget. Large or inactive tenants would not occupy every worker. Catalogue changes would build a new tenant index beside the old one, run smoke queries, then switch an atomic version pointer. Requests already using the old version can finish safely.

No embeddings are used, so there is no embedding re-index cost. A 40,000-item edit still requires lexical vectorisation. I would benchmark that size before setting an SLA and initially rebuild it as a background job. While rebuilding, the old snapshot can serve review candidates, but automatic matching should stop if the change disables items or the snapshot exceeds its freshness limit. This prevents a stale index from shipping an item that the catalogue has already withdrawn.

At higher traffic, each worker should retrieve from a dedicated tenant index service rather than hold all matrices itself. Catalogue versions, index build duration, loaded bytes, eviction count, query p95, and stale-index age need tenant labels in monitoring. The alias lookup needs a database index on `(tenant_id, customer_id, normalized_sku)` plus retention for obsolete history.

## Preventing alias feedback loops

An operator confirmation is evidence, not immediate truth. I would store it as an immutable observation with tenant, customer, source line, chosen item, rejected candidates, operator, matcher version, and timestamp. Automatic matcher outputs must never confirm themselves.

New aliases begin in quarantine and cannot create an automatic match. Promotion requires independent evidence, for example confirmations on separate orders and preferably separate operators, with no contradictory active mapping. High-risk cases such as pack twins, disabled successors, and cross-tenant-looking codes always require stronger review.

The service should continuously measure alias outcomes using later edits, cancellations, returns, and credit notes. Contradictory evidence demotes an alias immediately. Promotion and demotion are versioned and reversible. Limits on one operator's influence, anomaly alerts for sudden alias growth, and sampled audits reduce the chance that a repeated workflow mistake becomes accepted truth.

## Shipping matcher changes

I would use shadow first, then canary; they answer different questions.

In shadow mode, the candidate matcher sees production lines but cannot affect orders or write aliases. Its decisions, candidates, reasons, latency, and catalogue version are recorded beside the current matcher's output. Immediate gates catch cross-tenant, disabled-item, schema, latency, and determinism failures. Disagreements go to a sampled review queue.

Ground truth arrives late, so the comparison window stays open through fulfilment and the normal return or correction period. Release requires no hard safety violation, automatic precision at least 98%, the precision lower bound above the economic floor when sample size permits, non-increasing net cost, and no important tenant or noise segment regression. Coverage is useful only after those gates pass.

The canary then enables decisions for a small set of representative, lower-risk tenants while retaining a control group. Rollout expands by tenant, not random line, because indexes, catalogues, and aliases are tenant state. Every prediction carries a matcher and index version. A kill switch sends all uncertain traffic to review and can restore the previous immutable version without rebuilding.

Canary promotion waits for delayed outcomes rather than declaring success from click-through or operator acceptance. I would expand in stages such as 1%, 5%, 20%, 50%, and 100%, with a fresh outcome check at each stage. A single cross-tenant auto-match, disabled-item auto-match, or confirmed wrong match in the small-sample fallback stops rollout immediately.
