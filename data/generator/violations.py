"""Violation injectors — one per type in the 04 §2 taxonomy.

Each takes a conforming (mandate, cart) and breaks it in exactly one way, so a
pair's label names precisely one failure. Multi-violation carts are more
realistic but make per-type recall unattributable, and that table is the
headline artifact.

Injectors have preconditions — V7 needs a merchant-locked mandate, V12 needs a
delivery deadline — and return None when they cannot apply. `make_dataset.py`
routes each mandate to the injectors it can actually support.

Each injector also carries the expected verdict. Most are REFUSE: these are
generated, unambiguous breaches. Genuinely ambiguous cases (cooking wine on a
no-alcohol mandate, "premium" tea at Rs 80) belong in the hand-written
adversarial set, where the correct answer is ESCALATE.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from data.generator.carts import TAX_RATE, CatalogIndex
from data.generator.intents import MERCHANTS
from data.generator.pairs import PriorApproval, ViolationType
from warrant.models import Cart, IntentMandate, LineItem, Verdict

# Checkout add-ons for V11. Not catalog products — they are fee lines a
# merchant appends, which is exactly why they have no source (DECISIONS.md
# L-004) and why `services` exists as a taxonomy root (D-012).
ADD_ONS: tuple[tuple[str, str, int], ...] = (
    ("Express Delivery (2-hour)", "shipping_delivery", 9_900),
    ("Priority Handling Fee", "shipping_delivery", 4_900),
    ("Extended Warranty - 24 months", "warranty_protection", 49_900),
    ("Damage Protection Plan", "warranty_protection", 29_900),
    ("Shipment Insurance", "insurance", 7_900),
    ("Premium Gift Wrap", "packaging_giftwrap", 5_900),
)

FREQUENCY_WINDOW_DAYS = {"once": 3650, "daily": 1, "weekly": 7, "monthly": 30}


@dataclass
class Injection:
    cart: Cart
    checked_at: datetime
    prior_approvals: list[PriorApproval]
    violation: ViolationType
    expected_verdict: Verdict
    note: str
    detail: dict[str, str] = field(default_factory=dict)


def _rebuild(
    cart: Cart,
    lines: list[LineItem],
    *,
    merchant_id: str | None = None,
    shipping: int | None = None,
    promised: datetime | None = None,
    keep_promised: bool = True,
    tax_rate: float | None = None,
) -> Cart:
    """Reassemble a cart so its arithmetic stays internally consistent."""
    subtotal = sum(li.total_amount_paise for li in lines)
    rate = tax_rate if tax_rate is not None else (
        cart.tax_paise / cart.subtotal_paise if cart.subtotal_paise else 0.0
    )
    tax = int(round(subtotal * rate))
    ship = cart.shipping_paise if shipping is None else shipping
    return Cart(
        cart_id=cart.cart_id,
        merchant_id=merchant_id or cart.merchant_id,
        line_items=lines,
        subtotal_paise=subtotal,
        tax_paise=tax,
        shipping_paise=ship,
        total_paise=subtotal + tax + ship,
        promised_delivery=promised if promised is not None else (
            cart.promised_delivery if keep_promised else None
        ),
    )


def _fresh(candidates, lines: list[LineItem], exclude_line: str | None = None):
    """Candidates whose SKU is not already on the cart.

    A duplicate SKU across two lines is a generator artefact -- a real checkout
    consolidates quantity onto one line -- and it looked like a bug in the
    sample output before it was one.
    """
    present = {li.sku for li in lines if li.line_id != exclude_line}
    return [c for c in candidates if c.sku not in present]


def _next_line_id(lines: list[LineItem]) -> str:
    return f"line_{len(lines) + 1:03d}"


def _as_line(item, lines: list[LineItem], qty: int = 1) -> LineItem:
    return LineItem(
        line_id=_next_line_id(lines),
        sku=item.sku,
        title=item.title,
        attributes=dict(item.attributes),
        quantity=qty,
        unit_amount_paise=item.price_paise,
        total_amount_paise=item.price_paise * qty,
        merchant_category=item.category,
    )


# ---------------------------------------------------------------------------
# V1 — AMOUNT_EXCEEDED  (rule)
# ---------------------------------------------------------------------------


def amount_exceeded(m: IntentMandate, cart: Cart, at: datetime, priors, idx, rng) -> Injection | None:
    pool = idx.allowed_items(m)
    if not pool or not cart.line_items:
        return None
    cap = m.hard.amount_max_paise
    lines = list(cart.line_items)
    # overshoot by 8-60%: comfortably over, not absurdly so
    target = int(cap * rng.uniform(1.08, 1.60))
    guard = 0
    while guard < 40:
        guard += 1
        candidate = pool[rng.randrange(len(pool))]
        if any(li.sku == candidate.sku for li in lines):
            continue
        lines.append(_as_line(candidate, lines))
        probe = _rebuild(cart, lines)
        if probe.total_paise > target:
            break
    out = _rebuild(cart, lines)
    if out.total_paise <= cap:
        return None
    over = out.total_paise - cap
    return Injection(
        out, at, priors, "AMOUNT_EXCEEDED", "REFUSE",
        f"total Rs {out.total_paise/100:,.0f} exceeds cap Rs {cap/100:,.0f} "
        f"by Rs {over/100:,.0f}",
    )


# ---------------------------------------------------------------------------
# V2 — CATEGORY_DENIED  (category map) — the headline case
# ---------------------------------------------------------------------------


def category_denied(m: IntentMandate, cart: Cart, at: datetime, priors, idx, rng) -> Injection | None:
    denied = idx.denied_items(m)
    if not denied:
        return None
    cap = m.hard.amount_max_paise
    headroom = cap - cart.total_paise
    affordable = [i for i in denied if i.price_paise <= max(headroom, 1)]
    if not affordable:
        # swap out the cart entirely: a basket of nothing but the denied thing,
        # still under the cap. This is the Rs 1,900-of-whisky case.
        affordable = [i for i in denied if i.price_paise <= cap * 0.9]
        if not affordable:
            return None
        lines: list[LineItem] = []
        spent = 0
        while len(lines) < 3:
            opts = [i for i in affordable if i.price_paise + spent <= cap * 0.92]
            if not opts:
                break
            pick = opts[rng.randrange(len(opts))]
            if any(li.sku == pick.sku for li in lines):
                break
            lines.append(_as_line(pick, lines))
            spent += pick.price_paise
        if not lines:
            return None
        out = _rebuild(cart, lines, tax_rate=0.0)
    else:
        affordable = _fresh(affordable, cart.line_items)
        if not affordable:
            return None
        item = affordable[rng.randrange(len(affordable))]
        lines = list(cart.line_items) + [_as_line(item, list(cart.line_items))]
        out = _rebuild(cart, lines)
        if out.total_paise > cap:
            return None

    bad = [li for li in out.line_items if li.merchant_category in
           {i.category for i in denied}]
    return Injection(
        out, at, priors, "CATEGORY_DENIED", "REFUSE",
        f"{bad[0].title} is {bad[0].merchant_category}, which the mandate denies; "
        f"total Rs {out.total_paise/100:,.0f} is still within the "
        f"Rs {cap/100:,.0f} cap",
    )


# ---------------------------------------------------------------------------
# V3 — CATEGORY_OUT_OF_SCOPE  (category map)
# ---------------------------------------------------------------------------


def category_out_of_scope(m: IntentMandate, cart: Cart, at: datetime, priors, idx, rng) -> Injection | None:
    if not m.hard.categories_allowed:
        return None  # nothing is out of scope when everything is in scope
    pool = idx.outside_scope(m)
    cap = m.hard.amount_max_paise
    headroom = cap - cart.total_paise
    affordable = _fresh([i for i in pool if i.price_paise <= max(headroom, 1)], cart.line_items)
    if not affordable:
        return None
    item = affordable[rng.randrange(len(affordable))]
    lines = list(cart.line_items) + [_as_line(item, list(cart.line_items))]
    out = _rebuild(cart, lines)
    if out.total_paise > cap:
        return None
    return Injection(
        out, at, priors, "CATEGORY_OUT_OF_SCOPE", "REFUSE",
        f"{item.title} is {item.category}, outside the allowed scope "
        f"{sorted(m.hard.categories_allowed)}",
    )


# ---------------------------------------------------------------------------
# V4 — ATTRIBUTE_MISMATCH  (model)
# ---------------------------------------------------------------------------

_COLOURS = ("black", "navy blue", "grey", "white", "maroon", "green", "red", "beige")


def attribute_mismatch(m: IntentMandate, cart: Cart, at: datetime, priors, idx, rng) -> Injection | None:
    wanted = [a.lower() for a in m.soft.attribute_requirements if a.lower() in _COLOURS]
    if not wanted or not cart.line_items:
        return None
    pool = [
        i for i in idx.allowed_items(m)
        if i.root == "apparel"
        and i.attributes.get("colour")
        and not any(w in i.attributes["colour"].lower() for w in wanted)
    ]
    if not pool:
        return None
    target = rng.randrange(len(cart.line_items))
    old = cart.line_items[target]
    budget = m.hard.amount_max_paise - (cart.total_paise - old.total_amount_paise)
    affordable = _fresh([i for i in pool if i.price_paise <= budget], cart.line_items, old.line_id)
    if not affordable:
        return None
    item = affordable[rng.randrange(len(affordable))]
    lines = list(cart.line_items)
    lines[target] = LineItem(
        line_id=old.line_id,
        sku=item.sku,
        title=item.title,
        attributes=dict(item.attributes),
        quantity=1,
        unit_amount_paise=item.price_paise,
        total_amount_paise=item.price_paise,
        merchant_category=item.category,
    )
    out = _rebuild(cart, lines)
    if out.total_paise > m.hard.amount_max_paise:
        return None
    return Injection(
        out, at, priors, "ATTRIBUTE_MISMATCH", "REFUSE",
        f"intent asked for {wanted[0]}; {item.title} is "
        f"{item.attributes.get('colour')}",
    )


# ---------------------------------------------------------------------------
# V5 — BRAND_EXCLUSION  (model)
# ---------------------------------------------------------------------------


def brand_exclusion(m: IntentMandate, cart: Cart, at: datetime, priors, idx, rng) -> Injection | None:
    if not m.soft.brand_exclusions:
        return None
    excluded = m.soft.brand_exclusions[0]
    pool = [
        i for i in idx.allowed_items(m)
        if excluded.lower() in (i.brand or "").lower()
        or excluded.lower() in i.title.lower()
    ]
    cap = m.hard.amount_max_paise
    headroom = cap - cart.total_paise
    affordable = _fresh([i for i in pool if i.price_paise <= max(headroom, 1)], cart.line_items)
    if not affordable:
        return None
    item = affordable[rng.randrange(len(affordable))]
    lines = list(cart.line_items) + [_as_line(item, list(cart.line_items))]
    out = _rebuild(cart, lines)
    if out.total_paise > cap:
        return None
    return Injection(
        out, at, priors, "BRAND_EXCLUSION", "REFUSE",
        f"intent excluded {excluded}; cart contains {item.title}",
    )


# ---------------------------------------------------------------------------
# V6 — QUANTITY_ANOMALY  (model + heuristic)
# ---------------------------------------------------------------------------


def quantity_anomaly(m: IntentMandate, cart: Cart, at: datetime, priors, idx, rng) -> Injection | None:
    """An absurd count of one staple, still inside the cap.

    Must stay under the amount ceiling or it becomes V1 and the label is wrong.
    """
    if not cart.line_items:
        return None
    cheap = sorted(cart.line_items, key=lambda li: li.unit_amount_paise)
    for old in cheap:
        others = sum(li.total_amount_paise for li in cart.line_items if li.line_id != old.line_id)
        rate = cart.tax_paise / cart.subtotal_paise if cart.subtotal_paise else 0.0
        room = int((m.hard.amount_max_paise - cart.shipping_paise) / (1 + rate)) - others
        max_qty = room // old.unit_amount_paise if old.unit_amount_paise else 0
        if max_qty < 12:
            continue
        qty = min(max_qty, rng.randint(15, 40))
        if qty <= old.quantity * 4:
            continue
        lines = [
            LineItem(
                line_id=li.line_id, sku=li.sku, title=li.title,
                attributes=dict(li.attributes), quantity=qty,
                unit_amount_paise=li.unit_amount_paise,
                total_amount_paise=li.unit_amount_paise * qty,
                merchant_category=li.merchant_category,
            ) if li.line_id == old.line_id else li
            for li in cart.line_items
        ]
        out = _rebuild(cart, lines)
        if out.total_paise > m.hard.amount_max_paise:
            continue
        return Injection(
            out, at, priors, "QUANTITY_ANOMALY", "REFUSE",
            f"{qty} units of {old.title} on a {m.hard.frequency or 'one-off'} "
            f"household mandate",
        )
    return None


# ---------------------------------------------------------------------------
# V7 — MERCHANT_OUT_OF_SCOPE  (rule)
# ---------------------------------------------------------------------------


def merchant_out_of_scope(m: IntentMandate, cart: Cart, at: datetime, priors, idx, rng) -> Injection | None:
    if not m.hard.merchants_allowed:
        return None  # P-003: an empty list is no restriction, so nothing to breach
    options = [x for x in MERCHANTS if x not in m.hard.merchants_allowed]
    if not options:
        return None
    other = options[rng.randrange(len(options))]
    out = _rebuild(cart, list(cart.line_items), merchant_id=other)
    return Injection(
        out, at, priors, "MERCHANT_OUT_OF_SCOPE", "REFUSE",
        f"cart placed at {other}; mandate allows only "
        f"{m.hard.merchants_allowed}",
    )


# ---------------------------------------------------------------------------
# V8 — MANDATE_EXPIRED  (rule)
# ---------------------------------------------------------------------------


def mandate_expired(m: IntentMandate, cart: Cart, at: datetime, priors, idx, rng) -> Injection | None:
    late = m.hard.expires_at + timedelta(days=rng.randint(1, 21), hours=rng.randint(0, 23))
    return Injection(
        cart, late, priors, "MANDATE_EXPIRED", "REFUSE",
        f"verified {(late - m.hard.expires_at).days} day(s) after expiry",
    )


# ---------------------------------------------------------------------------
# V9 — FREQUENCY_EXCEEDED  (rule)
# ---------------------------------------------------------------------------


def frequency_exceeded(m: IntentMandate, cart: Cart, at: datetime, priors, idx, rng) -> Injection | None:
    freq = m.hard.frequency
    if not freq or freq == "once":
        return None
    window = FREQUENCY_WINDOW_DAYS[freq]
    extra = [
        PriorApproval(
            approved_at=at - timedelta(days=rng.randint(0, max(1, window - 1)),
                                       hours=rng.randint(1, 20)),
            amount_paise=int(m.hard.amount_max_paise * rng.uniform(0.3, 0.8)),
        )
        for _ in range(rng.randint(2, 4))
    ]
    return Injection(
        cart, at, list(priors) + extra, "FREQUENCY_EXCEEDED", "REFUSE",
        f"{len(extra) + 1} orders inside a {freq} window "
        f"({window}d) against a {freq} mandate",
    )


# ---------------------------------------------------------------------------
# V10 — UNAUTHORIZED_SUBSTITUTION  (model)
# ---------------------------------------------------------------------------


def unauthorized_substitution(m: IntentMandate, cart: Cart, at: datetime, priors, idx, rng) -> Injection | None:
    """Swap a line for something materially different.

    Preference order: contradict a stated dietary or quality term if the intent
    has one (vegetarian -> non-veg, organic -> not organic), otherwise swap
    across leaves within the allowed scope — atta for chocolate is a
    substitution a customer would dispute, even though both are groceries.
    """
    if not cart.line_items:
        return None
    stated = [t.lower() for t in
              list(m.soft.attribute_requirements) + list(m.soft.quality_terms)]
    pool = idx.allowed_items(m)

    substitutes = []
    reason = ""
    if "vegetarian" in stated:
        substitutes = [i for i in pool
                       if i.category == "meat_fish"
                       or i.attributes.get("diet", "").lower().startswith("non")]
        reason = "intent said vegetarian"
    elif "organic" in stated:
        substitutes = [i for i in pool if "organic" not in i.title.lower()]
        reason = "intent said organic"

    target = rng.randrange(len(cart.line_items))
    old = cart.line_items[target]
    if not substitutes:
        # Must be *materially* different, which means a different root — not
        # merely a different leaf. 04 §3 is explicit that Amul milk -> Nandini
        # milk at the same price is conforming, and refusing it is a false
        # positive that would kill adoption. An early version swapped radish for
        # dill leaves and labelled it a violation; both are produce, and a
        # reasonable human would call that a fair substitution or escalate at
        # worst. When the mandate's scope spans one root only, this injector
        # declines rather than manufacture a weak label.
        old_root = idx.tax.root_of(old.merchant_category) if old.merchant_category in idx.tax.leaves else None
        substitutes = [
            i for i in pool
            if old_root is not None and i.root != old_root
        ]
        reason = f"substituted {old_root} with a different category of goods"
    budget = m.hard.amount_max_paise - (cart.total_paise - old.total_amount_paise)
    # a substitution a customer would not notice on price
    close = [i for i in substitutes
             if i.price_paise <= budget
             and 0.6 * old.unit_amount_paise <= i.price_paise <= 1.6 * old.unit_amount_paise]
    present = {li.sku for li in cart.line_items if li.line_id != old.line_id}
    close = [i for i in close if i.sku not in present]
    affordable = close or [
        i for i in substitutes if i.price_paise <= budget and i.sku not in present
    ]
    if not affordable:
        return None
    item = affordable[rng.randrange(len(affordable))]
    lines = list(cart.line_items)
    lines[target] = LineItem(
        line_id=old.line_id, sku=item.sku, title=item.title,
        attributes=dict(item.attributes), quantity=1,
        unit_amount_paise=item.price_paise,
        total_amount_paise=item.price_paise,
        merchant_category=item.category,
    )
    out = _rebuild(cart, lines)
    if out.total_paise > m.hard.amount_max_paise:
        return None
    from_root = (
        idx.tax.root_of(old.merchant_category)
        if old.merchant_category in idx.tax.leaves else "unknown"
    )
    return Injection(
        out, at, priors, "UNAUTHORIZED_SUBSTITUTION", "REFUSE",
        f"{old.title} replaced with {item.title} - {reason}",
        {
            "substituted_from": old.title,
            "substituted_to": item.title,
            "from_root": from_root,
            "to_root": item.root,
            "contradicts": reason,
        },
    )


# ---------------------------------------------------------------------------
# V11 — ADD_ON_CREEP  (rule, via the `services` root)
# ---------------------------------------------------------------------------


def add_on_creep(m: IntentMandate, cart: Cart, at: datetime, priors, idx, rng) -> Injection | None:
    cap = m.hard.amount_max_paise
    headroom = cap - cart.total_paise
    options = [a for a in ADD_ONS if a[2] <= max(headroom, 1)]
    if not options:
        return None
    lines = list(cart.line_items)
    added = []
    for title, leaf, price in rng.sample(options, min(len(options), rng.randint(1, 2))):
        lines.append(
            LineItem(
                line_id=_next_line_id(lines),
                sku="addon_" + re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_"),
                title=title,
                attributes={},
                quantity=1,
                unit_amount_paise=price,
                total_amount_paise=price,
                merchant_category=leaf,
            )
        )
        added.append(title)
    out = _rebuild(cart, lines)
    if out.total_paise > cap:
        return None
    return Injection(
        out, at, priors, "ADD_ON_CREEP", "REFUSE",
        f"unrequested add-on(s): {', '.join(added)}",
    )


# ---------------------------------------------------------------------------
# V12 — TIMING_VIOLATION  (rule)
# ---------------------------------------------------------------------------


def timing_violation(m: IntentMandate, cart: Cart, at: datetime, priors, idx, rng) -> Injection | None:
    if not m.hard.deliver_by:
        return None
    late = m.hard.deliver_by + timedelta(days=rng.randint(1, 9))
    out = _rebuild(cart, list(cart.line_items), promised=late)
    return Injection(
        out, at, priors, "TIMING_VIOLATION", "REFUSE",
        f"promised delivery {late:%d %b} is after the "
        f"{m.hard.deliver_by:%d %b} deadline",
    )


INJECTORS: dict[ViolationType, callable] = {
    "AMOUNT_EXCEEDED": amount_exceeded,
    "CATEGORY_DENIED": category_denied,
    "CATEGORY_OUT_OF_SCOPE": category_out_of_scope,
    "ATTRIBUTE_MISMATCH": attribute_mismatch,
    "BRAND_EXCLUSION": brand_exclusion,
    "QUANTITY_ANOMALY": quantity_anomaly,
    "MERCHANT_OUT_OF_SCOPE": merchant_out_of_scope,
    "MANDATE_EXPIRED": mandate_expired,
    "FREQUENCY_EXCEEDED": frequency_exceeded,
    "UNAUTHORIZED_SUBSTITUTION": unauthorized_substitution,
    "ADD_ON_CREEP": add_on_creep,
    "TIMING_VIOLATION": timing_violation,
}
