# 06 — Submission Kit

The buildathon asks for four things: a public repo, a 5-minute pitch video, the architecture, and evidence of signal. This file is the template for all four.

---

## 1. The five-minute video script

Timing is tight. Rehearse it. The single most common failure is spending three minutes explaining agentic commerce and thirty seconds on the actual work.

### 0:00–0:35 — The loss

> "When an AI agent buys something for you and you later dispute it, the merchant has almost nothing to defend itself with. The IP address, the device fingerprint, the click path — all of that belonged to a machine, not to you. So merchants lose these disputes by default. And every dispute counts against their ratio, where Visa's threshold tightened to 1.5% in April."

No jargon. No "in today's rapidly evolving landscape." Start with money being lost.

### 0:35–1:30 — The gap, with the receipt

> "The industry's answer is signed mandates. Google's AP2 has the user sign an intent — 'running shoes, size 10, under $150, white or grey' — and everything is cryptographically verifiable.
>
> But look at what the reference implementations actually check."

**Show the screenshot of `ap2ValidateMandatePair` returning `total_within_intent` and `merchant_allowed`.**

> "Amount, and merchant allow-list. That's it.
>
> So here's a mandate that says 'groceries, under two thousand rupees, weekly.'"

**Live: submit ₹1,900 of premium whisky to the baseline.**

> "Amount passes. Merchant passes. Signature verifies perfectly. Approved.
>
> The merchant now has flawless cryptographic proof of the wrong purchase. Cryptography proves the mandate wasn't altered. It doesn't prove the cart honours the intent. That's what I built."

**Same cart, Warrant. Refused, with the reason.**

That's the whole pitch, delivered by minute 1:30. Everything after is evidence.

### 1:30–2:15 — Architecture

Show one diagram. Walk it in four sentences:

> "Signature check first — hard gate, no model. Then deterministic rules: amount, expiry, frequency, merchant, denied categories. That resolves [X]% of cases with no model at all. What's left goes to category mapping via embeddings — that's what catches the whisky. Only what survives that reaches a language model, and it returns a per-constraint verdict, never prose.
>
> The model writes explanations and judges attributes. The rules and the solver decide. That inversion is deliberate."

### 2:15–3:30 — Numbers

Put the table on screen. Read only the three that matter.

> "Test set: 400 held-out pairs, sealed until the final run.
>
> Violation recall [X]%. Precision [Y]%. And the number I care about most — false-positive cost: [₹Z] per thousand transactions, which is legitimate purchases I wrongly blocked. That's the number that decides whether a merchant would ever switch this on, so it's the one I'd want you to interrogate.
>
> Against the baseline: it catches amount and merchant violations. It misses wrong-size items, unauthorized substitutions, add-on creep, and whisky.
>
> Calibrated with isotonic regression on validation only. When it says 80% confident, it's right [N]% of the time."

### 3:30–4:15 — The failure, handled

> "Here's a case it refuses to decide."

**Show the cooking wine on a no-alcohol grocery mandate.**

> "Genuinely ambiguous. It escalates instead of guessing, and on Indian rails that escalation becomes an AFA step-up, which RBI requires above ₹15,000 anyway.
>
> [X]% of cases escalate. That's the cost of not guessing, and the cost model derives the threshold rather than me picking one. Here's the curve."

### 4:15–5:00 — What it can't do

> "Three honest limits.
>
> The data is synthetic — no public corpus of agent disputes exists. The generator is in the repo; change the seed and re-run.
>
> Agent volume is small today. Signifyd saw agent-referral orders up twelve-hundred percent year over year, but on a small base. This is built ahead of the curve.
>
> And I'm not claiming this space is empty. HUMAN's AgenticTrust and Riskified's guarantee are real, shipped products. They answer 'is this agent legitimate.' I answer 'is this purchase what the human asked for.' Different question. Still open."

Ending on limitations reads as confidence, not weakness. Most submissions end on a feature list.

---

## 2. README template

