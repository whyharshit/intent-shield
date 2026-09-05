# Warrant — Intent Conformance for Agent Purchases

**Razorpay AI Buildathon submission — Track 02, AI Risk Manager**

---

## The one-paragraph version

When an AI agent buys on your behalf, the payment industry has built cryptography to prove the *authorization document* wasn't tampered with. Nobody built the thing that checks whether the *purchase actually matches what the human asked for*. The open implementations check two things — is the amount within the cap, is the merchant allowed. So a mandate saying "groceries, under ₹2,000, weekly" will happily approve ₹1,900 of premium whisky. Every signature verifies. The customer disputes it, and the merchant has a perfect cryptographic proof of the wrong thing. Warrant is the missing check: given a signed natural-language intent and a proposed cart, decide whether the cart honours the intent, with calibrated confidence and three outcomes — allow, refuse, escalate to the human.

---

## Why this survives competitive scrutiny

| Layer | Who owns it | Status |
|---|---|---|
| Agent identity — *is this agent real?* | Visa TAP, Mastercard Agentic Tokens, Skyfire KYAPay, Nekuda, Prava | Built |
| Agent behaviour — *is this agent behaving badly?* | HUMAN AgenticTrust, Forter Identity Monitoring, Riskified | Built |
| Consent format — *what did the user sign?* | Google AP2 (Intent / Cart / Payment Mandates, W3C VCs) | Specified |
| Consent storage — *where is it kept?* | PayPal (roadmap), Tenzro, open MCP implementations | Being built |
| **Conformance — *does this cart honour the intent?*** | **Nobody** | **Open** |

The last row is a language and reasoning problem sitting between security teams and ML teams. Neither discipline owns it. That's why it's still open.

Second gap: everything above is card-rail shaped. India runs on UPI, NPCI's protocol deliberately won't hold this evidence, and nothing maps mandates onto UPI Circle delegation, Reserve Pay, AFA re-registration or the RBI pre-debit notification window.

---

## The document set

| File | What's in it | Read it when |
|---|---|---|
| **01-problem-and-thesis.md** | The problem, the landscape, why Track 02, the competitive teardown | First. This is the argument. |
| **02-product-spec.md** | What Warrant is, its components, the decision policy, the India layer | Before you write any code |
| **03-technical-design.md** | Architecture, data model, algorithms, stack, API surface | When you start building |
| **04-dataset-and-evaluation.md** | Violation taxonomy, synthetic data generation, labelling, metrics, calibration | Build this **first**, before the system |
| **05-roadmap.md** | Day-by-day plan, 21-day and compressed 10-day versions | Planning your weeks |
| **06-submission-kit.md** | Repo structure, README template, 5-minute video script, architecture diagram | Final week |
| **07-risks-and-faq.md** | Every hard question a panel will ask, with answers | Before the panel |

---

## The single rule that governs the build

**Deterministic first, model last.**

Amount caps, expiry, frequency, merchant allow-lists — these are joins and comparisons. Never send them to a language model. The model exists for one job: deciding whether a basket of items honours a sentence a human wrote. If your architecture diagram shows the LLM deciding anything a rule could have decided, you've built a demo, not a system.

---

## The thirty seconds that win it

Intent: *"groceries, under ₹2,000, weekly."*
Cart: **₹1,900 of premium whisky.**

Amount check passes. Merchant allow-list passes. Signature verifies.

Every shipping implementation approves this. Yours refuses and escalates to the human.

Show both, side by side, in the first ninety seconds of the video.

---

## Status checklist

- [ ] Read 01 and agree with the thesis
- [ ] Build the dataset generator (04) — **this comes before any product code**
- [ ] Hand-label the gold set
- [ ] Deterministic checker passing on hard constraints
- [ ] Semantic checker producing structured verdicts
- [ ] Calibration fitted on validation split
- [ ] Cost-optimal threshold derived, not guessed
- [ ] Evidence chain and audit log
- [ ] Streamlit review UI
- [ ] Full eval report generated from a single command
- [ ] Video recorded
- [ ] Repo public, README complete, one-command reproduction
