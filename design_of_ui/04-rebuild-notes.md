# Rebuild Notes & Observations

Practical notes for anyone recreating this page — plus issues found on the live build.

---

## 1. Fonts

- **TASA Orbiter Display** (Regular + Medium) carries the whole brand voice here. It is
  a commercial family from TypeArsenal — licence it, don't substitute silently.
  Nearest free stand-ins if you must: *General Sans*, *Satoshi*, or *Archivo* with
  `-0.04em` tracking applied at display sizes.
- **Inter** and **Inter Tight** are open-source (SIL OFL). Inter Tight is used
  exclusively inside the simulated checkout UI — that's what makes those mock cards
  read as "product" rather than "marketing".
- The page loads `Inter-SemiBold` as a separate family name rather than using
  `font-weight:600` on Inter. If you rebuild outside Framer, use one variable Inter
  file and real weight axes — it's smaller and avoids faux-bold mismatch.

## 2. Getting the look right

**Do:**
- Keep the accent count at one. `#305EFF` on white, `#EDF4F7` bands, `#192839` text —
  that trio does 90% of the work.
- Set display type at `-0.04em` and body at `0`. The tracking contrast is a big part
  of the feel.
- Give cards fill + 12 px radius and **no border, no shadow**. Only the floating
  checkout card gets `0 4px 9px rgba(0,0,0,.09)`.
- Hold the 120 px band padding. The page reads calm because the vertical rhythm is
  uniform and generous.
- Make every claim a number. If a section has no numeral, it probably doesn't belong.

**Don't:**
- Don't add a second saturated colour. The pastel tints are for chip fills only, never
  for text or buttons.
- Don't put the marquees on a fast loop — they're slow ambient texture, not a feature.
- Don't shrink the media composites below ~500 px tall; the embedded checkout UI stops
  being legible and the whole "proof" device fails.

## 3. Structural recipe (HTML skeleton)

```html
<header class="nav">…</header>
<main>
  <section class="hero band--white">…</section>
  <section class="logos band--white">…</section>
  <section class="value band--ice">
    <div class="section-head">…</div>
    <div class="stat-row">…×3</div>
    <div class="support-strip">…</div>
    <div class="banner banner--sky">…</div>
  </section>
  <section class="wallets band--white">…</section>
  <section class="stories band--ice">…</section>
  <section class="cta band--dark">…</section>
</main>
<footer class="footer">…</footer>
```

```css
.band{padding:120px 0}
.band>*{max-width:1184px;margin-inline:auto}
.band--ice{background:var(--band-ice)}
.band--dark{background:var(--dark-bg);color:#fff;text-align:center}
.stat-row{display:grid;grid-template-columns:repeat(3,1fr);gap:24px}
.card{background:#fff;border-radius:12px;padding:24px}
```

## 4. Accessibility issues found on the live page

Worth fixing in any rebuild:

| Issue | Detail |
|---|---|
| **Unstyled link colour leaking** | `rgb(0,0,238)` (browser-default link blue) is computed on **232 elements**, including the `Sign Up Now` and `Accept International Payments` buttons — the visible white label comes from a nested span, so the anchor's own colour is never reset. Harmless visually, but it means link colour is not being managed. Set `color` on the anchor. |
| **Default font fallback** | `sans-serif` with no family ahead of it is computed on **1925 elements** at `12px`. Those are mostly empty Framer wrappers, but it signals no global `font-family` / base size is set on `html`/`body`. Set both. |
| **Motion** | Three infinite marquees plus an animated map, with no visible pause control. Add `@media (prefers-reduced-motion: reduce){ animation:none }`. |
| **Carousel semantics** | Testimonial content is duplicated 4× in the DOM for looping, so screen readers hear each quote four times. Mark duplicates `aria-hidden="true"`. |
| **Marquee duplication** | Same issue for country and currency lists (each repeated 3×). |
| **Contrast to verify** | `#8996A9` on `#EDF4F7` ≈ 2.6:1 — below AA for text. Fine for inactive carousel dots, not for any label. |
| **Icon-only controls** | Carousel arrows, headset icon and social icons need `aria-label`s. |

## 5. Content inventory (for a copy deck)

| Section | Headline | Primary CTA |
|---|---|---|
| Hero | Don't Get Played. / Go Global with Razorpay. | Sign Up Now |
| Value | Built for India's global businesses. / Not international middlemen. | Accept International Payments |
| Cross-sell | Global brand? / Accept UPI from India. | Know More |
| Wallets | Accept Apple Pay and Google Pay payments on your global checkout | Get Apple Pay / Get Google Pay |
| Stories | Stories Beyond Borders | — |
| Close | Going global? / We'll help you feel at home. | Start Now |

**Claim set to keep consistent:** 180+ countries · 135 currencies · one platform ·
500 Mn+ wallet users · 95% success rates · 5x faster checkout · India-based support.

## 6. Legal / compliance chrome to carry over

- RBI Authorised Payment Aggregator line.
- Effective 01 Jan 2026 notice: payment aggregation services operated by
  Razorpay Payments Private Limited.
- RazorpayX current-account and credit-card disclaimer (partner banks: ICICI, RBL, Yes Bank).
- Registered office + CIN `U62099KA2024PTC188982`.
- Apple Pay and Google Pay marks are used under their respective brand guidelines —
  the Google Sign-In button must not be restyled.

---

**Sources:** [Accept International Payments | Razorpay](https://razorpay.com/international-payments-onboard/) — live DOM computed styles and screenshots, captured 05 Sep 2026.
