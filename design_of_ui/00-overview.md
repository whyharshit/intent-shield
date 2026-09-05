# Razorpay — International Payments Landing Page
## Design & UI Overview

**Source:** https://razorpay.com/international-payments-onboard/
**Captured:** 05 Sep 2026 · Desktop (1349 px viewport, 1853 px page canvas)
**Built with:** Framer (all `data-framer-name` wrappers, Framer font placeholders)

---

## 1. Design language in one paragraph

A **fintech-editorial** style: large display headlines in a wide, geometric grotesque
(TASA Orbiter Display) set on generous white and pale-blue bands, with all supporting
copy in Inter / Inter Tight. Colour is used sparingly — near-black navy for text,
one saturated electric blue for every action and every emphasis word, and desaturated
pastel tints (ice blue, mint, sky) for section bands and card fills. Photography is
warm, human and full-bleed inside 12 px-rounded containers, always overlaid with a
floating "product proof" UI card (a checkout, a payment sheet). Numbers are the hero
of the middle of the page — `180+`, `135`, `One`, `500 Mn+`, `95%`, `5x` — rendered
at display scale so the value proposition is scannable in three seconds.

## 2. Design principles read off the page

| Principle | How it shows up |
|---|---|
| **One accent, used decisively** | `#305EFF` is the *only* saturated colour: second line of the H1, every primary button, every link. Nothing else competes. |
| **Proof over prose** | Every claim is a number in a card, a real logo strip, or a named customer quote with a face. Body copy never exceeds ~2 lines. |
| **Show the product, don't describe it** | Hero and wallets sections both composite a real checkout UI on top of a lifestyle photo. |
| **Bands, not borders** | Sections are separated by full-bleed background tints (`#EDF4F7`, `#FFFFFF`, dark navy) rather than rules or heavy card outlines. Cards are borderless — shape comes from fill + radius. |
| **India-first positioning** | Copy contrast ("Not international middlemen", "India-based support. For Indian exporters.") is echoed visually by the India flag chip in the nav and the country/currency tickers. |
| **Motion as texture** | Country and currency lists are infinite marquees; testimonials are a paged carousel; the closing CTA sits on an animated dotted world map. |

## 3. Page rhythm (scroll map)

```
┌ 74 px  Sticky nav — white, logo left, 7 menu items, region chip, Login, Sign Up
├ ~640   HERO — eyebrow / 2-line 64px H1 / support copy + 2 CTAs (asymmetric 2-col)
├ ~110   TRUST STRIP — greyscale customer logo marquee
├ 1005   VALUE BAND (#EDF4F7) — H2 + blue CTA, 3 stat cards, support strip, UPI banner
├ ~900   DIGITAL WALLETS (white) — eyebrow / H2 / photo+checkout composite / 4 KPIs / 2 CTAs
├ ~900   STORIES BEYOND BORDERS (#EDF4F7) — sticky left title + 5-card testimonial carousel
├ ~800   CLOSING CTA — dark navy, dotted world map, centred H2 + white pill button
└ ~1100  FOOTER — white, logo + 3 legal paragraphs + 6 link columns + address + RBI notice
```

## 4. Files in this set

| File | Contents |
|---|---|
| `01-design-tokens.md` | Colour, typography, spacing, radius, shadow, grid tokens (with CSS variables) |
| `02-components.md` | Reusable component specs — buttons, cards, nav, marquee, carousel, KPI row |
| `03-page-ui-spec.md` | Section-by-section anatomy, layout, copy and behaviour |
| `04-rebuild-notes.md` | Practical notes for rebuilding, incl. accessibility gaps found on the live page |

> All values were measured from the live DOM's computed styles; hex values are
> conversions of the reported `rgb()` values. Anything marked *approx.* was read
> off screenshots rather than the DOM.
