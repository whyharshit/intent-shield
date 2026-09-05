# Page UI Spec — section by section
### Razorpay — International Payments landing page (desktop)

Page canvas 1853 px wide · 6567 px tall · content column 1184 px.

---

## S0 · Navigation — sticky, 74 px, `#FFFFFF`

```
[Razorpay logo]  Agentic Stack  Payments  Banking+  Payroll  Engage  Partners  Resources  Pricing
                                               [🎧] [🇮🇳 ▾]  Login  [ Sign Up → ]
```
Behaviour: sticky through the whole page; mega-menu on hover for the product items;
region selector opens a country list; `Sign Up` is the persistent primary conversion.

---

## S1 · Hero — white, ~640 px

**Layout:** two-column, ~7 / 5 split, top-aligned, then a full-width media block below.

| Slot | Content | Style |
|---|---|---|
| Eyebrow | `Accept International Payments` | Inter 14/20, `#2950DA` |
| H1 line 1 | `Don't Get Played.` | TASA Orbiter Display Regular **64/70**, `-2.56px`, `#192839` |
| H1 line 2 | `Go Global with Razorpay.` | same, `#305EFF` |
| Support copy (right col) | *Power your business with global payment options. Cards, bank transfers, Apple Pay and more. Lowest fees and India-based support.* | Inter 14/20, `#40566D`, max ~2 lines |
| CTA row (right col) | `Sign Up Now` (primary, 180×36) + `Sign up with Google` (vendor button) | 12 px gap |
| Media | 1184 × 570 photo, radius 12, padding 60 | see *Media composite* in `02-components.md` |

**Notes on the composite:** the checkout card is centre-left over the photo; a
`🇺🇸 USA` pill sits bottom-left, a flag avatar bottom-right; floating amount bubbles
(`€ 380.00 · $1840.00 · A$ 8720.00 · £423.00`) drift around the frame to signal
multi-currency without a word of copy.

---

## S2 · Trust strip — white, ~110 px

Continuous greyscale logo marquee, ~24–32 px cap height, `‹ ›` edge affordances.
No heading. Acts as the visual break between hero and value band.

---

## S3 · Value band — `#EDF4F7`, 1005 px, padding 120 / 120

### S3a — Section header (2-col, baseline aligned)
- **H2 (left):** `Built for India's global businesses.` / `Not international middlemen.`
  TASA Orbiter ~48/56, `#192839`, two lines, hard break preserved.
- **CTA (right):** `Accept International Payments` — primary blue, 277 × 48, radius 4,
  label Inter SemiBold 16/24.

### S3b — Stat card row (3 columns, 24 px gap, cards `#FFF` radius 12 pad 24)

| Card | Eyebrow | Value | Body |
|---|---|---|---|
| 1 | `Receive payments from` | `180+` `Countries` | vertical flag marquee — USA, United Kingdom, Canada, Australia, UAE, France, Singapore, Italy, Germany, Saudi Arabia |
| 2 | `Receive payments in` | `135` `Currencies` | horizontal pill marquee — £ $ ₽ ¥ A$ C$ CHF S$ د.إ € |
| 3 | `Accept cards, local methods & bank transfers on` | `One` `Platform` | static network-logo grid — Diners Club, VISA, Discover, Mastercard, Amex |

### S3c — Support strip
White bar, radius 12, headset icon + `India-based support. For Indian exporters.`

### S3d — UPI cross-sell banner
`#D7ECF0`, radius 12, padding 32 / 44, 2-col:
- Left: `Global brand?` / `Accept UPI from India.`
- Right: *Collect INR payments from Indian customers without a local entity. Accept payments via cards, netbanking and India's best UPI stack.* + `Know More` link.

---

## S4 · Digital Wallets — white, ~900 px

