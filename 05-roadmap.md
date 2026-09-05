# 05 — Roadmap

Two plans. **21 days** if you have three weeks. **10 days** if the deadline is tight. Pick one now and don't blend them.

---

## Sequencing principle

```
dataset  →  baseline  →  rules  →  categories  →  LLM  →  calibration  →  UI  →  video
```

Never out of order. Two reasons:

- The dataset defines correctness. Build it after the system and you'll shape it to fit.
- The baseline defines your claim. If you don't have it running by day 4, you don't yet know whether your project is worth doing.

**Hard rule: if the baseline turns out to catch most violations, stop and reconsider the project.** It shouldn't — it checks amount and merchant only — but verify it rather than assuming.

---

## 21-day plan

### Week 1 — Prove the gap is real

**Day 1 — Ground the claim**
- Re-read the Track 02 brief. Copy the exact wording into your README.
- Read the AP2 spec: Intent / Cart / Payment Mandate structure, W3C VC format.
- Read Tenzro's `ap2ValidateMandatePair` signature. Screenshot `total_within_intent` and `merchant_allowed`. **This screenshot goes in your video.**
- Write a one-page problem statement in your own words. If you can't, you don't understand it yet.

**Day 2–3 — Catalog and taxonomy**
- Build `categories.yaml`: ~12 roots, ~60 leaves, Indian retail.
- Build `catalog.py`: ~800 SKUs with title, category, attributes, price band. Grocery, personal care, apparel, footwear, electronics, alcohol, pharma, restaurant.
- Eyeball it. A fake-looking catalog makes the whole demo look fake.

**Day 4 — Intents and conforming carts**
- ~30 intent templates with parameter sampling, deliberately varying in specificity.
- Conforming cart synthesis from an intent.
- Sanity check by hand: do these read like something a person would say?

**Day 5 — Violation injectors**
- All twelve injectors from the taxonomy.
- `make_dataset.py` producing train/val/test splits **by mandate**.
- Generate the first full dataset.

**Day 6 — The baseline**
- Implement `total_within_intent + merchant_allowed`.
- Run it on the test set. Record the numbers.
- **Checkpoint:** the baseline should catch V1 and V7 and nothing else. If it catches much more, your dataset is too easy — go make it harder before continuing.

**Day 7 — Adversarial set and gold labels**
- Hand-write the 40 near-misses. Do this *before* building the checker, so you're not writing tests you already know you pass.
- Hand-label 150 pairs without looking at generator labels. Compute disagreement.

*End of week 1: you have a dataset, a baseline, a measured gap, and evidence your labels are sound. If the gap isn't there, you've lost a week instead of three.*

---

### Week 2 — Build the system

**Day 8 — Mandate ingest**
- ES256 sign/verify, expiry, revocation.
- `AP2Adapter`, `RawIntentAdapter`, stub `UAPAdapter`.
- Test harness that mints signed test mandates.
- Hard-stop path on invalid signature.

**Day 9 — Constraint extraction**
- LLM → Pydantic, temperature 0, retry once on schema failure.
- `ambiguous_terms` handling — the instruction to flag rather than guess.
- Measure extraction accuracy against generator ground truth on 100 intents. **Report this separately** — extraction errors poison everything downstream, and a reviewer will ask.

**Day 10 — Deterministic checker**
- All seven rule checks.
- Run on test set. You should now match or beat the baseline using rules alone.
- Record what fraction resolves here. This number matters: it shows the LLM isn't doing work a comparison could do.

**Day 11 — Category mapping**
- Precompute category centroids with sentence-transformers.
- Cosine match + keyword fallback + `unknown` → escalate.
- **The whisky case should now pass.** Screenshot it.
- Measure category assignment accuracy separately.

**Day 12–13 — Semantic attribute checker**
- Per-constraint verdicts: `satisfied | violated | not_determinable`.
- Structured output, schema-forced, delimited data block for cart content.
- Prompt injection defence + the injection test case.
- Iterate prompts **on train split only**. Do not look at test.

**Day 14 — Integration**
- Full pipeline end to end.
- FastAPI routes.
- Latency instrumentation by path.
- First full run on validation.

