"""Dataset integrity tests — an independent audit of the generator's labels.

The checks here are written against the *mandate's own constraints*, not
against the generator's internals. If a pair labelled `conforming` breaches a
hard constraint, the label is wrong, and every metric computed later inherits
the error. This is the cheapest defence available against the criticism in
07 §R2 that the data was shaped to flatter the system.
"""

from __future__ import annotations

from collections import Counter

import pytest

from warrant.taxonomy import default_taxonomy

make_dataset = pytest.importorskip("data.generator.make_dataset")
from data.generator.pairs import ALL_VIOLATIONS, RESOLVED_BY  # noqa: E402

FREQ_WINDOW = {"once": 3650, "daily": 1, "weekly": 7, "monthly": 30}


@pytest.fixture(scope="module")
def splits():
    try:
        return make_dataset.build()
    except FileNotFoundError as exc:
        pytest.skip(f"catalog not built: {exc}")


@pytest.fixture(scope="module")
def every_pair(splits):
    return [p for pairs in splits.values() for p in pairs]


# ---------------------------------------------------------------------------
# split hygiene — rule 4: never touch the test split
# ---------------------------------------------------------------------------


def test_no_mandate_straddles_two_splits(splits) -> None:
    """The leak the by-mandate split exists to prevent.

    Carts from one mandate share its constraints and its intent text, so a
    mandate appearing in both train and test would mean tuning on the exact
    case later scored against.
    """
    seen: dict[str, str] = {}
    for name, pairs in splits.items():
        for p in pairs:
            mid = p.mandate.mandate_id
            assert seen.setdefault(mid, name) == name, f"{mid} in both {seen[mid]} and {name}"


def test_no_cart_holds_the_same_sku_twice(every_pair) -> None:
    """A real checkout consolidates quantity onto one line.

    Duplicate lines were a generator artefact from injectors appending an item
    the cart already held, and from two add-ons sharing a category-derived SKU.
    """
    for p in every_pair:
        skus = [li.sku for li in p.cart.line_items]
        assert len(skus) == len(set(skus)), p.pair_id


def test_no_cart_or_pair_id_repeats(every_pair) -> None:
    for field in ("pair_id",):
        ids = [getattr(p, field) for p in every_pair]
        assert len(ids) == len(set(ids))
    carts = [p.cart.cart_id for p in every_pair]
    assert len(carts) == len(set(carts))


def test_split_proportions_are_roughly_60_20_20(splits) -> None:
    total = sum(len(v) for v in splits.values())
    assert 0.55 <= len(splits["train"]) / total <= 0.65
    for name in ("validation", "test"):
        assert 0.15 <= len(splits[name]) / total <= 0.25


# ---------------------------------------------------------------------------
# label integrity — conforming carts must actually conform
# ---------------------------------------------------------------------------


def test_conforming_carts_are_within_the_amount_cap(splits) -> None:
    for pairs in splits.values():
        for p in pairs:
            if p.label == "conforming":
                assert p.cart.total_paise <= p.mandate.hard.amount_max_paise, p.pair_id


def test_conforming_carts_are_checked_before_expiry(every_pair) -> None:
    for p in every_pair:
        if p.label == "conforming":
            assert p.checked_at < p.mandate.hard.expires_at, p.pair_id


def test_conforming_carts_contain_no_denied_category(every_pair) -> None:
    """The whisky check, run against the labels themselves."""
    tax = default_taxonomy()
    for p in every_pair:
        if p.label != "conforming":
            continue
        denied = tax.expand(p.mandate.hard.categories_denied) if p.mandate.hard.categories_denied else set()
        for li in p.cart.line_items:
            assert li.merchant_category not in denied, f"{p.pair_id}: {li.title}"


def test_conforming_carts_stay_inside_the_allowed_scope(every_pair) -> None:
    tax = default_taxonomy()
    for p in every_pair:
        if p.label != "conforming" or not p.mandate.hard.categories_allowed:
            continue
        allowed = tax.expand(p.mandate.hard.categories_allowed)
        for li in p.cart.line_items:
            assert li.merchant_category in allowed, f"{p.pair_id}: {li.title}"


