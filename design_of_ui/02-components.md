# Component Library
### Razorpay — International Payments landing page

Each entry: anatomy → measured spec → states/behaviour.

---

## 1. Buttons

### 1.1 Primary (solid blue)
Anatomy: label only, or label + trailing arrow `→`.

| Property | Value |
|---|---|
| Background | `#305EFF` |
| Label | Inter SemiBold, `14px/20px` (small) or `16px/24px` (large), `#FFFFFF` |
| Radius | `4px` |
| Size — nav `Sign Up` | ~90 × 36 px |
| Size — hero `Sign Up Now` | 180 × 36 px |
| Size — section `Accept International Payments` | 277 × 48 px |
| Padding | ~12–14 px vertical, 20–24 px horizontal |
| Hover | Slight darken toward `#2950DA` |

```html
<a class="btn btn--primary">Sign Up Now</a>
```
```css
.btn--primary{background:var(--blue-500);color:#fff;font:600 14px/20px Inter,sans-serif;
  border-radius:4px;padding:8px 20px;display:inline-flex;gap:8px;align-items:center}
```

### 1.2 Secondary — Google Sign-In
Vendor component. White fill, 1 px `#DADCE0` border, `4px` radius, Google "G" mark
16 px, label `Roboto 14px/400 #000`, height 36 px. **Do not restyle** — Google brand
guidelines apply.

### 1.3 Ghost / dark-band pill
Used once, for `Start Now` on the navy CTA band.

| Property | Value |
|---|---|
| Background | `#FFFFFF` |
| Label | Inter SemiBold `16px`, `#192839` |
| Radius | `100px` (pill) |
| Size | ~84 × 40 px, centred |

### 1.4 Text link
Inter `14px/20px`, `#2950DA` (footer/nav) or `#305EFF` (in-content `Know More`,
`Get Apple Pay`). No underline at rest; underline on hover.

### 1.5 Wallet CTA pair
`Get Apple Pay` / `Get Google Pay` — two primary blue buttons side by side, 16 px gap,
centred under the KPI row.

---

## 2. Navigation bar

| Property | Value |
|---|---|
| Height | 74 px, sticky, `#FFFFFF`, full-bleed |
| Content width | 1184 px, space-between |
| Logo | Razorpay wordmark ~112 × 24 px, left |
| Menu items | `Agentic Stack · Payments · Banking+ · Payroll · Engage · Partners · Resources · Pricing` — Inter `14px/16.8px`, `-0.42px` tracking, `#192839` |
| Right cluster | Headset support icon → India flag chip with caret → `Login` (Inter SemiBold 14 px `#2950DA`) → `Sign Up` primary button |
| Item gap | ~24 px |
| Dropdowns | Menu items with children open on hover (mega-menu) |

`Agentic Stack` appears twice in the DOM — a visible label plus a transparent
duplicate (`rgba(0,0,0,0)`) used for a hover/animation swap.

---

## 3. Stat card ("Receive payments from 180+ Countries")

```
┌──────────────────────────┐  320 × 425, #FFF, radius 12, pad 24, no border
│ Receive payments from    │  eyebrow — TASA Orbiter Regular 18/24 #40566D
│ 180+                     │  number  — TASA Orbiter Medium 48/56 #192839
│ Countries                │  noun    — same style, second line
│                          │
│ 🇨🇦 Canada                │  marquee list: 28px flag circle + Inter Tight 20/50
│ 🇦🇺 Australia             │  vertically scrolling, masked top & bottom
│ 🇦🇪 UAE                   │
└──────────────────────────┘
```

Three variants share the frame:
1. **Countries** — vertical flag+name marquee.
2. **Currencies** — horizontal row of pastel-filled currency pills (`£ $ ₽ ¥ A$ C$ CHF S$ د.إ €`), glyph Inter Tight `45.57px/500`, chip is a `100%`-radius circle in a rotating tint from the accent-tint set.
3. **One Platform** — static grid of payment-network logos (Diners Club, VISA, Discover, Mastercard, Amex…), greyscale/full-colour as supplied.

---

## 4. Support strip

Full-width `1184 × 156` *(inner strip ~1184 × 64)*, `#FFFFFF`, radius 12,
padding `32px 44px`. Headset icon in a mint circle + text
"**India-based support. For Indian exporters.**" — the second sentence bolded.

---

## 5. Cross-sell banner (UPI)

