# 04 — Dataset and Evaluation

**Build this before you build the product.** The dataset defines what "working" means. If you build the system first, you will unconsciously design the data to flatter it — and a reviewer will smell that immediately.

---

## 1. The honesty problem, stated up front

You are generating your own test data and grading yourself on it. That is a legitimate criticism and the track explicitly warns against it: *one cherry-picked match proves nothing.*

Four defences, all of which you should implement:

1. **Ship the generator in the repo.** A reviewer regenerates with a different seed and re-runs your numbers. If they hold, the result is real.
2. **Hand-label a gold set you did not generate the labels for.** Generate cart/intent pairs *without* violation labels, label them by hand, and only then check against the generator's ground truth. Report the disagreement rate — that's your label noise estimate, and publishing it is more convincing than claiming perfection.
3. **Include adversarial near-misses you did not design your system to catch.** Write them before you write the checker.
4. **Report per-violation-type results.** An aggregate F1 hides that you nail amount violations and miss attribute violations. Breaking it down invites the criticism, which is why it disarms it.

---

## 2. Violation taxonomy

Twelve types. Each needs its own generator and its own row in the results table.

| # | Type | Example | Caught by |
|---|---|---|---|
| V1 | `AMOUNT_EXCEEDED` | ₹2,400 cart against a ₹2,000 cap | Rule |
| V2 | `CATEGORY_DENIED` | Whisky against "nothing alcoholic" | Category map |
| V3 | `CATEGORY_OUT_OF_SCOPE` | Electronics against "groceries" | Category map |
| V4 | `ATTRIBUTE_MISMATCH` | Size 9 black against "size 10, white or grey" | LLM |
| V5 | `BRAND_EXCLUSION` | Excluded brand appears in cart | LLM |
| V6 | `QUANTITY_ANOMALY` | 40 kg rice on a weekly household grocery mandate | LLM + heuristic |
| V7 | `MERCHANT_OUT_OF_SCOPE` | Merchant not in allow-list | Rule |
| V8 | `MANDATE_EXPIRED` | Purchase after expiry | Rule |
| V9 | `FREQUENCY_EXCEEDED` | 4th weekly order in one week | Rule |
| V10 | `UNAUTHORIZED_SUBSTITUTION` | Out of stock → materially different item | LLM |
| V11 | `ADD_ON_CREEP` | Express shipping, warranty, insurance not requested | LLM + rule |
| V12 | `TIMING_VIOLATION` | Delivery after the stated deadline | Rule |

**Deliberate design point:** V1, V7, V8, V9, V12 are rule-catchable. V2, V3 need only the category map. Only V4, V5, V6, V10, V11 genuinely need a language model. Your results table should make that split visible — it proves you didn't reach for an LLM where a comparison would do.

---

## 3. Adversarial near-misses

These are the cases that separate a real system from a demo. Write at least 40, by hand, before building the checker.

| Case | Why it's hard |
|---|---|
| ₹1,900 whisky vs. "groceries under ₹2,000" | Amount passes. Category is the only signal. **The headline case.** |
| ₹1,999 vs. ₹2,000 cap, fully conforming | Must **allow**. A system that gets nervous near the ceiling is useless. |
| Cooking wine on a "no alcohol" grocery mandate | Genuinely ambiguous. Correct answer is **escalate**, not refuse. |
| "Size 10" shoes, cart says "UK 10" vs "US 10" | Unit ambiguity. Escalate. |
| Substitution: Amul milk → Nandini milk, same price | Conforming. Refusing this is a false positive that would kill adoption. |
| Substitution: whole milk → almond milk | Materially different. Violates. |
| "Premium" tea at ₹80 vs ₹400 | Quality term, subjective. Escalate. |
| Cart total under cap, but shipping pushes it over | Rule must check the right total. |
| Mandate says "weekly", cart placed on day 6 | Conforming. Off-by-one traps. |
| Prompt injection in a product title | Must not change the verdict. |
| Empty cart | Degenerate input. Must not crash. |
| Single item at exactly ₹0 | Free sample or an error? Escalate. |
| Regional language item name ("तूर दाल") | Category mapping must not fail open. |
| 200-line-item cart | Latency and aggregation correctness. |

