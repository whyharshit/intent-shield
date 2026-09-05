# 02 — Product Specification

---

## 1. What Warrant is

A verification service that sits between an AI agent and a payment, answering one question:

> **Does this cart honour the intent the customer signed?**

Input: a signed Intent Mandate (natural language + structured constraints) and a proposed cart.
Output: a verdict — `ALLOW`, `REFUSE`, or `ESCALATE` — with a calibrated confidence, a per-constraint breakdown, a plain-English explanation, and an audit record.

It is **not** a consent ledger (AP2 defines that), **not** an agent identity system (Visa TAP, Skyfire, Nekuda do that), **not** bot detection (HUMAN, Kasada, DataDome do that). It is the conformance check that sits after identity is established and before money moves.

---

## 2. Scope boundaries — write these in the README

**In scope**
- Verifying a cart against a signed intent
- Extracting checkable constraints from natural language
- Calibrated three-way decisions with an explicit cost model
- Tamper-evident decision log usable as dispute evidence
- Mapping escalation onto Indian payment rails

**Out of scope**
- Issuing or signing mandates (we consume AP2-shaped mandates; a test harness produces them)
- Agent identity verification (assumed upstream)
- Fraud detection, bot detection, card testing
- Actually moving money
- Being a payment gateway

Stating what you don't do is how you avoid being judged for not doing it.

---

## 3. The five components

### C1 — Mandate ingest and verification
Accepts AP2-shaped Intent Mandates as W3C-VC-style JSON, signed ES256. Verifies the signature, checks expiry, checks revocation. If the signature fails, everything stops — this is a hard gate, no model involved.

Also accepts a **degraded mode**: an unsigned intent object, for merchants not yet on AP2. Warrant still works; the evidence is weaker and the output says so.

### C2 — Constraint extraction
Turns the natural-language intent into a typed constraint set.

```
"groceries for the week, under ₹2,000, nothing alcoholic,
 prefer Indian brands, deliver by Friday"

  ↓

hard:
  amount_max: 200000          # paise
  frequency: weekly
  deliver_by: <date>
  categories_allowed: [grocery, produce, staples, household]
  categories_denied: [alcohol, tobacco]
soft:
  brand_preference: "Indian brands"
  ambiguous_terms: ["for the week"]
```

An LLM does the extraction, but the output is validated against a Pydantic schema. Anything that doesn't parse is a hard failure, not a best guess. Extraction happens **once at mandate creation**, is cached and signed alongside the mandate — never re-run per transaction. It's not in the hot path.

### C3 — Deterministic checker
Everything expressible as arithmetic or set membership:

| Check | Logic |
|---|---|
| Amount ceiling | `cart.total <= intent.amount_max` |
| Mandate validity | `now < intent.expires_at` and not revoked |
| Frequency | count of prior approvals in window vs. cap |
| Merchant scope | merchant ID in allow-list, or category in allowed set |
| Denied category | no line item maps to a denied category |
| Delivery window | promised delivery ≤ `deliver_by` |
| Cumulative spend | running total across the mandate's lifetime |

Fast, free, fully explainable, and it should resolve the large majority of decisions. **Never send these to a model.**

### C4 — Semantic conformance checker
Runs only on what C3 couldn't settle. Two stages:

**Stage 1 — retrieval and mapping.** Each line item is mapped to a category taxonomy using embeddings plus a lookup table. This catches the whisky case cheaply: *premium whisky* → `alcohol` → in `categories_denied` → refuse, without an LLM call.

**Stage 2 — attribute and preference reasoning.** For what remains: does *size 9 black dress shoes* honour *"size 10, white or grey, running shoes"*? Does a substituted item honour the original request? Is *"prefer Indian brands"* violated?

The model returns a structured verdict, never prose:

```json
{
  "verdict": "violates",
  "violated_constraints": ["attribute:size", "attribute:colour", "category:footwear_type"],
  "confidence": 0.91,
  "reasoning": "Intent specified size 10 running shoes in white or grey. Cart contains size 9 black dress shoes.",
  "evidence_line_items": ["line_001"]
}
```

Schema-validated. Unparseable output is treated as `uncertain`, which routes to escalation — a failure to parse must never become a silent approval.

### C5 — Decision policy
Takes the deterministic result, the semantic verdict and the calibrated confidence, and picks one of three actions using an **expected-cost calculation, not a hand-picked threshold**. Detailed in section 5.

---

## 4. The three outcomes

| Verdict | Meaning | What happens |
|---|---|---|
| `ALLOW` | Cart conforms; confidence high | Payment proceeds. Decision logged. |
| `REFUSE` | Cart clearly violates a hard constraint | Payment blocked. Agent gets a structured reason it can act on (re-plan, or re-prompt the user). |
| `ESCALATE` | Genuinely uncertain, or a soft-constraint violation with real money at stake | Human is asked. On Indian rails this maps to an AFA step-up or a push notification. |