| Slot | Content |
|---|---|
| Eyebrow | `Digital Wallets` — Inter 14/20 `#2950DA` |
| H2 | `Accept Apple Pay and Google Pay payments` / `on your global checkout` — TASA Orbiter ~40/48, left-aligned, 2 lines |
| Media | 1184 × 570 composite, radius 12. Left half: portrait photo with Apple Pay + Google Pay marks and the caption *Give your global buyers the checkout they love and trust* overlaid bottom-left. Right half: a full mobile checkout sheet (merchant header `kaaleenindia™`, Contact / Address / **Payment** step rail, Apple Pay black button, Google Pay black button, "All Payment Options" → Cards ›, Wallets ›, and a `$75.98 · Pay Now` action bar). |
| KPI row | `500 Mn+ Worldwide` · `95% ▲ Success Rates` · `5x Faster Checkout` · `Biometric Auth — No card entry, no OTPs` |
| CTA row | `Get Apple Pay` + `Get Google Pay`, both primary blue, centred |

---

## S5 · Stories Beyond Borders — `#EDF4F7`, ~900 px

- **Left rail (sticky, ~4 cols):** `Stories Beyond Borders` (TASA Orbiter ~38/44) +
  *How Razorpay is helping Indian businesses scale globally* (Inter 14/20 `#40566D`).
- **Right:** horizontally paged carousel of 395 × 520 quote cards.

| # | Customer | Speaker | Angle |
|---|---|---|---|
| 1 | Masaba | Masaba Gupta, Founder | expanded to 87 countries; +5% intl success rate |
| 2 | Habuild | Anshul Agrawal, CPTO & Co-Founder | multi-currency subscriptions without hassle |
| 3 | Spardha School of Music & Dance | Saurabh Srivastav & Rikhil Jain | secure, efficient processing for expansion |
| 4 | FNP | Chirantan Sharma, Head of Product | 2× international orders per day |
| 5 | Astrotalk | Anmol Jain, Chief Business Officer | best-in-class chargeback win rates |

Controls: circular `‹` `›` overlapping card edges + 5 dot indicators.

---

## S6 · Closing CTA — dark navy, ~800 px

Full-bleed `#0B1F2A` with an animated halftone world map and green flight arcs.
Centred: `Going global?` / `We'll help you feel at home.` in white TASA Orbiter,
above a white pill `Start Now` button. Deliberately empty of everything else —
maximum negative space before the footer.

---

## S7 · Footer — white, ~1100 px

Four-column layout at 1184 px.

1. **Brand column** — logo + three SEO paragraphs (payments suite / RazorpayX / marketplace) + RazorpayX banking disclaimer, all `12px/18px #40566D`.
2. **Links col A** — ACCEPT PAYMENTS (11 links incl. Razorpay POS `NEW`), PAYROLL, BECOME A PARTNER, MORE (8 links).
3. **Links col B** — BANKING PLUS (6), DEVELOPERS (3), RESOURCES (6), SOLUTIONS (4), FREE TOOLS (6).
4. **Links col C** — COMPANY (10), HELP & SUPPORT (2), FIND US ONLINE (5 social icons), REGD. OFFICE ADDRESS + CIN.

Bottom rail: `© Razorpay 2025 · All Rights Reserved`, the RBI Authorised Payment
Aggregator line, and a dated regulatory notice (*Effective January 01, 2026 …*) with
a `Know more` link.

---

## Responsive intent (inferred — verify against the live mobile build)

| Breakpoint | Expected behaviour |
|---|---|
| ≥1280 | Spec as written; 1184 px content, 120 px band padding |
| 1024–1279 | Content fluid to gutters; H1 → ~52 px; stat row stays 3-up |
| 768–1023 | Hero collapses to single column (headline → copy → CTAs → media); stat row 3-up becomes 1-up stack or 2+1; KPI row 2×2 |
| <768 | H1 → ~36–40 px; all rows stack; buttons full-width; testimonial carousel one card per page with swipe; footer columns become accordions |

Framer variant names in the DOM (`Dweb`, `Variant 4`) confirm separate desktop/mobile
component variants rather than pure CSS reflow.
