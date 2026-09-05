# 01 — Problem and Thesis

---

## 1. The loss being prevented

A merchant accepts an order placed by a customer's AI agent. Weeks later the customer disputes it: *"I never authorised that."*

In the old world the merchant wins this. They produce the IP address, the device fingerprint, the browsing path, the delivery signature. Proof exists because a human touched the screen.

With an agent, none of that exists in a meaningful form. The device belongs to the agent. The browsing path was an API call. The industry states it plainly: traditional chargeback evidence doesn't exist in the same way when an agent made the purchase, and the burden falls on the merchant.

The loss is not one order. Every dispute counts against the merchant's dispute ratio, and Visa tightened the merchant threshold from 2.2% to 1.5% in April 2026. Cross it and you face fines, forced remediation, or losing the ability to accept payments at all.

---

## 2. Why the existing answer is incomplete

The industry's answer is cryptographic delegation. Google's AP2 defines three mandates, all W3C Verifiable Credentials signed with ECDSA and anchored to DIDs:

- **Intent Mandate** — the user's scope and constraints, signed in their client. Example from the spec: *"buy a pair of running shoes, size 10, under $150, white or grey, deliver to my saved address."* The agent cannot exceed this scope without re-prompting.
- **Cart Mandate** — produced by the merchant, binding SKU, price, tax, shipping and total to the Intent.
- **Payment Mandate** — the authorized amount, funding instrument reference, and a hash of the matched Intent and Cart.

Any modification invalidates the signature. Any party can verify the chain without contacting the issuer.

**This is good infrastructure and it solves a real problem — tampering. It does not solve the problem merchants actually face.**

Look at what the reference implementations verify. Tenzro's public `ap2ValidateMandatePair` returns `total_within_intent` and `merchant_allowed`.

**Amount. And merchant allow-list.**

Now take the spec's own example intent — *running shoes, size 10, under $150, white or grey* — and present a cart containing **size 9 black dress shoes at $149**.

- Amount within intent: ✅
- Merchant allowed: ✅
- Signature valid: ✅
- Chain verifies end to end: ✅
- **Purchase is completely wrong.**

The merchant now holds a flawless cryptographic proof that the plumbing worked. The customer isn't complaining about plumbing. They're complaining that they didn't get what they asked for.

> **Cryptography proves the mandate wasn't altered. It does not prove the cart honours the intent.**

That sentence is the entire thesis.

---

## 3. Why nobody has built it

It falls in a discipline gap.

Payment networks and security vendors own this space, and their tooling is cryptographic and behavioural. Signature verification, agent registries, bot detection, trust scoring, velocity checks. All of it answers *"is this actor legitimate?"*

Checking whether a basket of SKUs honours a sentence a human wrote is a language and reasoning problem. It needs constraint extraction, semantic matching, calibrated uncertainty and an explicit cost model. That's ML work, and the teams shipping agentic commerce infrastructure aren't ML teams — they're payments and security teams.

So both sides assumed the other had it. Neither does.

---

## 4. What has actually shipped (the honest teardown)

Do not claim this space is empty. It isn't. Claim precisely what's missing.

**HUMAN Security — AgenticTrust** (shipped, inside HUMAN Sightline). Detects AI agent traffic; verifies agents with cryptographic signatures that can't be spoofed; shows what actions agents take on behalf of each user from discovery to checkout including intent and target routes and whether activity was blocked or allowed; applies granular real-time allow/deny policies; scores agent trustworthiness with AI-generated insights.
→ **Answers: is this agent legitimate and well-behaved?** Not: is this purchase correct?

**Riskified × HUMAN** (Jan 2026). Extended Riskified's chargeback guarantee to cover agent transactions verified through major identity standards. Shipped an AI Agent Policy Builder covering programmatic returns abuse, reseller arbitrage and promo abuse. Riskified has already observed agents stripping inventory and reselling via fraudulent storefronts that other agents then recommend.
→ **Guarantee is conditioned on verified agent identity.** Verified identity says nothing about whether the agent bought the right thing.

**Forter — Identity Monitoring for Agentic Commerce.** Ingests Visa TAP signatures, Skyfire KYAPay JWTs and cross-network agent transaction history, returns a per-request trust score for step-up routing.
→ Reputation scoring. Same category as above.

**PayPal — AP2 work in progress.** Their community post lists extending Seller Protection with Cart and Intent Mandates, mandate IDs and signatures; APIs and adapters for mandate creation and storage; analytics separating agentic from non-agentic traffic.
→ **Storage and evidence assembly.** Not judgment. And it's a roadmap.

**Stripe.** Shared Payment Tokens scoped to one merchant and one cart total, with Radar risk signals stored and shared through the token. Radar previewed bot abuse prevention to distinguish legitimate AI agents from fraudulent actors.
→ Fraud signals and spend caps. Not intent conformance.

**Amex ACE.** Purchase protection covering erroneous purchases by *registered* agents on their network.
→ One network, registered agents, and the announcement never uses the word "fraud."