| Property | Value |
|---|---|
| Size | 1184 × 156 |
| Fill | `#D7ECF0` (band-sky), radius 12 |
| Padding | `32px 44px` |
| Layout | 2-col — left headline block, right copy + link |
| Headline | TASA Orbiter `~28px`, two lines, second line emphasised |
| Body | Inter `14px/20px` `#40566D`, max ~2 lines |
| Link | `Know More` — `#305EFF`, Inter 14 SemiBold |

---

## 6. Media composite (hero & wallets)

The signature component: a full-bleed lifestyle photograph inside a `1184 × 570`
container at radius 12, with a **simulated product UI** composited on top.

Hero composite layers:
1. Photo (warm interior, two people).
2. Floating **checkout card** — white, radius ~12, `shadow 0 4px 9px rgba(0,0,0,.09)`,
   containing: merchant name, product name (`Red Lehenga`, Inter Tight 14/16.8),
   buyer name, `Total Amount` micro-label (Inter Tight 10/12 `#021C29`),
   amount (Inter Tight `20.65px/400` with a `19.1px/500` decimal run),
   a `Pay Now` button (Inter Tight `11.67px/600` `#192839`), and a
   `Secured by Razorpay` footer (TASA Orbiter `8.44px` `#243547`).
3. Country/flag chips (`🇺🇸 USA`) pinned to the lower corners — pill, white, 100 px radius.
4. Ambient amount bubbles (`€ 380.00`, `$1840.00`, `A$ 8720.00`, `£423.00`).

Wallets composite: same frame, right half is a full mobile checkout sheet showing
Apple Pay / Google Pay buttons stacked above an "All Payment Options" accordion
(Cards, Wallets) and a `$75.98 → Pay Now` action bar.

---

## 7. KPI row

Four equal columns, hairline `1px #E3EAF3` dividers between them.

```
500 Mn+        95% ▲          5x Faster       Biometric Auth
Worldwide      Success Rates  Checkout        No card entry, no OTPs
```

- Value: Inter `~32px/500`, `#192839` (`95%` carries a small green ▲ delta glyph).
- Caption: Inter `14px/20px`, `#40566D`.

---

## 8. Logo marquee (trust strip)

Height ~110 px on `#FFFFFF`. Logos rendered greyscale/mono at ~24–32 px cap height,
~48 px gap, continuous horizontal scroll with `‹ ›` affordances at the edges.
Members observed: IndiGo, PSL, Flipkart, Policybazaar, Lenskart, Nykaa, Sabyasachi,
MakeMyTrip, ixigo, Air India.

---

## 9. Testimonial carousel

| Property | Value |
|---|---|
| Card | 395 × 520, `#FFFFFF`, radius **8**, padding `32px 20px`, no border |
| Card top | Customer logo, ~24 px tall, left-aligned |
| Quote | Inter `14px/22px` `#192839`, curly quotes retained |
| Attribution | pinned to card bottom: 32 px circular avatar + name (Inter 14/600) + role (Inter 12/400 `#40566D`) |
| Left rail | Sticky title block — `Stories Beyond Borders` (TASA Orbiter ~38px) + supporting line `14px #40566D` |
| Controls | Circular `‹` `›` buttons overlapping the card edges; 5 dot indicators below, active dot `#192839`, inactive `#8996A9` |
| Loop | Content set duplicated 4× in DOM for seamless paging |

---

## 10. Closing CTA band

Full-bleed dark navy (`#0B1F2A`), ~800 px tall. Background: halftone dotted world map
in `rgba(255,255,255,.16)` with thin green flight arcs. Centred content:
H2 in white TASA Orbiter (`Going global? / We'll help you feel at home.`) over a
white pill `Start Now` button. No other content in the band.

---

## 11. Footer

White, ~1100 px tall, 1184 px content width.

- **Column 1 (≈340 px):** Razorpay logo, then three `12px/18px #40566D` SEO paragraphs, then a disclaimer paragraph.
- **Columns 2–4:** grouped link lists under 12 px uppercase eyebrows with `letter-spacing ~.08em`, weight 600–700, `#192839`:
  `ACCEPT PAYMENTS · PAYROLL · BECOME A PARTNER · MORE · BANKING PLUS · DEVELOPERS · RESOURCES · SOLUTIONS · FREE TOOLS · COMPANY · HELP & SUPPORT · FIND US ONLINE`
- Links: Inter `14px/20px` `#2950DA`, ~20 px row spacing. A `NEW` pill badge appears beside *Razorpay POS*.
- **Social row:** 5 circular 24 px icons (Facebook, X, Instagram, GitHub, LinkedIn).
- **Registered address block** + CIN, then copyright, RBI authorisation line and an
  effective-date regulatory notice with a `Know more` link.