def test_conforming_carts_use_an_allowed_merchant(every_pair) -> None:
    for p in every_pair:
        if p.label == "conforming" and p.mandate.hard.merchants_allowed:
            assert p.cart.merchant_id in p.mandate.hard.merchants_allowed, p.pair_id


def test_conforming_carts_meet_the_delivery_deadline(every_pair) -> None:
    for p in every_pair:
        if p.label != "conforming":
            continue
        by = p.mandate.hard.deliver_by
        if by and p.cart.promised_delivery:
            assert p.cart.promised_delivery <= by, p.pair_id


def test_conforming_carts_contain_no_unrequested_add_ons(every_pair) -> None:
    """`services` lines are never implicitly in scope — the V11 mirror image."""
    tax = default_taxonomy()
    services = set(tax.roots["services"].leaf_ids)
    for p in every_pair:
        if p.label == "conforming":
            for li in p.cart.line_items:
                assert li.merchant_category not in services, f"{p.pair_id}: {li.title}"


def test_conforming_carts_avoid_excluded_brands(every_pair) -> None:
    for p in every_pair:
        if p.label != "conforming":
            continue
        for excluded in p.mandate.soft.brand_exclusions:
            for li in p.cart.line_items:
                assert excluded.lower() not in li.title.lower(), f"{p.pair_id}: {li.title}"


def test_conforming_carts_respect_the_frequency_window(every_pair) -> None:
    for p in every_pair:
        if p.label != "conforming" or not p.mandate.hard.frequency:
            continue
        window = FREQ_WINDOW[p.mandate.hard.frequency]
        recent = [
            a for a in p.prior_approvals
            if (p.checked_at - a.approved_at).days < window
        ]
        assert not recent, p.pair_id


# ---------------------------------------------------------------------------
# label integrity — violating carts must actually violate, and only in one way
# ---------------------------------------------------------------------------


def test_violating_pairs_name_exactly_one_type(every_pair) -> None:
    """Multi-violation carts make per-type recall unattributable."""
    for p in every_pair:
        if p.label == "violating":
            assert len(p.violation_types) == 1, p.pair_id


def test_amount_violations_actually_exceed_the_cap(every_pair) -> None:
    for p in every_pair:
        if "AMOUNT_EXCEEDED" in p.violation_types:
            assert p.cart.total_paise > p.mandate.hard.amount_max_paise, p.pair_id


def test_category_violations_stay_within_the_cap(every_pair) -> None:
    """The headline case only lands if the amount check passes.

    A denied-category cart that also breaches the cap would be caught by the
    baseline, and would prove nothing about the gap this project exists to
    close.
    """
    for p in every_pair:
        if {"CATEGORY_DENIED", "CATEGORY_OUT_OF_SCOPE"} & set(p.violation_types):
            assert p.cart.total_paise <= p.mandate.hard.amount_max_paise, p.pair_id


def test_denied_category_violations_contain_a_denied_item(every_pair) -> None:
    tax = default_taxonomy()
    for p in every_pair:
        if "CATEGORY_DENIED" not in p.violation_types:
            continue
        denied = tax.expand(p.mandate.hard.categories_denied)
        assert any(li.merchant_category in denied for li in p.cart.line_items), p.pair_id


def test_expiry_violations_are_checked_after_expiry(every_pair) -> None:
    for p in every_pair:
        if "MANDATE_EXPIRED" in p.violation_types:
            assert p.checked_at >= p.mandate.hard.expires_at, p.pair_id


def test_merchant_violations_use_a_disallowed_merchant(every_pair) -> None:
    for p in every_pair:
        if "MERCHANT_OUT_OF_SCOPE" in p.violation_types:
            allowed = p.mandate.hard.merchants_allowed
            assert allowed, p.pair_id
            assert p.cart.merchant_id not in allowed, p.pair_id


def test_timing_violations_miss_the_deadline(every_pair) -> None:
    for p in every_pair:
        if "TIMING_VIOLATION" in p.violation_types:
            assert p.cart.promised_delivery > p.mandate.hard.deliver_by, p.pair_id