**Networks.** Mastercard Verifiable Intent creates an auditable trail of consumer consent. Visa TAP adds signed HTTP headers attesting agent identity, user consent and transaction intent.
→ Attestation that consent exists. Not verification that the cart matches it.

**Chargeflow, Justt, Chargeback.io.** All publishing guidance telling merchants to log agent identifiers and mandate events. Chargeback.io, citing ACI Worldwide: *today's tools can't capture the mandate that proves an agent stayed inside the customer's limits, and that mandate is what an agent dispute comes down to.* ACI calls mandate-based authorization untested in courts and before regulators.
→ **Advice, not product.**

---

## 5. The second gap: none of it is Indian

Every layer above is card-rail shaped — Visa TAP, Mastercard Agentic Tokens and Verifiable Intent, Riskified's chargeback guarantee, Amex's protection. AgenticTrust, Riskified and Forter are US/EU enterprise products.

India's position, as of this week:

- **NPCI's Unified Agent Protocol** is expected at Global Fintech Fest, Mumbai, 9–11 September 2026. It builds on UPI Circle delegated payments and Reserve Pay fund-blocking, adding agent registration, spending limits, identity checks and liability provisions. It requires RBI approval.
- **NPCI will not hold this evidence, by design.** Its role stops at confirming a payment request is genuine; it does not see what was bought, mirroring existing UPI architecture. It holds logs only to verify agent trust.
- **RBI Digital Payments E-mandate Framework 2026** (21 April 2026): AFA required at registration and first transaction; pre-transaction notification at least 24 hours before a debit; recurring debits without AFA only up to ₹15,000.
- **CERT-In Digital Threat Report 2025-26** proposed that India mandate human-in-the-loop controls for agentic AI actions above defined financial thresholds, **with full audit trails**. A proposal, not a rule — but it describes this product.
- **DPDP Act 2023** requires consent for a specified purpose. A conversational agent harvests budget, size, recipient and rejection reasons as a by-product; whether existing privacy notices cover that is unsettled.
- **Razorpay, Cashfree and PayU all shipped LLM-native UPI payments in February 2026.** Indian merchants are already taking agent-initiated orders with nothing behind them.
- Banks have publicly flagged that they cannot determine whether an AI-generated payment was genuinely authorised.

**Nothing maps AP2-style mandates onto UPI Circle delegation, Reserve Pay blocks, AFA re-registration or pre-debit notification windows.** Not the global vendors, not Razorpay, not Cashfree, not PayU.

---

## 6. Why Track 02

The track text:

> Build a working **detector, verifier or auto-responder for one class of loss**, with measured **precision and recall on a held-out test set**.
> The bar: honest metrics **including false-positive cost**. Strictly defence-only: anything offense-capable is disqualified.

- **"Verifier"** — the exact word. Warrant verifies a cart against a mandate.
- **"One class of loss"** — disputes and refunds on agent purchases that didn't match the customer's stated intent.
- **"Precision and recall on a held-out test set"** — conforming vs. violating cart pairs, labelled, held out.
- **"False-positive cost"** — legitimate purchases wrongly blocked × order value. This is the number that decides adoption, and it's your honest weak spot. Volunteering it is the credibility move.
- **"Defence-only"** — nothing here is offense-capable.

**Also quote Track 01's bar in your write-up**, because it reads like a spec for this project:

> Every money action explainable, bounded and gated. Show the audit trail and one failure handled gracefully.

Explainable — the verdict says why, in plain language. Bounded — the mandate scope. Gated — allow, refuse, escalate. Audit trail — the decision log in the evidence chain. One failure handled gracefully — the whisky case.

**Do not submit to Track 01.** That track is about growing revenue and making merchants transactable. Warrant sometimes *stops* a purchase. Wrong side of the ledger.

---

## 7. How to open the pitch

Track 02 reviewers are risk and ML people expecting fraud models. Lead with the loss, not the architecture.

> "Merchants are starting to eat disputes on agent purchases they cannot defend, because the evidence that used to win those cases — IP, device, click path — doesn't exist when a machine did the buying. The industry's answer is signed mandates. But the reference implementations check two things: amount, and merchant allow-list. So a mandate for 'groceries under ₹2,000' approves ₹1,900 of whisky, with a perfect signature. I built the missing check."

Then metrics. Lead with model architecture and you read as a protocol project in the wrong track.

---

## 8. What you must not overclaim

Say these out loud in the video and the README. Being first to name your own weaknesses is worth more than any extra metric:

1. Agent transaction volume is small today. Signifyd's network saw agent-referral orders up 1,247% year over year as of October 2025 — a large multiple on a small base. This is built ahead of the curve.
2. The data is synthetic. No public corpus of agent-initiated disputes exists.
3. AgenticTrust, Riskified and Forter have shipped real products in the adjacent layer. You are not claiming the space is empty — you are claiming one specific check is missing, and you can point at `total_within_intent` to prove it.
4. NPCI's UAP spec is unpublished. Your India layer is built against announced mechanics, with adapters, not against a final spec.
