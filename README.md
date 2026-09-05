# Warrant — Intent Conformance for Agent Purchases

**Razorpay AI Buildathon · Track 02, AI Risk Manager**

> Build a working detector, verifier or auto-responder for one class of loss,
> with measured precision and recall on a held-out test set. The bar: honest
> metrics including false-positive cost. Strictly defence-only.

---

## The problem

When an AI agent buys on a customer's behalf and the purchase is later disputed,
the evidence that used to win those cases — IP address, device fingerprint,
navigation path — doesn't exist. Merchants absorb the loss, and every dispute
counts against a ratio whose threshold tightened to 1.5% in April 2026.

The industry's answer is cryptographically signed mandates (Google AP2). Those
prove the authorization document wasn't tampered with. They do not prove the
cart honours the intent.

The reference implementations verify two things: `total_within_intent` and
`merchant_allowed`. Amount, and merchant allow-list. So a mandate reading
*"groceries, under ₹2,000, weekly"* approves ₹1,775 of Seagram's Blenders Pride
whisky, with a perfect signature chain.

Warrant is the missing check.

---

## Status

**Milestone 1 complete** — taxonomy, catalog, schemas, tests. The verifier
itself is not built yet. Nothing in this repo yet claims a metric.

| Milestone | | |
|---|---|---|
| 1 | Taxonomy, catalog, core schemas | ✅ |
| 2 | Intents, carts, violation injectors, splits | ◻ |
| 3 | Baseline — the K1 go/no-go | ◻ |
| 4 | Deterministic checker, category mapping, semantic checker | ◻ |
| 5 | Calibration, cost policy, evidence log | ◻ |
| 6 | India rails, UI, sealed test run, report | ◻ |

---

## The dataset

Every product in the catalog is real, with a real Indian price. Nothing is
invented.

| Source | Rows | Covers |
|---|---|---|
| BigBasket | 8,208 | grocery, produce, staples, personal care, household |
| Karnataka excise price list | 8,180 | alcohol |
| Myntra | 14,214 | apparel |
| Flipkart | 2,460 | electronics |
| A-Z Medicines of India | 253,000 | pharmacy |
| Swiggy | 60,000 | restaurant |

~295,000 rows map onto the taxonomy; 800 are selected by quota into
`data/catalog/catalog.jsonl`.

**What is still synthetic:** the mandates, the carts and the violation
labels. No public corpus of agent-initiated purchase disputes exists — that is
the honest ceiling here, not an oversight. See DECISIONS.md D-002.

`data/raw/` is not committed. The repo carries the loader and the mapping rules;
the sources are third-party scrapes redistributed under licences their uploaders
could not grant (D-011).

---

## Run it

    make setup
    make dataset SEED=1337     # build the catalog
    make test                  # 55 tests
    make report                # mapping coverage and composition
    make sample                # eyeball the catalog

On Windows without GNU make, `.\make.ps1 <target>` mirrors the same targets.

`make eval` arrives with Milestone 3. Without `data/raw/`, the catalog tests
skip and the rest of the suite still runs.

Change the seed and re-run. Once there are numbers, they should move by less
than 3%. If they don't, the result isn't real and I'd want to know.

---

## Design

**Deterministic first, model last.** Amount caps, expiry, frequency, merchant
allow-lists and denied categories are comparisons and set membership. They never
touch a language model. The model exists for one job: judging whether a basket
of items honours a sentence a human wrote.

    C1  mandate ingest        signature, expiry, revocation   — hard gate, no model
    C2  constraint extraction NL -> typed constraints         — LLM, once, cached
    C3  deterministic checker amount, expiry, frequency, ...  — rules only
    C4  semantic checker      ① embed -> category  ② attributes — LLM on the remainder
    C5  decision policy       expected-cost argmin            — solver, no model

Three outcomes: `ALLOW`, `REFUSE`, `ESCALATE`. Escalation is the product, not a
failure mode.

**Fail closed.** If the model is unavailable, the output unparseable, or a
category unknown, the verdict is `ESCALATE` — never `ALLOW`.

---

## Scope

**In:** verifying carts against signed intents; constraint extraction;
calibrated three-way decisions; tamper-evident decision log; mapping escalation
onto Indian payment rails.

**Out:** issuing mandates, agent identity verification, bot detection, fraud
scoring, moving money. Those layers exist — Visa TAP, Skyfire, HUMAN
AgenticTrust, Forter, Riskified. Warrant sits after identity and before money.

---

## Honest limitations

1. Mandates, carts and violation labels are synthetic. Generator in the repo.
2. Agent transaction volume is small today — a large multiple on a small base.
   This is built ahead of the curve.
3. NPCI's UAP spec is unpublished. The India layer will be built against
   announced mechanics behind an adapter interface.
4. Category mapping is imperfect and the residue is visible in the ground truth
   itself. Measured, not assumed — DECISIONS.md L-001.
5. Footwear, and therefore size-based attribute matching, is out of the current
   catalog — D-004.

---

## Reading

[DECISIONS.md](DECISIONS.md) — every non-obvious choice and why, the kill
criteria set on day one, six open problems in the design docs, and the measured
limitations of what's built.
