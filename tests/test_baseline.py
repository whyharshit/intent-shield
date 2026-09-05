"""Baseline tests.

The baseline is the comparison the whole submission rests on, so it has to be
right in the ways that matter: it must catch exactly what `ap2ValidateMandatePair`
catches, and it must not be quietly crippled to make Warrant look better.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from conftest import cart, line
from eval.baseline import validate_mandate_pair

make_dataset = pytest.importorskip("data.generator.make_dataset")
from data.generator.pairs import ALL_VIOLATIONS  # noqa: E402
from eval.metrics import Outcome, score  # noqa: E402

# Types the baseline is expected to catch — and only these. 04 §2.
BASELINE_CATCHES = {"AMOUNT_EXCEEDED", "MERCHANT_OUT_OF_SCOPE"}


def test_allows_a_conforming_cart(mandate) -> None:
    c = cart(line(unit=50_000))
    r = validate_mandate_pair(mandate, c)
    assert r.verdict == "ALLOW"
    assert r.total_within_intent and r.merchant_allowed


def test_refuses_when_the_total_exceeds_the_cap(mandate) -> None:
    c = cart(line(unit=250_000))  # cap is 200,000
    r = validate_mandate_pair(mandate, c)
    assert r.verdict == "REFUSE"
    assert not r.total_within_intent


def test_a_cart_exactly_on_the_cap_is_allowed(mandate) -> None:
    """`<=`, not `<`. An off-by-one here would refuse a legitimate cart."""
    c = cart(line(unit=200_000))
    assert validate_mandate_pair(mandate, c).verdict == "ALLOW"


def test_empty_merchant_allow_list_means_no_restriction(mandate) -> None:
    """P-003.

    The alternative reading — empty means deny-all — would have the baseline
    refuse nearly every cart, inflating its recall and making the headline
    comparison meaningless in Warrant's favour.
    """
    assert mandate.hard.merchants_allowed == []
    c = cart(line(unit=10_000), merchant_id="mrc_anything")
    r = validate_mandate_pair(mandate, c)
    assert r.merchant_allowed
    assert r.verdict == "ALLOW"


def test_refuses_a_merchant_outside_a_non_empty_allow_list(mandate) -> None:
    m = mandate.model_copy(deep=True)
    m.hard.merchants_allowed = ["mrc_bigbasket"]
    ok = validate_mandate_pair(m, cart(line(), merchant_id="mrc_bigbasket"))
    bad = validate_mandate_pair(m, cart(line(), merchant_id="mrc_zepto"))
    assert ok.verdict == "ALLOW"
    assert bad.verdict == "REFUSE" and not bad.merchant_allowed


def test_the_whisky_case_passes_the_baseline(mandate) -> None:
    """The headline demo, as an assertion.

    Rs 1,830 of real whisky against a Rs 2,000 mandate that denies alcohol.
    Amount passes, merchant passes, so the baseline approves it. This is the
    failure the entire project exists to fix.
    """
    whisky = cart(
        line("line_001", unit=120_500, title="Red Knight Malt Whisky 750 ml"),
        line("line_002", unit=62_500, title="Windsor Special Whisky 750 ml"),
    )
    assert whisky.total_paise == 183_000 <= mandate.hard.amount_max_paise
    assert "alcohol" in mandate.hard.categories_denied
    assert validate_mandate_pair(mandate, whisky).verdict == "ALLOW"


def test_the_baseline_ignores_expiry(mandate) -> None:
    """Not a bug in the port — the reference implementation checks two things."""
    late = mandate.hard.expires_at + timedelta(days=30)
    assert validate_mandate_pair(mandate, cart(line())).verdict == "ALLOW"
    assert late > mandate.hard.expires_at  # and nothing above consulted it


# ---------------------------------------------------------------------------
# behaviour on the real dataset — the K1 evidence
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def scored():
    try:
        splits = make_dataset.build()
    except FileNotFoundError as exc:
        pytest.skip(f"catalog not built: {exc}")
    pairs = splits["train"] + splits["validation"]
    from eval.baseline import run

    results = run(pairs)
    return score([Outcome(pair=p, verdict=r.verdict) for p, r in zip(pairs, results)])


def test_k1_has_not_fired(scored) -> None:
    """Kill criterion K1: if the baseline catches most violations, stop.

    Expected around 17% — it catches two of twelve types. A large jump here
    means the dataset got easier, not that the baseline got better.
    """
    assert scored.recall < 0.50, (
        f"K1 FIRED: baseline recall {scored.recall:.1%}. The gap may not be "
        f"real, or the dataset has become too easy."
    )
    assert 0.10 < scored.recall < 0.30


def test_the_baseline_catches_amount_and_merchant_and_nothing_else(scored) -> None:
    for vtype in ALL_VIOLATIONS:
        caught, total = scored.per_type_recall[vtype]
        assert total > 0, f"{vtype} has no cases"
        rate = caught / total
        if vtype in BASELINE_CATCHES:
            assert rate > 0.95, f"{vtype}: baseline should catch these ({rate:.0%})"
        else:
            assert rate < 0.05, f"{vtype}: baseline unexpectedly caught {rate:.0%}"


def test_the_baseline_has_no_false_positives(scored) -> None:
    """It refuses only on breaches it can actually see, so precision is 1.0.

    Worth stating plainly in the report: the baseline is not *wrong* about what
    it checks. It is incomplete. Claiming it is inaccurate would be a strawman.
    """
    assert scored.false_positives == 0
    assert scored.precision == 1.0


def test_the_baseline_never_escalates(scored) -> None:
    """Two outcomes, not three — which is why P-004 exists."""
    assert scored.escalation_rate == 0.0
