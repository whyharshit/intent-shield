"""Catalog tests.

The catalog is ground truth for the whole evaluation: its `category` labels are
what per-violation-type recall is scored against. So these tests check the
things that would quietly corrupt that — mislabelled categories, prices in the
wrong unit, non-determinism across runs.

They exercise the *built* catalog, so they need data/raw/ present. They skip
rather than fail when it is absent, so a reviewer without the raw sources can
still run the rest of the suite.
"""

from __future__ import annotations

import re
from collections import Counter

import pytest

from warrant.taxonomy import default_taxonomy

catalog = pytest.importorskip("data.generator.catalog")


@pytest.fixture(scope="module")
def items():
    try:
        return catalog.build(seed=catalog.DEFAULT_SEED)
    except FileNotFoundError as exc:
        pytest.skip(f"raw sources not present: {exc}")


def test_catalog_is_about_the_target_size(items) -> None:
    assert 750 <= len(items) <= 850


def test_every_category_is_a_real_taxonomy_leaf(items) -> None:
    tax = default_taxonomy()
    for it in items:
        assert it.category in tax.leaves, f"{it.sku}: {it.category}"
        assert it.root == tax.root_of(it.category)


def test_skus_are_unique(items) -> None:
    skus = [i.sku for i in items]
    assert len(skus) == len(set(skus))


def test_prices_are_positive_paise(items) -> None:
    """Money is integer paise everywhere. A float here becomes a rounding
    difference in an amount-ceiling comparison later."""
    for it in items:
        assert isinstance(it.price_paise, int)
        assert it.price_paise > 0


def test_prices_are_in_a_plausible_indian_retail_band(items) -> None:
    """Catches a unit error — rupees stored as paise, or vice versa — which
    would silently shift every amount check by 100x."""
    prices = sorted(i.price_paise for i in items)
    median = prices[len(prices) // 2]
    assert 5_000 <= median <= 100_000, f"median Rs {median/100:,.0f} is implausible"
    assert prices[0] >= 100  # nothing below Rs 1


def test_build_is_deterministic(items) -> None:
    """The reproducibility contract in 04 §7 depends on this."""
    again = catalog.build(seed=catalog.DEFAULT_SEED)
    assert [i.sku for i in again] == [i.sku for i in items]


def test_a_different_seed_gives_a_different_catalog(items) -> None:
    other = catalog.build(seed=99)
    assert {i.sku for i in other} != {i.sku for i in items}
    assert len(other) == len(items)


def test_titles_look_like_real_products(items) -> None:
    """A catalog of 'Product 1, Product 2' makes the whole demo look fake."""
    for it in items:
        assert len(it.title) >= 3
        assert not re.fullmatch(r"(?i)(product|item|sku)[\s_-]*\d+", it.title)
    # real retail titles are multi-word far more often than not
    multiword = sum(1 for i in items if len(i.title.split()) >= 3)
    assert multiword / len(items) > 0.8


def test_alcohol_is_present_and_restricted(items) -> None:
    tax = default_taxonomy()
    alcohol = [i for i in items if i.root == "alcohol"]
    assert len(alcohol) >= 50
    assert all(tax.is_restricted(i.category) for i in alcohol)


def test_the_whisky_leaf_actually_contains_whisky(items) -> None:
    """Regression guard for the source's catch-all label.

    4,202 rows in the excise list are labelled "IMFL Whisky" and include sake,
    cognac and sauvignon blanc. An earlier build filled the whisky leaf with
    Italian wine — Ricossa Gavi, Te Mata Gamay Noir — and the test at the time
    only asserted that whisky *existed*, so it passed. Assert the contents.
    """
    whiskies = [i for i in items if i.category == "whisky"]
    assert whiskies
    for i in whiskies:
        assert re.search(
            r"whisk(y|ey)|scotch|bourbon|single malt|blended malt", i.title, re.I
        ), f"not a whisky: {i.title}"


def test_the_headline_demo_cart_is_buildable(items) -> None:
    """A cart of whisky totalling just under a Rs 2,000 grocery cap.

    This is the case the whole submission opens on, so the catalog has to be
    able to express it. One bottle or several — what matters is that a total
    lands under the cap while every line is alcohol.
    """
    cheap = sorted(
        (i for i in items if i.root == "alcohol" and i.price_paise < 200_000),
        key=lambda i: -i.price_paise,
    )
    assert cheap, "no alcohol under Rs 2,000 — the demo cart cannot be built"

    cap, total, lines = 200_000, 0, 0
    for i in cheap:
        if total + i.price_paise < cap:
            total += i.price_paise
            lines += 1
    assert total >= 150_000, f"best alcohol cart is only Rs {total/100:,.0f}"
    assert lines >= 1


def test_price_stratification_spans_each_leaf(items) -> None:
    """Sampling must preserve the real price range, not cluster.

    A leaf whose SKUs all sit in one narrow band makes amount-ceiling checks
    trivial and unrepresentative.
    """
    from collections import defaultdict

    by_leaf = defaultdict(list)
    for i in items:
        by_leaf[i.category].append(i.price_paise)
    wide = [c for c, p in by_leaf.items() if len(p) >= 8 and max(p) >= 4 * min(p)]
    assert len(wide) >= 10, "price ranges look collapsed across leaves"


def test_no_alcohol_leaked_into_grocery_roots(items) -> None:
    """A false negative here is the demo failing on stage: the whisky case
    only works if liquor never maps to a grocery leaf."""
    food_roots = {"grocery", "produce", "staples"}
    for it in items:
        if it.root in food_roots:
            assert it.source != "karnataka_excise", f"{it.title} -> {it.category}"


def test_catalog_spans_the_domains_the_dataset_needs(items) -> None:
    roots = Counter(i.root for i in items)
    # the grocery-mandate world the demo lives in
    for root in ("grocery", "produce", "staples", "personal_care", "household"):
        assert roots[root] >= 20, root
    # and the out-of-scope worlds violations get injected from
    for root in ("alcohol", "apparel", "electronics", "pharma", "restaurant"):
        assert roots[root] >= 20, root


def test_attributes_are_flat_strings(items) -> None:
    """LineItem.attributes is dict[str, str]; anything nested would fail to
    round-trip into a cart later."""
    for it in items:
        for k, v in it.attributes.items():
            assert isinstance(k, str) and isinstance(v, str), it.sku


def test_apparel_carries_colour(items) -> None:
    """Colour is the real attribute V4 ATTRIBUTE_MISMATCH is built on, now that
    footwear (and therefore size) is out of the catalog. See DECISIONS.md."""
    apparel = [i for i in items if i.root == "apparel"]
    assert apparel
    with_colour = [i for i in apparel if i.attributes.get("colour")]
    assert len(with_colour) / len(apparel) > 0.9


def test_round_trips_through_jsonl(items, tmp_path) -> None:
    path = tmp_path / "catalog.jsonl"
    catalog.write(items, path)
    again = catalog.load_catalog(path)
    assert again == items
