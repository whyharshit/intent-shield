"""Tests for C4 stage 1 (category mapping) and C3 (deterministic checks).

The fail-closed tests matter most. Every one of them is a case where the wrong
answer is a silent approval on a payment.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from conftest import NOW, cart, line
from warrant.checks.categories import CategoryMapper, MappedCategory
from warrant.checks.deterministic import DeterministicChecker, PriorApproval
from warrant.models import HardConstraints, IntentMandate
from warrant.taxonomy import UNKNOWN, default_taxonomy


@pytest.fixture(scope="module")
def mapper() -> CategoryMapper:
    return CategoryMapper()


@pytest.fixture
def checker() -> DeterministicChecker:
    return DeterministicChecker()


def mapping(**kw) -> dict[str, MappedCategory]:
    return {
        lid: MappedCategory(leaf, 1.0, "keyword") for lid, leaf in kw.items()
    }


# ---------------------------------------------------------------------------
# category mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "title,expect_root",
    [
        ("Red Knight Malt Whisky 750 ml", "alcohol"),
        ("Kingfisher Premium Lager Beer 650 ml", "alcohol"),
        ("Old Monk Gold Reserve Rum 180 ml", "alcohol"),
        ("Butternut Pinot Noir 750 ml", "alcohol"),
        ("Amul Pasteurised Butter 100 g", "grocery"),
        ("Aashirvaad Shudh Chakki Atta 5 kg", "staples"),
        ("Colgate Vedshakti Ayurvedic Toothpaste", "personal_care"),
    ],
)
def test_maps_real_products_to_the_right_root(mapper, title, expect_root) -> None:
    got = mapper.map_one(title)
    assert got.is_known, f"{title} -> UNKNOWN"
    assert default_taxonomy().root_of(got.leaf_id) == expect_root


def test_premium_beer_is_not_insurance(mapper) -> None:
    """Regression for the defect that made K2 fire.

    `insurance` carried the keyword "premium", and longest-match let it beat
    "beer", so *Tuborg Super Premium Danish Beer* mapped to `insurance` and
    would have passed a no-alcohol mandate.
    """
    for title in (
        "Tuborg Super Premium Danish Beer Strong 650 ml",
        "Mc Dowell's Premium Dry Gin 750 ml",
        "Becks Ice Premium Lager 650 ml",
    ):
        got = mapper.map_one(title)
        assert default_taxonomy().root_of(got.leaf_id) == "alcohol", title


def test_flavour_words_do_not_decide_the_category(mapper) -> None:
    """"Orange Juice" is a beverage, not fruit. An ingredient is not a category."""
    tax = default_taxonomy()
    juice = mapper.map_one("Raw Pressery Valencia Orange - 100% Natural Cold Pressed Juice")
    assert not juice.is_known or tax.root_of(juice.leaf_id) != "produce"


def test_declines_rather_than_guesses(mapper) -> None:
    """Nonsense must map to UNKNOWN, which forces escalation."""
    got = mapper.map_one("Zxqv Blorptastic 7000")
    assert got.leaf_id == UNKNOWN
    assert not got.is_known


def test_degraded_mode_still_catches_alcohol() -> None:
    """If embeddings cannot load, the restricted keyword path must still work."""
    degraded = CategoryMapper(use_embeddings=False)
    assert degraded.degraded
    got = degraded.map_one("Red Knight Malt Whisky 750 ml")
    assert default_taxonomy().root_of(got.leaf_id) == "alcohol"


def test_mapping_is_batch_order_stable(mapper) -> None:
    titles = ["Amul Butter", "Old Monk Rum 180 ml", "Colgate Toothpaste"]
    batch = mapper.map_many([(t, None) for t in titles])
    one_by_one = [mapper.map_one(t) for t in titles]
    assert [b.leaf_id for b in batch] == [o.leaf_id for o in one_by_one]


# ---------------------------------------------------------------------------
# deterministic checks
# ---------------------------------------------------------------------------


def test_amount_ceiling(checker, mandate) -> None:
    assert checker.amount_ceiling(mandate, cart(line(unit=150_000))).result == "pass"
    assert checker.amount_ceiling(mandate, cart(line(unit=200_000))).result == "pass"
    fail = checker.amount_ceiling(mandate, cart(line(unit=250_000)))
    assert fail.result == "fail" and "exceeds cap" in fail.detail


def test_expiry(checker, mandate) -> None:
    assert checker.mandate_validity(mandate, NOW).result == "pass"
    assert checker.mandate_validity(mandate, NOW + timedelta(days=31)).result == "fail"


def test_empty_merchant_list_is_skipped_not_failed(checker, mandate) -> None:
    """P-003 again, at the rule layer."""
    r = checker.merchant_scope(mandate, cart(line(), merchant_id="mrc_anything"))
    assert r.result == "skipped"


def test_frequency_uses_prior_approvals(checker, mandate) -> None:
    """Closes P-002: the check is unverifiable without mandate state."""
    assert checker.frequency(mandate, NOW, []).result == "pass"
    recent = [PriorApproval(NOW - timedelta(days=2), 50_000)]
    assert checker.frequency(mandate, NOW, recent).result == "fail"
    old = [PriorApproval(NOW - timedelta(days=20), 50_000)]
    assert checker.frequency(mandate, NOW, old).result == "pass"


def test_cumulative_spend(checker, mandate) -> None:
    m = mandate.model_copy(deep=True)
    m.hard.cumulative_cap_paise = 500_000
    priors = [PriorApproval(NOW - timedelta(days=k), 200_000) for k in (10, 20)]
    assert checker.cumulative_spend(m, cart(line(unit=50_000)), priors).result == "pass"
    assert checker.cumulative_spend(m, cart(line(unit=150_000)), priors).result == "fail"


def test_delivery_window(checker, mandate) -> None:
    m = mandate.model_copy(deep=True)
    m.hard.deliver_by = NOW + timedelta(days=5)
    ok = cart(line(), promised_delivery=NOW + timedelta(days=3))
    late = cart(line(), promised_delivery=NOW + timedelta(days=9))
    assert checker.delivery_window(m, ok).result == "pass"
    assert checker.delivery_window(m, late).result == "fail"
    # a cart that promises nothing against a deadline is uncertain, not a pass
    assert checker.delivery_window(m, cart(line())).result == "uncertain"


def test_denied_category_catches_the_whisky_case(checker, mandate) -> None:
    c = cart(
        line("line_001", unit=120_500, title="Red Knight Malt Whisky 750 ml"),
        line("line_002", unit=62_500, title="Windsor Special Whisky 750 ml"),
    )
    r = checker.denied_category(mandate, c, mapping(line_001="whisky", line_002="whisky"))
    assert r.result == "fail"
    assert "denied category" in r.detail
    assert set(r.line_refs) == {"line_001", "line_002"}
    # and the amount check passes, which is the whole point
    assert checker.amount_ceiling(mandate, c).result == "pass"


def test_denied_category_is_uncertain_when_a_material_line_is_unmappable(
    checker, mandate
) -> None:
    """Fail closed: an uncategorised line cannot clear the deny-list."""
    c = cart(line("line_001", unit=180_000, title="Zxqv Blorptastic"))
    r = checker.denied_category(mandate, c, {"line_001": MappedCategory(UNKNOWN, 0.1, "unknown")})
    assert r.result == "uncertain"


def test_an_immaterial_unmappable_line_does_not_escalate(checker, mandate) -> None:
    """A Rs 20 unknown on a Rs 1,800 cart is not worth interrupting a human.

    Derived from the cost model rather than picked: escalation costs ~Rs 12 of
    friction, so asking is only worth it above ~Rs 150 at risk.
    """
    c = cart(
        line("line_001", unit=180_000, title="Aashirvaad Atta 5 kg"),
        line("line_002", unit=2_000, title="Zxqv Blorptastic"),
    )
    m = mapping(line_001="atta_flour")
    m["line_002"] = MappedCategory(UNKNOWN, 0.1, "unknown")
    assert checker.denied_category(mandate, c, m).result == "pass"


def test_a_cheap_denied_item_still_fails(checker, mandate) -> None:
    """Materiality gates *unmappable* lines only.

    A small bottle of whisky is categorised, so it must refuse however cheap it
    is — otherwise the gate would open a hole in the headline check.
    """
    c = cart(
        line("line_001", unit=180_000, title="Aashirvaad Atta 5 kg"),
        line("line_002", unit=2_800, title="Olympic Champ Deluxe Whisky 90 ml"),
    )
    r = checker.denied_category(mandate, c, mapping(line_001="atta_flour", line_002="whisky"))
    assert r.result == "fail"


def test_unknown_category_in_the_mandate_is_uncertain_not_empty(checker, mandate) -> None:
    """A typo'd deny-list must not silently expand to nothing."""
    m = mandate.model_copy(deep=True)
    m.hard.categories_denied = ["alcohols"]  # plausible typo
    r = checker.denied_category(m, cart(line()), mapping(line_001="atta_flour"))
    assert r.result == "uncertain"


