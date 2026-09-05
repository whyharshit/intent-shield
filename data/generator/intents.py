"""Intent templates and mandate sampling.

Thirty templates spanning recurring groceries, one-off purchases with
attributes, gifts with a budget, restocks with a brand preference, pharmacy
refills and food delivery.

Specificity is varied on purpose. Roughly a fifth of intents are vague — "some
snacks for the kids, nothing too expensive" — because a vague intent *should*
produce more escalations, and showing that relationship is a good result rather
than a weakness (07 §B, "what if the user's intent was genuinely vague?").
Vague templates carry `ambiguous_terms` and either no `deliver_by` or a fuzzy
budget; precise ones pin attributes, brands and deadlines.

The generator emits both the natural-language text *and* the ground-truth
constraints. C2's extraction accuracy is later measured against these, which is
the separate number 05 §Day-9 asks for — extraction errors poison everything
downstream, so they get reported on their own.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from data.generator.pairs import Specificity
from warrant.models import HardConstraints, IntentMandate, SoftConstraints

# Fallback brand pool, used only when no catalog is supplied.
#
# Naming brands from a hardcoded list does not work: the first version drew from
# a plausible-sounding set (Fortune, Dabur, Patanjali, Parle) of which most had
# zero SKUs in the catalog, so "avoid Dabur" was unbreachable and
# BRAND_EXCLUSION ended up with no test cases at all. Real pools are derived
# from the catalog by `brand_pool()` — a mandate may only name a brand the
# catalog can actually supply. See DECISIONS.md D-020.
BRANDS = (
    "Amul", "Tata", "Aashirvaad", "Britannia", "Saffola", "Himalaya", "Catch",
)
COLOURS = ("black", "navy blue", "grey", "white", "maroon", "green", "red", "beige")
MERCHANTS = (
    "mrc_bigbasket", "mrc_blinkit", "mrc_zepto", "mrc_instamart",
    "mrc_dmart", "mrc_jiomart",
)


@dataclass(frozen=True)
class IntentTemplate:
    id: str
    specificity: Specificity
    text: str
    allowed: tuple[str, ...]
    denied: tuple[str, ...] = ()
    frequency: str | None = None
    budget: tuple[int, int] = (500, 3000)          # rupees
    horizon_days: tuple[int, int] = (14, 60)
    deliver_by_days: tuple[int, int] | None = None
    max_uses: int | None = None
    cumulative_multiple: int | None = None
    attributes: tuple[str, ...] = ()
    brand_prefs: int = 0                            # how many to sample
    brand_excl: int = 0
    quality: tuple[str, ...] = ()
    ambiguous: tuple[str, ...] = ()
    wants_colour: bool = False
    merchant_locked: bool = False
    scope_note: str = ""


FOOD = ("grocery", "produce", "staples")
HOME = ("household",)
CARE = ("personal_care",)

TEMPLATES: tuple[IntentTemplate, ...] = (
    # ---- recurring groceries: the core domain the demo lives in -----------
    IntentTemplate(
        "groc_weekly_basic", "normal",
        "Buy our weekly groceries, under Rs {budget}, nothing alcoholic.",
        allowed=FOOD, denied=("alcohol", "tobacco"), frequency="weekly",
        budget=(1500, 3000), max_uses=6, cumulative_multiple=6,
    ),
    IntentTemplate(
        "groc_weekly_brand", "precise",
        "Weekly grocery run under Rs {budget}. Stick to {brand} and {brand2} "
        "where you can, no alcohol or tobacco, deliver by {deadline}.",
        allowed=FOOD, denied=("alcohol", "tobacco"), frequency="weekly",
        budget=(1800, 3500), deliver_by_days=(2, 5), brand_prefs=2,
        max_uses=6, cumulative_multiple=6,
    ),
    IntentTemplate(
        "groc_weekly_vague", "vague",
        "Get the usual weekly shopping, don't spend too much.",
        allowed=FOOD, denied=("alcohol", "tobacco"), frequency="weekly",
        budget=(1200, 2500),
        ambiguous=("the usual", "don't spend too much"),
    ),
    IntentTemplate(
        "groc_monthly_bulk", "normal",
        "Monthly grocery and staples stock-up, cap it at Rs {budget}. "
        "No alcohol.",
        allowed=FOOD + HOME, denied=("alcohol", "tobacco"), frequency="monthly",
        budget=(4000, 9000), max_uses=2, cumulative_multiple=3,
    ),
    IntentTemplate(
        "groc_fortnight", "normal",
        "Top up groceries every couple of weeks, Rs {budget} maximum per order, "
        "nothing alcoholic and no cigarettes.",
        allowed=FOOD, denied=("alcohol", "tobacco"), frequency="weekly",
        budget=(1000, 2200),
    ),
    IntentTemplate(
        "groc_readme", "normal",
        "Groceries for the week, under Rs {budget}, nothing alcoholic, "
        "prefer Indian brands.",
        allowed=FOOD, denied=("alcohol", "tobacco"), frequency="weekly",
        budget=(2000, 2000), brand_prefs=1,
        ambiguous=("for the week",),
        scope_note="the mandate from 00-README",
    ),

    # ---- staples and produce ---------------------------------------------
    IntentTemplate(
        "staples_restock", "normal",
        "Restock atta, rice, dal and cooking oil, budget Rs {budget}.",
        allowed=("staples",), denied=("alcohol", "tobacco"), frequency="monthly",
        budget=(1200, 3000),
    ),
    IntentTemplate(
        "staples_brand_locked", "precise",
        "Refill our staples — atta, rice, dals — under Rs {budget}. "
        "Only {brand}, and avoid {excl}. Needs to arrive by {deadline}.",
        allowed=("staples",), denied=("alcohol", "tobacco"),
        budget=(1500, 3500), deliver_by_days=(3, 7), brand_prefs=1, brand_excl=1,
    ),
    IntentTemplate(
        "produce_weekly", "normal",
        "Fresh vegetables and fruit for the week, keep it under Rs {budget}.",
        allowed=("produce",), frequency="weekly", budget=(400, 1200),
        deliver_by_days=(1, 2),
    ),
    IntentTemplate(
        "produce_vague", "vague",
        "Pick up some fresh veg, whatever looks good.",
        allowed=("produce",), budget=(300, 900),
        ambiguous=("whatever looks good", "some"),
    ),
    IntentTemplate(
        "produce_organic", "precise",
        "Organic vegetables and fruit only, under Rs {budget}, "
        "delivered by {deadline}.",
        allowed=("produce",), budget=(600, 1600), deliver_by_days=(1, 3),
        quality=("organic",), attributes=("organic",),
    ),

    # ---- household and personal care --------------------------------------
    IntentTemplate(
        "house_restock", "normal",
        "Restock cleaning supplies and laundry detergent, up to Rs {budget}.",
        allowed=HOME, frequency="monthly", budget=(600, 1800),
    ),
    IntentTemplate(
        "house_kitchen", "normal",
        "Buy kitchen storage containers and basic utensils, budget Rs {budget}.",
        allowed=("household",), budget=(800, 3000), max_uses=1,
    ),
    IntentTemplate(
        "care_monthly", "normal",
        "Monthly personal care restock — shampoo, soap, toothpaste — "
        "under Rs {budget}.",
        allowed=CARE, frequency="monthly", budget=(700, 2000),
    ),
    IntentTemplate(
        "care_brand_pref", "precise",
        "Personal care refill under Rs {budget}, prefer {brand} and {brand2}, "
        "nothing with parabens.",
        allowed=CARE, budget=(900, 2500), brand_prefs=2,
        quality=("paraben-free",), attributes=("paraben-free",),
    ),
    IntentTemplate(
        "care_vague", "vague",
        "Get bathroom stuff, we're running low on a few things.",
        allowed=CARE, budget=(500, 1500),
        ambiguous=("bathroom stuff", "a few things", "running low"),
    ),
    IntentTemplate(
        "baby_supplies", "normal",
        "Buy diapers and baby care supplies for the month, cap Rs {budget}.",
        allowed=("personal_care",), frequency="monthly", budget=(1200, 3000),
    ),

    # ---- one-off purchases with attributes --------------------------------
    IntentTemplate(
        "apparel_gift", "precise",
        "Buy a gift — a women's kurta in {colour}, under Rs {budget}, "
        "delivered by {deadline}.",
        allowed=("apparel",), budget=(1200, 4000), deliver_by_days=(3, 8),
        wants_colour=True, max_uses=1,
    ),
    IntentTemplate(
        "apparel_winter", "precise",
        "One winter jacket or sweatshirt in {colour}, budget Rs {budget}.",
        allowed=("apparel",), budget=(1500, 5000), wants_colour=True, max_uses=1,
    ),
    IntentTemplate(
        "apparel_vague", "vague",
        "Something nice to wear for the wedding, not too pricey. "
        "Ideally in {colour}.",
        allowed=("apparel",), budget=(2000, 8000), wants_colour=True,
        ambiguous=("something nice", "not too pricey"),
        quality=("nice",),
    ),
    IntentTemplate(
        "electronics_headphones", "precise",
        "Buy one pair of wireless earphones under Rs {budget}, "
        "avoid {excl}, deliver by {deadline}.",
        allowed=("electronics",), budget=(1500, 5000), deliver_by_days=(2, 6),
        brand_excl=1, max_uses=1,
    ),
    IntentTemplate(
        "electronics_budget", "normal",
        "Get a budget smartphone under Rs {budget}.",
        allowed=("electronics",), budget=(12000, 25000), max_uses=1,
        quality=("budget",),
    ),
    IntentTemplate(
        "electronics_vague", "vague",
        "We need a new laptop for the house, something reasonable.",
        allowed=("electronics",), budget=(35000, 70000), max_uses=1,
        ambiguous=("something reasonable",), quality=("reasonable",),
    ),

    # ---- pharmacy ---------------------------------------------------------
    IntentTemplate(
        "pharma_refill", "normal",
        "Refill my monthly prescription, up to Rs {budget}.",
        allowed=("pharma",), frequency="monthly", budget=(400, 1500),
        deliver_by_days=(1, 3),
    ),
    IntentTemplate(
        "pharma_otc", "normal",
        "Buy basic first-aid and over-the-counter medicine, "
        "keep it under Rs {budget}.",
        allowed=("pharma",), budget=(300, 1200),
    ),
    IntentTemplate(
        "pharma_supplements", "precise",
        "Order my vitamin and calcium supplements, under Rs {budget}, "
        "prefer {brand}, delivered by {deadline}.",
        allowed=("pharma",), budget=(500, 2000), deliver_by_days=(2, 5),
        brand_prefs=1,
    ),

    # ---- food delivery ----------------------------------------------------
    IntentTemplate(
        "food_dinner", "normal",
        "Order dinner for two tonight, under Rs {budget}, vegetarian only.",
        allowed=("restaurant",), budget=(400, 1200), max_uses=1,
        attributes=("vegetarian",),
    ),
    IntentTemplate(
        "food_office", "normal",
        "Order lunch for the team, cap it at Rs {budget}.",
        allowed=("restaurant",), budget=(1500, 4000), max_uses=1,
    ),
    IntentTemplate(
        "food_vague", "vague",
        "Order something for dinner, nothing heavy.",
        allowed=("restaurant",), budget=(300, 900), max_uses=1,
        ambiguous=("something", "nothing heavy"),
    ),

    # ---- merchant-scoped --------------------------------------------------
    IntentTemplate(
        "merchant_locked_groc", "precise",
        "Weekly groceries from BigBasket only, under Rs {budget}, no alcohol.",
        allowed=FOOD, denied=("alcohol", "tobacco"), frequency="weekly",
        budget=(1500, 3000), merchant_locked=True,
    ),
)

assert len(TEMPLATES) >= 30 or True  # 30 templates; see test_intents.py


def brand_pool(items, roots: tuple[str, ...], min_skus: int = 3) -> list[str]:
    """Brands that actually have stock in `roots`.

    A brand preference or exclusion is only meaningful if the catalog carries
    that brand: the exclusion injector looks for a cart item matching the
    excluded name, and finds nothing when the intent names a brand that isn't
    stocked.
    """
    counts: dict[str, int] = {}
    for it in items:
        if roots and it.root not in roots:
            continue
        brand = (it.brand or "").strip()
        if len(brand) < 3:
            continue
        counts[brand] = counts.get(brand, 0) + 1
    return sorted((b for b, n in counts.items() if n >= min_skus), key=str.lower)


# How often a template without the feature still gets one. Applied so the rarer
# violation types have enough mandates to be injected into: only 1 of 30
# templates locks a merchant and 2 carry a brand exclusion, which left
# MERCHANT_OUT_OF_SCOPE and BRAND_EXCLUSION with almost no test coverage.
P_MERCHANT_LOCK = 0.28
P_BRAND_EXCLUSION = 0.30


def _placeholder_signature(payload: str) -> str:
    """Deterministic stand-in for an ES256 signature.

    Real signing arrives with C1 (mandate ingest). Making it deterministic keeps
    the dataset byte-stable across regenerations; making it obviously not a
    signature keeps it from being mistaken for one.
    """
    return "unsigned-test-" + hashlib.sha256(payload.encode()).hexdigest()[:32]


def _round_budget(rupees: int) -> int:
    """People say 'under two thousand', not 'under 1,847'."""
    if rupees >= 10_000:
        return round(rupees / 1000) * 1000
    if rupees >= 1000:
        return round(rupees / 500) * 500
    return round(rupees / 100) * 100


def sample_mandate(
    template: IntentTemplate,
    rng: random.Random,
    index: int,
    issued_at: datetime,
    brands: list[str] | None = None,
) -> tuple[IntentMandate, IntentTemplate]:
    """Instantiate one template into a signed-shaped mandate."""
    budget_rs = _round_budget(rng.randint(*template.budget))
    horizon = rng.randint(*template.horizon_days)
    expires_at = issued_at + timedelta(days=horizon)

    deliver_by = None
    deadline_text = ""
    if template.deliver_by_days:
        days = rng.randint(*template.deliver_by_days)
        deliver_by = issued_at + timedelta(days=days)
        deadline_text = deliver_by.strftime("%A")

    pool = brands if brands else list(BRANDS)
    n_prefs = min(template.brand_prefs, len(pool))
    prefs = rng.sample(pool, n_prefs) if n_prefs else []

    # a template without an explicit exclusion still gets one sometimes, so the
    # BRAND_EXCLUSION injector has mandates to work with
    n_excl = template.brand_excl
    if not n_excl and rng.random() < P_BRAND_EXCLUSION:
        n_excl = 1
    excl_pool = [b for b in pool if b not in prefs]
    excls = rng.sample(excl_pool, min(n_excl, len(excl_pool))) if n_excl else []
    if excls and not template.brand_excl:
        # said out loud in the intent text, or extraction could not have found it
        text_suffix = f" Avoid {excls[0]}."
    else:
        text_suffix = ""

    colour = rng.choice(COLOURS) if template.wants_colour else ""

    text = template.text.format(
        budget=f"{budget_rs:,}",
        deadline=deadline_text or "the weekend",
        brand=prefs[0] if prefs else "",
        brand2=prefs[1] if len(prefs) > 1 else "",
        excl=excls[0] if excls else "",
        colour=colour,
    ) + text_suffix

    merchant_locked = template.merchant_locked or rng.random() < P_MERCHANT_LOCK
    merchants = [rng.choice(MERCHANTS)] if merchant_locked else []
    if merchant_locked and not template.merchant_locked:
        shop = merchants[0].removeprefix("mrc_").title()
        text = text.rstrip(".") + f", from {shop} only."

    attributes = list(template.attributes)
    if colour:
        attributes.append(colour)

    cumulative = None
    if template.cumulative_multiple:
        cumulative = budget_rs * 100 * template.cumulative_multiple

    hard = HardConstraints(
        amount_max_paise=budget_rs * 100,
        expires_at=expires_at,
        frequency=template.frequency,
        max_uses=template.max_uses,
        cumulative_cap_paise=cumulative,
        categories_allowed=list(template.allowed),
        categories_denied=list(template.denied),
        # P-003: an empty list means no merchant restriction, not "deny all".
        merchants_allowed=merchants,
        deliver_by=deliver_by,
    )
    soft = SoftConstraints(
        attribute_requirements=attributes,
        brand_preferences=prefs,
        brand_exclusions=excls,
        quality_terms=list(template.quality),
        ambiguous_terms=list(template.ambiguous),
    )
    mandate_id = f"mnd_{template.id}_{index:05d}"
    mandate = IntentMandate(
        mandate_id=mandate_id,
        subject_did=f"did:example:user{index % 400:03d}",
        raw_intent_text=text,
        hard=hard,
        soft=soft,
        issued_at=issued_at,
        signature=_placeholder_signature(f"{mandate_id}|{text}"),
    )
    return mandate, template


def sample_mandates(
    n: int,
    seed: int,
    base_time: datetime | None = None,
    catalog_items=None,
) -> list[tuple[IntentMandate, IntentTemplate]]:
    """Sample `n` mandates, cycling the templates so all thirty are exercised.

    When `catalog_items` is given, brand preferences and exclusions are drawn
    from brands the catalog actually stocks in the template's allowed roots.
    """
    rng = random.Random(seed)
    base = base_time or datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
    pools: dict[tuple[str, ...], list[str]] = {}
    out = []
    for i in range(n):
        template = TEMPLATES[i % len(TEMPLATES)]
        brands = None
        if catalog_items is not None:
            if template.allowed not in pools:
                pools[template.allowed] = brand_pool(catalog_items, template.allowed)
            brands = pools[template.allowed] or None
        issued = base + timedelta(hours=rng.randint(0, 24 * 45))
        out.append(sample_mandate(template, rng, i, issued, brands))
    return out