For each, record the *expected* verdict including whether the correct answer is `ESCALATE`. **An escalation on a genuinely ambiguous case is a success, not a miss.** Score it that way and say so.

---

## 4. Generator design

```
data/generator/
├── catalog.py      # ~800 Indian SKUs: title, category, attributes, price band
├── intents.py      # intent templates × parameter sampling
├── carts.py        # conforming cart synthesis
├── violations.py   # one injector per violation type
└── make_dataset.py # assembles, splits, writes JSONL
```

**Catalog.** Build ~800 realistic Indian retail SKUs across the taxonomy, with attributes (size, colour, brand, pack size) and realistic price bands. Grocery, personal care, apparel, footwear, electronics, alcohol, pharma. Do this by hand or with LLM assistance, then eyeball it — a catalog full of "Product 1, Product 2" will make the whole demo look fake.

**Intent templates.** ~30 templates spanning: recurring groceries, one-off purchase with attributes, gift with budget, restock with brand preference, travel booking with constraints, bill payment. Vary specificity deliberately — some intents should be vague, because vague intents *should* produce more escalations, and showing that relationship is a good result.

**Split.** 60/20/20 train/validation/test by *mandate*, not by cart, so carts from the same mandate never straddle a split. Calibration fits on validation only. Test set stays sealed until the final run.

**Target sizes.**

| Split | Pairs | Purpose |
|---|---|---|
| Train | ~1,200 | Prompt iteration, taxonomy tuning |
| Validation | ~400 | Calibration fitting, threshold derivation |
| Test | ~400 | Reported numbers. Run once. |
| Gold (hand-labelled) | 150 | Label-noise estimate |
| Adversarial | 40 | Named cases, reported individually |

Class balance: roughly 55% conforming, 45% violating. Real traffic would be far more skewed toward conforming — say so, and report on a reweighted realistic distribution as a secondary result.

---

## 5. Metrics

### Primary

| Metric | Definition | Why |
|---|---|---|
| **Violation recall** | violations correctly refused or escalated ÷ all violations | Missing a violation is the loss you're preventing |
| **Violation precision** | true violations ÷ all things flagged | Flagging good carts destroys adoption |
| **False-positive cost (₹)** | conforming carts refused × mean cart value × margin | The number that decides whether a merchant switches it on |
| **Escalation rate** | escalations ÷ total | Too high = useless. Too low = guessing. |
| **ECE** | expected calibration error post-isotonic | Does 0.8 mean 0.8? |

### Secondary

- Per-violation-type recall (the twelve rows)
- Rule-resolved vs. model-resolved split
- Latency p50 / p95 by path
- Cost per 1,000 verifications
- Adversarial case table, all 40, pass/fail individually
- Label disagreement rate on the gold set
- Sensitivity of thresholds to cost-model parameters

### The baseline you must beat

Implement `total_within_intent + merchant_allowed` — literally the check the open AP2 implementations perform. Run it on the same test set. Report both.

Expected result: the baseline catches V1 and V7 and nothing else. Your table showing it approving whisky, wrong-size shoes, unauthorized substitutions and add-on creep **is the single most persuasive artifact in your entire submission.** It's not a strawman — it's the state of the art, and you can cite the implementation.

---

## 6. Report format

`make eval` writes `eval/REPORT.md` containing:

1. Dataset composition table
2. Headline metrics with 95% bootstrap confidence intervals
3. Per-violation-type breakdown
4. **Baseline comparison table**
5. Reliability diagram, before and after calibration
6. Cost curve — expected cost vs. threshold, with the chosen operating point marked
7. Sensitivity analysis on cost parameters
8. All 40 adversarial cases, individually, with verdict and expected verdict
9. **Full escalation list, unedited** — every case the system refused to decide
10. Latency distribution
11. Known failure modes, written by you

Point 9 is not optional. The track says *"honest metrics including false-positive cost"* and *"one cherry-picked match proves nothing."* Printing every case you couldn't handle is how you answer both.

---

## 7. Reproducibility contract

Put this in the README:

```bash
git clone <repo> && cd warrant
make setup
make dataset SEED=1337     # regenerate from scratch
make eval                  # rewrites eval/REPORT.md
```

Then: *"Change the seed. The numbers should move by less than X%. If they don't, the result isn't real and I'd want to know."*

Inviting falsification is a stronger claim than any metric.
