"""Conforming cart synthesis.

Given a mandate, build a cart that honours it. Everything downstream is a
mutation of one of these: `violations.py` takes a conforming cart and breaks it
in exactly one way, so if a cart out of here is subtly non-conforming, the
labels are wrong and every metric inherits the error.

Carts are built to sit at 55-85% of the cap rather than hugging it. A generator
that always lands at 99% of the ceiling would make the amount check trivially
easy and would not resemble real baskets — but one of the adversarial cases in
04 §3 is a cart at Rs 1,999 against a Rs 2,000 cap that must still be allowed,
so `tight=True` produces exactly that.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from data.generator.catalog import CatalogItem
from data.generator.intents import MERCHANTS, IntentTemplate
from warrant.models import Cart, IntentMandate, LineItem
from warrant.taxonomy import Taxonomy, default_taxonomy

# GST bands. Food and unbranded staples sit low; electronics and apparel high.
TAX_RATE = {
    "produce": 0.0,
    "staples": 0.05,
    "grocery": 0.05,
    "restaurant": 0.05,
    "pharma": 0.12,
    "household": 0.18,
    "personal_care": 0.18,
    "apparel": 0.12,
    "electronics": 0.18,
    "alcohol": 0.0,   # state excise, outside GST
    "services": 0.18,
}

SHIPPING_OPTIONS = (0, 0, 0, 2_000, 3_000, 4_900)  # paise


class CatalogIndex:
    """Catalog grouped for fast, deterministic selection."""

    def __init__(self, items: list[CatalogItem], taxonomy: Taxonomy | None = None):
        self.tax = taxonomy or default_taxonomy()
        self.items = items
        self.by_leaf: dict[str, list[CatalogItem]] = {}
        self.by_root: dict[str, list[CatalogItem]] = {}
        for it in items:
            self.by_leaf.setdefault(it.category, []).append(it)
            self.by_root.setdefault(it.root, []).append(it)
        for bucket in (self.by_leaf, self.by_root):
            for k in bucket:
                bucket[k].sort(key=lambda i: i.sku)

    def allowed_items(self, mandate: IntentMandate) -> list[CatalogItem]:
        hard = mandate.hard
        allowed = (
            self.tax.expand(hard.categories_allowed)
            if hard.categories_allowed
            else set(self.tax.leaf_ids)
        )
        denied = self.tax.expand(hard.categories_denied) if hard.categories_denied else set()
        # `services` is never implicitly in scope; add-ons must be asked for
        allowed -= denied | set(self.tax.roots["services"].leaf_ids)
        out = [i for i in self.items if i.category in allowed]
        return sorted(out, key=lambda i: i.sku)

    def outside_scope(self, mandate: IntentMandate) -> list[CatalogItem]:
        """Items in no denied category but outside what was allowed — V3."""
        hard = mandate.hard
        allowed = (
            self.tax.expand(hard.categories_allowed)
            if hard.categories_allowed
            else set(self.tax.leaf_ids)
        )
        denied = self.tax.expand(hard.categories_denied) if hard.categories_denied else set()
        pool = [
            i for i in self.items
            if i.category not in allowed
            and i.category not in denied
            and i.root != "services"
        ]
        return sorted(pool, key=lambda i: i.sku)

    def denied_items(self, mandate: IntentMandate) -> list[CatalogItem]:
        """Items explicitly forbidden by the mandate — V2, the whisky case."""
        denied = (
            self.tax.expand(mandate.hard.categories_denied)
            if mandate.hard.categories_denied
            else set()
        )
        return sorted((i for i in self.items if i.category in denied), key=lambda i: i.sku)


def _quantity(rng: random.Random, item: CatalogItem) -> int:
    """Household-plausible quantities. Most lines are one unit."""
    if item.root in ("produce", "grocery", "staples"):
        return rng.choices([1, 1, 1, 2, 2, 3], k=1)[0]
    if item.root in ("apparel", "electronics"):
        return 1
    return rng.choices([1, 1, 1, 2], k=1)[0]


def _matches_soft_preferences(item: CatalogItem, mandate: IntentMandate) -> bool:
    """Soft constraints are preferences, but a *conforming* cart honours them.

    Brand exclusions are the sharp edge: a cart containing an excluded brand is
    V5, so a conforming cart must never contain one, even by accident.
    """
    soft = mandate.soft
    brand = (item.brand or "").lower()
    title = item.title.lower()
    for excluded in soft.brand_exclusions:
        if excluded.lower() in brand or excluded.lower() in title:
            return False
    wanted_colours = [
        a.lower() for a in soft.attribute_requirements
        if a.lower() in (
            "black", "navy blue", "grey", "white", "maroon",
            "green", "red", "beige",
        )
    ]
    if wanted_colours and item.root == "apparel":
        colour = item.attributes.get("colour", "").lower()
        if colour and not any(c in colour or colour in c for c in wanted_colours):
            return False
    return True


def build_conforming_cart(
    mandate: IntentMandate,
    template: IntentTemplate,
    index: CatalogIndex,
    rng: random.Random,
    cart_id: str,
    tight: bool = False,
) -> Cart | None:
    """Synthesise a cart that honours `mandate`, or None if the catalog can't."""
    pool = [i for i in index.allowed_items(mandate) if _matches_soft_preferences(i, mandate)]
    if not pool:
        return None

    cap = mandate.hard.amount_max_paise
    root = pool[0].root
    tax_rate = TAX_RATE.get(root, 0.05)
    shipping = 0 if tight else rng.choice(SHIPPING_OPTIONS)

    # work backwards from the cap so tax and shipping never push us over
    fill = rng.uniform(0.93, 0.985) if tight else rng.uniform(0.55, 0.85)
    subtotal_budget = int((cap * fill - shipping) / (1 + tax_rate))
    if subtotal_budget <= 0:
        return None

    affordable = [i for i in pool if i.price_paise <= subtotal_budget]
    if not affordable:
        return None

    lines: list[LineItem] = []
    spent = 0
    max_lines = 1 if template.max_uses == 1 and root in ("apparel", "electronics") else rng.randint(3, 9)

    for attempt in range(max_lines * 6):
        if len(lines) >= max_lines:
            break
        remaining = subtotal_budget - spent
        options = [i for i in affordable if i.price_paise <= remaining]
        if not options:
            break
        item = options[rng.randrange(len(options))]
        qty = _quantity(rng, item)
        while qty > 1 and item.price_paise * qty > remaining:
            qty -= 1
        total = item.price_paise * qty
        if total > remaining:
            continue
        if any(li.sku == item.sku for li in lines):
            continue
        lines.append(
            LineItem(
                line_id=f"line_{len(lines) + 1:03d}",
                sku=item.sku,
                title=item.title,
                description=None,
                attributes=dict(item.attributes),
                quantity=qty,
                unit_amount_paise=item.price_paise,
                total_amount_paise=total,
                merchant_category=item.category,
            )
        )
        spent += total

    if not lines:
        return None

    subtotal = sum(li.total_amount_paise for li in lines)
    tax = int(round(subtotal * tax_rate))
    total = subtotal + tax + shipping
    if total > cap:
        return None

    merchant = (
        rng.choice(mandate.hard.merchants_allowed)
        if mandate.hard.merchants_allowed
        else rng.choice(MERCHANTS)
    )

    promised = None
    if mandate.hard.deliver_by:
        # comfortably inside the window, never on the boundary
        window = (mandate.hard.deliver_by - mandate.issued_at).days
        promised = mandate.issued_at + timedelta(
            days=max(1, rng.randint(1, max(1, window - 1)))
        )

    return Cart(
        cart_id=cart_id,
        merchant_id=merchant,
        line_items=lines,
        subtotal_paise=subtotal,
        tax_paise=tax,
        shipping_paise=shipping,
        total_paise=total,
        promised_delivery=promised,
    )


def checked_at_for(mandate: IntentMandate, rng: random.Random) -> datetime:
    """A verification time inside the mandate's validity window."""
    span = (mandate.hard.expires_at - mandate.issued_at).days
    offset = rng.randint(0, max(0, span - 1))
    return mandate.issued_at + timedelta(days=offset, hours=rng.randint(0, 12))