```markdown
# Warrant — Intent Conformance for Agent Purchases

**Razorpay AI Buildathon · Track 02, AI Risk Manager**

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
"groceries, under ₹2,000, weekly" approves ₹1,900 of premium whisky, with a
perfect signature chain.

Warrant is the missing check.

## What it does

Given a signed intent and a proposed cart, returns ALLOW / REFUSE / ESCALATE
with a calibrated probability, a per-constraint breakdown, a plain-English
explanation, and a tamper-evident audit record.

## Results (held-out test set, n=400, run once)

| Metric | Warrant | Baseline (`total_within_intent` + `merchant_allowed`) |
|---|---|---|
| Violation recall | | |
| Violation precision | | |
| False-positive cost per 1,000 txns | | |
| Escalation rate | | n/a |
| ECE (post-calibration) | | n/a |
| p95 latency | | |

Per-violation-type breakdown, all 40 adversarial cases, the full unedited
escalation list, and known failure modes: [eval/REPORT.md](eval/REPORT.md)

## Reproduce

    make setup
    make dataset SEED=1337
    make eval

Change the seed. The numbers should move by less than 3%. If they don't,
the result isn't real and I'd want to know.

## Architecture

[diagram]

Deterministic first, model last. Signature verification is a hard gate. Rules
resolve [X]% with no model call. Category mapping via embeddings resolves
another [Y]%. Only the remainder reaches a language model, which returns
per-constraint verdicts, never prose — it explains and judges attributes; it
never decides anything a comparison could decide.

## Scope

**In:** verifying carts against signed intents; constraint extraction;
calibrated three-way decisions; tamper-evident decision log; mapping
escalation onto Indian payment rails.

**Out:** issuing mandates, agent identity verification, bot detection, fraud
scoring, moving money. Those layers exist — Visa TAP, Skyfire, HUMAN
AgenticTrust, Forter, Riskified. Warrant sits after identity and before money.

## Honest limitations

1. Synthetic data. No public corpus of agent-initiated disputes exists.
   Generator included; regenerate and re-run.
2. Small market today. Signifyd's network saw agent-referral orders up 1,247%
   YoY as of Oct 2025 — a large multiple on a small base.
3. NPCI's UAP spec is unpublished. The India layer is built against announced
   mechanics behind an adapter interface.
4. The India rails integrations are designed interfaces with stubs, not live
   integrations.
5. Extraction errors propagate. Extraction accuracy reported separately in
   eval/REPORT.md.

## Decisions log

[DECISIONS.md](DECISIONS.md) — every non-obvious choice and why, including the
kill criteria I set before starting.
```

---

## 3. Architecture diagram

One diagram, not five. It must communicate the inversion — cheap and deterministic first, expensive and probabilistic last — at a glance.

Requirements:
- Vertical flow, top to bottom
- **Annotate each stage with the % of traffic it resolves** — this is what makes the diagram argue rather than describe
- Colour-code: rules one colour, embeddings another, LLM a third. The LLM colour should be visibly the smallest region.
- Show the hard-stop path on signature failure branching out early
- Show all three outcomes, with escalation feeding the India rails box

A reviewer who looks only at your diagram should come away thinking *"this person didn't just wrap an LLM around a problem."*

---

## 4. Application form answers

The form is short. Density matters.

**What did you build?**
> A verifier that checks whether an AI agent's cart honours the intent its user actually signed. AP2-style mandates are cryptographically verifiable, but the reference implementations only check amount and merchant allow-list — so "groceries under ₹2,000" approves ₹1,900 of whisky with a valid signature. Warrant closes that gap: calibrated ALLOW/REFUSE/ESCALATE, per-constraint reasoning, tamper-evident audit log, mapped onto UPI rails.

**What's the evidence it works?**
> 400 held-out pairs, sealed until the final run. Violation recall [X]%, precision [Y]%, false-positive cost [₹Z] per 1,000 transactions, ECE [E] after isotonic calibration. Benchmarked against the actual open-source AP2 check. Per-violation-type breakdown, 40 named adversarial cases, and the full unedited escalation list in the repo. Reproducible with `make eval` from a clean clone.

**Why does this matter to Razorpay?**
> Razorpay, Cashfree and PayU all shipped LLM-native UPI payments in February. NPCI's UAP arrives with liability provisions, and NPCI deliberately won't hold this evidence — its role stops at confirming a request is genuine; it never sees what was bought. So the conformance record has to live at the PSP or the merchant. Nothing in the Indian market does this today.

---

## 5. Panel preparation

Bring three artifacts:

1. **`DECISIONS.md`** — every non-obvious choice, why, and the kill criteria you set on day one. Being able to say *"I decided in advance that if the baseline caught most violations I'd abandon this"* is worth more than any metric.
2. **The failure list** — know your worst violation type and why it's worst. Volunteer it before they find it.
3. **The one thing you'd build next** — and it should be small and specific. "Active learning on human escalation resolutions, so the constraint taxonomy improves from real corrections" is a good answer. "More integrations" is not.

---

## 6. Pre-submission checklist

- [ ] Repo public, clean clone tested on a different machine
- [ ] `make setup && make dataset && make eval` works from scratch
- [ ] No API keys committed; `.env.example` present
- [ ] `eval/REPORT.md` regenerated from the sealed test run
- [ ] Full escalation list present and unedited
- [ ] Baseline comparison table present
- [ ] Known limitations section written honestly
- [ ] `DECISIONS.md` written
- [ ] Video under 5:00, whisky demo before 1:30
- [ ] Architecture diagram shows traffic % per stage
- [ ] Track 02 named explicitly, with Track 01's bar quoted in the README
- [ ] Prompt-injection test case visible in the test suite