def test_out_of_scope_escalates_but_restricted_refuses(checker, mandate) -> None:
    """D-031: 'not allowed' is a weaker signal than 'explicitly denied'."""
    m = mandate.model_copy(deep=True)
    m.hard.categories_denied = []
    m.hard.categories_allowed = ["grocery", "produce", "staples"]

    ordinary = cart(line("line_001", unit=90_000, title="Boult Earphones"))
    soft = checker.allowed_scope(m, ordinary, mapping(line_001="audio_headphones"))
    assert soft.result == "uncertain"

    booze = cart(line("line_001", unit=90_000, title="Old Monk Rum 180 ml"))
    hard = checker.allowed_scope(m, booze, mapping(line_001="rum"))
    assert hard.result == "fail", "age-gated goods must refuse, not escalate"


def test_add_on_creep_is_a_rule_not_a_language_judgement(checker, mandate) -> None:
    """D-012: 04 §2 marks V11 as needing an LLM. Set membership answers it."""
    c = cart(
        line("line_001", unit=90_000, title="Aashirvaad Atta"),
        line("line_002", unit=49_900, title="Extended Warranty - 24 months"),
    )
    r = checker.unrequested_add_ons(
        mandate, c, mapping(line_001="atta_flour", line_002="warranty_protection")
    )
    assert r.result == "fail"
    assert r.line_refs == ["line_002"]


def test_empty_cart_escalates_and_does_not_crash(checker, mandate) -> None:
    from warrant.models import Cart

    empty = Cart(cart_id="c", merchant_id="m", subtotal_paise=0, total_paise=0)
    outcome = checker.run(mandate, empty, NOW, {})
    assert any(c.check == "empty_cart" and c.result == "uncertain" for c in outcome.checks)
    assert not outcome.failed


def test_every_check_is_decided_by_rule(checker, mandate) -> None:
    """C3 must never claim a model decided anything."""
    outcome = checker.run(mandate, cart(line()), NOW, mapping(line_001="atta_flour"))
    assert all(c.decided_by == "rule" for c in outcome.checks)


def test_details_carry_the_numbers_that_produced_them(checker, mandate) -> None:
    """The audit record has to explain the verdict, not just assert it."""
    r = checker.amount_ceiling(mandate, cart(line(unit=250_000)))
    assert "2,500" in r.detail and "2,000" in r.detail