**Escalation is the product, not a failure mode.** A system that never escalates is guessing. Report the escalation rate as a headline metric and defend it with the cost model.

---

## 5. The decision policy — cost, not vibes

Three errors, three very different costs.

Let:
- `V` = cart value
- `m` = merchant gross margin
- `p_d` = probability this becomes a dispute if wrongly approved
- `C_cb` = chargeback handling cost + scheme fee
- `R` = ratio damage — the amortised cost of one more dispute against the VAMP 1.5% threshold
- `f` = friction cost of an escalation (customer annoyance + drop-off risk)

**Cost of wrongly approving a violating cart:**
`p_d × (V + C_cb + R)`

**Cost of wrongly refusing a conforming cart:**
`V × m` (lost margin) `+ churn_risk`

**Cost of escalating:**
`f` — small, roughly fixed, and much smaller than either error above.

Given calibrated `P(violates) = p`, expected costs are:

```
E[allow]    = p × (p_d × (V + C_cb + R))
E[refuse]   = (1 - p) × (V × m + churn_risk)
E[escalate] = f
```

Pick the minimum. This produces two thresholds naturally, and both **move with cart value** — which is correct behaviour. A ₹200 grocery cart should rarely escalate; a ₹40,000 electronics cart should escalate at much lower uncertainty.

**Show this curve in the video.** Threshold-by-derivation rather than threshold-by-feel is the difference between an engineering project and a demo.

---

## 6. Evidence and audit

Every decision writes an immutable record:

```json
{
  "decision_id": "...",
  "mandate_id": "...",
  "mandate_hash": "...",
  "cart_hash": "...",
  "verdict": "REFUSE",
  "confidence": 0.91,
  "checks": [
    {"check": "amount_ceiling", "result": "pass", "decided_by": "rule"},
    {"check": "category_denied", "result": "fail", "decided_by": "rule",
     "detail": "line_002 → alcohol ∈ denied"},
    {"check": "attribute_match", "result": "n/a", "decided_by": "skipped"}
  ],
  "explanation": "The mandate excludes alcohol. Line item 2 is whisky.",
  "escalated_to_human": false,
  "human_override": null,
  "timestamp": "...",
  "prev_hash": "...",
  "record_hash": "..."
}
```

`prev_hash` chains records so the log is tamper-evident without a blockchain. Anyone can recompute the chain and detect an edit.

**Why this matters for disputes:** the merchant can now produce not just "the signature was valid" but "here is the check we ran before the money moved, here is what it found, and here is why we allowed it." That's the difference between proving the plumbing worked and proving the purchase was in scope.

---

## 7. The India rails layer

This is what makes it Razorpay's problem rather than a generic one. Escalation has to land somewhere real.

| Situation | UPI-native response |
|---|---|
| Escalate below AFA threshold | Push notification with cart summary, one-tap approve/reject; mandate debit held |
| Escalate above ₹15,000 | AFA step-up — UPI PIN re-authentication, since RBI requires it above that ceiling anyway |
| Recurring agent spend | Map the mandate onto **UPI Circle** delegated authority; the mandate's cumulative cap becomes the delegation limit |
| Pre-funding an agent's budget | **Reserve Pay** blocks funds for multiple debits, so an approved intent has money reserved against it |
| Pre-debit notification | RBI requires notification at least 24 hours before a debit — Warrant's conformance verdict rides along in that notification, so the customer sees *what* is about to be bought, not just *that* something is |
| High-value autonomy | **CERT-In-shaped** human-in-the-loop threshold: above a configurable amount, `ALLOW` is disabled entirely and the only outcomes are `REFUSE` or `ESCALATE` |
| Data minimisation | **DPDP** purpose-limitation: constraint extraction keeps only the constraints, discards the conversational context it came from, and logs what it discarded |

**Design note.** UAP's spec isn't public. Model the mandate internally in your own schema and write thin adapters — `AP2Adapter`, `UAPAdapter`, `RawIntentAdapter`. When the spec lands, you change a mapping file, not the engine. Say this out loud; it shows you understood the risk rather than ignored it.

---

## 8. What "good" looks like at demo time

- A 500-pair batch runs end to end in one command
- Precision, recall, false-positive cost in rupees, calibration error, escalation rate, and a **per-violation-type breakdown** — because an overall F1 hides that you're catching amount violations and missing attribute violations
- The whisky case and the size-9-black-shoes case both refused, side by side with a baseline that approves both
- One near-miss where Warrant escalates instead of deciding, and the human resolves it
- The full exception list printed, unedited
- Latency numbers, because it sits in the payment path
