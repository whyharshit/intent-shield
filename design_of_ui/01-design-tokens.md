# Design Tokens
### Razorpay — International Payments landing page

Measured from computed styles on the live page. `rgb()` values are as reported by the
browser; hex is the conversion.

---

## 1. Colour

### 1.1 Core palette

| Token | Value | Hex | Where it's used |
|---|---|---|---|
| `--ink-900` | `rgb(25, 40, 57)` | `#192839` | Primary text: H1 line 1, stat numbers, nav links, "Pay Now" label |
| `--ink-800` | `rgb(36, 53, 71)` | `#243547` | "Secured by" micro-label |
| `--ink-700` | `rgb(2, 28, 41)` | `#021C29` | "Total Amount" micro-label in checkout card |
| `--ink-600` | `rgb(64, 86, 109)` | `#40566D` | Card eyebrows ("Receive payments from"), secondary body |
| `--ink-400` | `rgb(137, 150, 169)` | `#8996A9` | Muted meta, carousel dots (inactive) |
| `--blue-600` | `rgb(41, 80, 218)` | `#2950DA` | Footer + inline links, "Login" |
| `--blue-500` | `rgb(48, 94, 255)` | `#305EFF` | **Primary accent** — H1 line 2, all primary buttons, "Know More" |
| `--surface` | `rgb(255, 255, 255)` | `#FFFFFF` | Nav, cards, white bands |
| `--band-ice` | `rgb(237, 244, 247)` | `#EDF4F7` | Value band + testimonial band background |
| `--band-mist` | `rgb(240, 244, 246)` | `#F0F4F6` | Secondary surface / hover fills |
| `--band-sky` | `rgb(215, 236, 240)` | `#D7ECF0` | UPI cross-sell banner fill |
| `--ink-inverse` | `#FFFFFF` | — | Text on dark navy CTA band |

### 1.2 Dark band (closing CTA)

| Token | Value (approx.) | Use |
|---|---|---|
| `--dark-bg` | `#0B1F2A` – `#0D2430` | Full-bleed closing CTA background |
| `--dark-map-dot` | `rgba(255,255,255,0.16)` | Dotted world-map halftone |
| `--dark-arc` | `#4FD1A5` (thin green) | Flight-path arcs across the map |

### 1.3 Accent tints (illustration / chip fills)

Used only inside small decorative chips, avatars and currency pills — never for text.

```
#C1FF84  #D8FDB4  #B4CDFD  #D8E4FD  #BAD9F7  #C2E0E0
#B6ECD1  #91E3BA  #B7D8E0  #CBDDE6  #E3EAF3
```

### 1.4 Semantic / brand-borrowed

| Token | Value | Use |
|---|---|---|
| `--flag-red` | `rgb(237, 41, 57)` `#ED2939` | India flag chip |
| `--brand-red` | `rgb(213, 43, 30)` `#D52B1E` | Third-party mark (Discover/UAE flag) |
| `--near-black` | `rgb(28, 28, 24)` `#1C1C18` | Apple Pay button surface |

### 1.5 CSS variables

```css
:root{
  --ink-900:#192839; --ink-800:#243547; --ink-700:#021C29;
  --ink-600:#40566D; --ink-400:#8996A9;
  --blue-500:#305EFF; --blue-600:#2950DA;
  --surface:#FFFFFF; --band-ice:#EDF4F7; --band-mist:#F0F4F6; --band-sky:#D7ECF0;
  --dark-bg:#0B1F2A;
  --radius-sm:4px; --radius-md:8px; --radius-lg:12px; --radius-xl:24px; --radius-pill:100px;
  --shadow-card:0 4px 9px rgba(0,0,0,.09);
}
```

---

## 2. Typography

### 2.1 Families

| Role | Stack | Notes |
|---|---|---|
| **Display** | `"TASA Orbiter Display", sans-serif` (Regular + Medium cuts) | All H1/H2, big stat numbers, card eyebrows. Wide, low-contrast geometric grotesque. |
| **UI / body** | `Inter, sans-serif` — SemiBold cut loaded separately as `Inter-SemiBold` | Nav, buttons, body copy, footer |
| **Numeric / product UI** | `"Inter Tight", sans-serif` | Everything inside the simulated checkout cards, currency glyphs, country names |
| **Tertiary** | `Lato` | A few legacy footer/legal fragments |
| **Third-party** | `Roboto` | Google Sign-In button only (vendor-controlled) |

### 2.2 Type scale (desktop, measured)

