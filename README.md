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

**Milestones 1–3 complete.** Dataset built, baseline run, gap measured. The
verifier itself is next.

| Milestone | | |
|---|---|---|
| 1 | Taxonomy, catalog, core schemas | ✅ |
| 2 | Intents, carts, violation injectors, splits | ✅ |
| 3 | Baseline — the K1 go/no-go | ✅ |
| 4 | Deterministic checker, category mapping, semantic checker | ◻ |
| 5 | Calibration, cost policy, evidence log | ◻ |
| 6 | India rails, UI, sealed test run, report | ◻ |

### The gap, measured

The reference AP2 check — `total_within_intent + merchant_allowed`, the one the
shipping implementations perform — scores **16.8% violation recall** on
train+validation (n=3,126).

| Violation type | Baseline recall | |
|---|---|---|
| `AMOUNT_EXCEEDED` | **100%** | amount check |
| `MERCHANT_OUT_OF_SCOPE` | **100%** | allow-list check |
| `CATEGORY_DENIED` — *the whisky case* | **0%** | |
| `CATEGORY_OUT_OF_SCOPE` | 0% | |
| `ATTRIBUTE_MISMATCH` | 0% | |
| `BRAND_EXCLUSION` | 0% | |
| `QUANTITY_ANOMALY` | 0% | |
| `MANDATE_EXPIRED` | 0% | |
| `FREQUENCY_EXCEEDED` | 0% | |
| `UNAUTHORIZED_SUBSTITUTION` | 0% | |
| `ADD_ON_CREEP` | 0% | |
| `TIMING_VIOLATION` | 0% | |

Its precision is 1.0 and it has zero false positives. **The baseline is not
inaccurate about what it checks — it is incomplete.** That distinction matters:
claiming otherwise would be a strawman.

Kill criterion K1 ("if the baseline catches most violations, stop — the gap is
not real") **has not fired**. `tests/test_baseline.py` asserts it, so a dataset
change that quietly flatters the baseline fails the suite.

Reproduce: `make baseline`. The test split is untouched — the baseline script
refuses `--splits test`.

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
`data/catalog/catalog.jsonl`, which **is** committed so a clean clone works
without the raw sources.

From those, `make pairs` builds **3,908 labelled (mandate, cart) pairs** from
4,000 mandates over 30 intent templates — split 60/20/20 **by mandate**, so no
mandate straddles a split. Twelve violation injectors, one violation per pair,
quota'd so every type has 25–29 test cases.

`tests/test_dataset.py` audits the labels independently: it re-derives
conformance from each mandate's own constraints rather than trusting the
generator. It has already caught two real defects.

**What is still synthetic:** the mandates, the carts and the violation
labels. No public corpus of agent-initiated purchase disputes exists — that is
the honest ceiling here, not an oversight. See DECISIONS.md D-002.

`data/raw/` is not committed. The repo carries the loader and the mapping rules;
the sources are third-party scrapes redistributed under licences their uploaders
could not grant (D-011).

---

## Run it

    make setup
    make dataset SEED=1337     # catalog + labelled pairs
    make baseline              # the AP2 reference check, and K1
    make test                  # 99 tests
    make report                # mapping coverage and composition
    make sample                # eyeball the catalog

On Windows without GNU make, `.\make.ps1 <target>` mirrors the same targets.

`make eval` arrives with Milestone 4.

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
6. Generated violations are unambiguous by construction, so they cannot measure
   how the system handles genuine ambiguity. That is what the 40 hand-written
   adversarial near-misses are for — L-008, not yet written.

---

## Reading

[DECISIONS.md](DECISIONS.md) — 27 decisions with reasons, the kill criteria set
on day one and how K1 was tested, the open problems found in the design docs
(three now resolved), and eight measured limitations of what's built.