def test_substitutions_are_materially_different(every_pair) -> None:
    """Guards the label-quality bug found in review.

    An early injector swapped radish for dill leaves and called it a violation.
    Both are produce, and 04 §3 is explicit that an equivalent substitution is
    conforming — refusing it is a false positive that would kill adoption. A
    substitution only counts when it crosses a root or contradicts a stated
    dietary or quality term.
    """
    tax = default_taxonomy()
    for p in every_pair:
        if "UNAUTHORIZED_SUBSTITUTION" not in p.violation_types:
            continue
        detail = p.violation_detail
        assert detail, f"{p.pair_id}: no structured detail recorded"
        if detail["contradicts"].startswith("intent said"):
            continue  # contradicting a stated term is material regardless of root
        assert detail["from_root"] != detail["to_root"], (
            f"{p.pair_id}: {detail['substituted_from']} -> "
            f"{detail['substituted_to']} stayed inside {detail['from_root']}"
        )


def test_add_on_violations_carry_a_services_line(every_pair) -> None:
    tax = default_taxonomy()
    services = set(tax.roots["services"].leaf_ids)
    for p in every_pair:
        if "ADD_ON_CREEP" in p.violation_types:
            assert any(li.merchant_category in services for li in p.cart.line_items), p.pair_id


def test_frequency_violations_carry_prior_approvals_in_window(every_pair) -> None:
    for p in every_pair:
        if "FREQUENCY_EXCEEDED" not in p.violation_types:
            continue
        window = FREQ_WINDOW[p.mandate.hard.frequency]
        recent = [a for a in p.prior_approvals
                  if (p.checked_at - a.approved_at).days < window]
        assert recent, p.pair_id


# ---------------------------------------------------------------------------
# composition
# ---------------------------------------------------------------------------


def test_every_violation_type_is_represented_in_every_split(splits) -> None:
    """P-005: each type needs enough test cases to support a per-type recall."""
    for name, pairs in splits.items():
        counts = Counter(v for p in pairs for v in p.violation_types)
        for vtype in ALL_VIOLATIONS:
            assert counts[vtype] > 0, f"{vtype} missing from {name}"
        if name == "test":
            for vtype in ALL_VIOLATIONS:
                assert counts[vtype] >= 20, f"{vtype} only {counts[vtype]} in test"


def test_class_balance_is_near_the_target(every_pair) -> None:
    conf = sum(1 for p in every_pair if p.label == "conforming")
    assert 0.5 <= conf / len(every_pair) <= 0.65


def test_intent_specificity_varies(every_pair) -> None:
    """Vague intents should exist, because they should escalate more often."""
    spec = Counter(p.specificity for p in every_pair)
    assert spec["vague"] / len(every_pair) > 0.1
    assert spec["precise"] / len(every_pair) > 0.1


def test_all_templates_are_exercised(every_pair) -> None:
    from data.generator.intents import TEMPLATES

    used = {p.template_id for p in every_pair}
    assert used == {t.id for t in TEMPLATES}


def test_rule_catchable_types_are_the_majority(every_pair) -> None:
    """04 §2's deliberate design point: only five types genuinely need a model."""
    model_only = {v for v, layer in RESOLVED_BY.items() if layer == "model"}
    violating = [p for p in every_pair if p.label == "violating"]
    needs_model = sum(1 for p in violating if set(p.violation_types) <= model_only)
    assert needs_model / len(violating) < 0.5


def test_generation_is_deterministic() -> None:
    a = make_dataset.build(seed=7, n_mandates=120)
    b = make_dataset.build(seed=7, n_mandates=120)
    assert [p.pair_id for p in a["test"]] == [p.pair_id for p in b["test"]]
    assert [p.cart.total_paise for p in a["test"]] == [p.cart.total_paise for p in b["test"]]


def test_a_different_seed_changes_the_data() -> None:
    a = make_dataset.build(seed=7, n_mandates=120)
    b = make_dataset.build(seed=8, n_mandates=120)
    assert [p.cart.total_paise for p in a["test"]] != [p.cart.total_paise for p in b["test"]]