| Style | Size / line-height | Weight | Family | Letter-spacing | Colour |
|---|---|---|---|---|---|
| Display XL — H1 | `64px / 70px` | 400 | TASA Orbiter Display Regular | `-2.56px` (-0.04em) | `#192839`, 2nd line `#305EFF` |
| Display L — section H2 | `48px / 56px` | 400 | TASA Orbiter Display | `-0.04em` *approx.* | `#192839` |
| Stat number | `48px / 56px` | 400 | TASA Orbiter Display **Medium** | normal | `#192839` |
| Currency glyph | `45.57px` | 500 | Inter Tight | normal | `#000` |
| Display M | `38.13px` / `40px` | 400 | TASA Orbiter Display | — | `#192839` |
| KPI number (`500 Mn+`) | `32px` *approx.* | 500 | Inter | `-0.02em` | `#192839` |
| Card eyebrow | `18px / 24px` | 400 | TASA Orbiter Display Regular | normal | `#40566D` |
| Button label (large) | `16px / 24px` | 600 | Inter SemiBold | normal | `#FFFFFF` |
| Body / nav / button (default) | `14px / 20px` | 400–600 | Inter | nav uses `-0.42px` (-0.03em) | `#192839` |
| Ticker item | `20px / 50px` | 400 | Inter Tight | normal | `#000` |
| Micro-label | `10px / 12px` | 400 | Inter Tight | normal | `#021C29` |
| Legal / footnote | `12px` | 400 | Inter | normal | `#40566D` |

**Weights in use:** 400 (dominant), 500, 600, 700 (rare — footer eyebrows).

**Rule of thumb:** display sizes always take negative tracking (≈ `-0.04em`);
UI text at 14–16 px stays at normal tracking except the nav, which is tightened slightly.

---

## 3. Spacing & layout

| Token | Value | Use |
|---|---|---|
| Content max-width | **1184 px** | Every card row, image container and text column snaps to this |
| Page gutter | ~64 px at 1349 vw; fluid below | |
| Section vertical padding | **120 px top / 120 px bottom** | Measured on the value band; the standard band rhythm |
| Card padding (stat card) | **24 px** | 320 × 425 stat card |
| Card padding (testimonial) | **32 px 20px** | 395 × 520 quote card |
| Banner padding | **32 px 44 px** | UPI cross-sell banner |
| Image container padding | **60 px** | Composite hero/wallet image frames |
| Grid gap | 24 px (3-col cards), 32 px (carousel) *approx.* | |
| Nav height | **74 px** | |

### Spacing scale (inferred)
`4 · 8 · 12 · 16 · 20 · 24 · 32 · 44 · 60 · 80 · 120`

### Grid
- 12-column, 1184 px content width.
- Hero: asymmetric **7 / 5** split (headline left, support copy + CTAs right).
- Stat row: **3 equal columns** (320 / 408 / 408-ish; the middle and right cards are wider than the left).
- Wallet KPIs: **4 equal columns** separated by 1 px hairline dividers.
- Testimonials: sticky **4-col** title block + horizontally scrolling **395 px** cards.

---

## 4. Radius

| Token | Value | Applied to |
|---|---|---|
| `--radius-sm` | `4px` | Buttons (`Sign Up Now`, `Accept International Payments`) |
| `--radius-md` | `8px` | Testimonial cards |
| `--radius-lg` | `12px` | Stat cards, image frames, banners, product cards |
| `--radius-xl` | `24px` | Large decorative containers (most frequent non-zero radius, 72 occurrences) |
| `--radius-pill` | `100px` / `100%` | Chips, avatars, country flag badges, closing CTA button |

---

## 5. Elevation

Shadows are almost absent — the page relies on fill contrast. Only two real elevations:

| Token | Value | Use |
|---|---|---|
| `--shadow-card` | `0 4px 9px rgba(0,0,0,.09)` | The single floating checkout card in the hero |
| `--glow-warm` | `inset 0 0 15px rgba(217,119,87,.7), inset 0 0 25px rgba(217,119,87,.5), inset 0 0 35px rgba(217,119,87,.2)` | Decorative inner glow on an accent element |

Cards on tinted bands use **no shadow and no border** — separation is fill-vs-band contrast only.

---

## 6. Motion

| Element | Behaviour |
|---|---|
| Country list | Vertical infinite marquee, ~10 items repeated 3× in the DOM, continuous linear scroll |
| Currency list | Same pattern, horizontal, currency glyphs in pastel pill chips |
| Logo strip | Horizontal marquee, greyscale logos, pauses/arrows at either end |
| Testimonials | Paged carousel — arrow buttons left/right, 5 dot indicators, DOM contains 4 duplicate sets for looping |
| Closing CTA map | Slow ambient animation on the dotted world map + flight arcs |
| Nav | Sticky, white, remains opaque on scroll |