*End of week 2: the system works. You have not yet touched the test set.*

---

### Week 3 — Make it credible, then make it visible

**Day 15 — Calibration**
- Isotonic regression on validation.
- Reliability diagram before/after. ECE.
- **Do not fit on test.**

**Day 16 — Decision policy**
- Cost model with defaults.
- Expected-cost argmin.
- Cost curve plot, operating point marked.
- Sensitivity analysis across `p_dispute`, `friction_cost`, `margin`.

**Day 17 — Evidence and audit**
- Hash-chained decision log.
- `verify_chain()` plus a test that mutates a record and asserts detection.
- Dispute evidence packet generator.

**Day 18 — India rails layer**
- AFA step-up above ₹15,000.
- Pre-debit notification carrying the conformance verdict.
- UPI Circle delegation cap mapping, Reserve Pay reservation.
- CERT-In-shaped threshold above which `ALLOW` is disabled entirely.
- These can be well-designed interfaces with clear stubs — say so honestly rather than faking live integration.

**Day 19 — Streamlit UI**
- Escalation review queue.
- Decision inspector: every check, why, what decided it.
- Side-by-side baseline vs. Warrant on a chosen case.
- Human resolution writing back to the log.

**Day 20 — The sealed test run**
- Run on test **once**.
- Generate `eval/REPORT.md` with all eleven sections.
- Write the known-failure-modes section yourself, honestly.
- Freeze. Do not tune after seeing test numbers. If you do, say so in the report.

**Day 21 — Video and submission**
- Record per the script in `06-submission-kit.md`.
- Public repo, README complete, `make eval` verified on a clean clone.
- Submit.

---

## 10-day compressed plan

Cut scope, never rigour. The metrics are the submission.

| Day | Do | Cut |
|---|---|---|
| 1 | Taxonomy + 300-SKU catalog + 12 intent templates | Full 800-SKU catalog |
| 2 | Violation injectors (V1–V4, V7, V8, V10 only) + splits | V5, V6, V9, V11, V12 |
| 3 | Baseline + 20 adversarial cases + 60 gold labels | 40 cases, 150 labels |
| 4 | Mandate ingest + constraint extraction | Multiple adapters — AP2 only |
| 5 | Deterministic checker | — |
| 6 | Category mapping — **whisky case working** | — |
| 7 | Semantic attribute checker | — |
| 8 | Calibration + cost policy + evidence log | Sensitivity analysis |
| 9 | Minimal Streamlit + sealed test run + report | Full review queue |
| 10 | Video + submit | — |

**Non-negotiables even at 10 days:** the baseline comparison, calibration, false-positive cost in rupees, the full escalation list, and the whisky demo. Drop the India rails layer to a design section in the README before you drop any of those.

---

## Daily discipline

- **Commit every day.** A public repo with 21 real commits reads very differently from one with three.
- **Keep a `DECISIONS.md`.** One line per non-obvious choice and why. This becomes your panel prep.
- **Never look at the test set.** Write it down as a rule and hold to it.
- **Timebox prompt iteration.** Two days maximum. If per-constraint accuracy stalls, the fix is usually the constraint schema or the taxonomy, not the prompt.

---

## Kill criteria — decide in advance

Stop and switch projects if:

- **Day 6:** the baseline catches most violations. The gap isn't real, or your data is too easy.
- **Day 11:** category mapping accuracy is below ~80%. The whisky case is your headline; if it's fragile, the demo collapses.
- **Day 14:** the deterministic path resolves under 40% of cases. Every transaction hitting an LLM means unusable latency and cost, and reviewers will say so.

Writing kill criteria before you start is itself a signal of engineering maturity. Put them in `DECISIONS.md` and reference them in the panel.

---

## What to do with slack time

In priority order, if you're ahead:

1. **More adversarial cases.** Highest return per hour.
2. **A second LLM provider** behind the interface, with agreement rate reported. Cheap robustness evidence.
3. **A realistic-distribution rerun** — 95% conforming — reported as a secondary result.
4. **A short ablation:** rules only, rules + categories, full system. Three rows showing what each layer buys.

Not: more UI, more features, more integrations.
