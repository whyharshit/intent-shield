"""Tests for C5 (cost model, policy) and calibration.

The properties asserted here are the ones 02 §5 argues for: thresholds derived
rather than picked, and both moving with cart value.
"""

from __future__ import annotations

import pytest

from warrant.decide.calibration import (
    Calibrator,
    expected_calibration_error,
    reliability_bins,
)
from warrant.decide.costs import (
    DEFAULT_COSTS,
    CostModel,
    abandon_rate,
    cost_of_escalating,
    cost_of_wrongly_allowing,
    cost_of_wrongly_refusing,
)
from warrant.decide.policy import (
    HUMAN_IN_THE_LOOP_CEILING_PAISE,
    decide,
    thresholds_for,
)

RS = 100  # paise per rupee


# ---------------------------------------------------------------------------
# cost model
# ---------------------------------------------------------------------------


def test_wrongly_allowing_costs_more_than_the_cart() -> None:
    """The dispute-ratio term is what makes a bad approval expensive.

    If approving a bad cart only cost the cart, refusing would almost never be
    worth it and the whole product would be pointless.
    """
    value = 2_000 * RS
    assert cost_of_wrongly_allowing(value, DEFAULT_COSTS) > value * DEFAULT_COSTS.p_dispute


def test_wrongly_refusing_costs_margin_not_the_whole_cart() -> None:
    value = 2_000 * RS
    cost = cost_of_wrongly_refusing(value, DEFAULT_COSTS)
    assert cost < value
    assert cost == pytest.approx(value * DEFAULT_COSTS.margin + DEFAULT_COSTS.churn_cost_paise)


def test_escalation_is_not_free() -> None:
    """It costs friction, abandoned sales, and residual human error.

    Modelling it as a flat Rs 12 made escalation win almost everywhere.
    """
    value = 2_000 * RS
    cost = cost_of_escalating(value, 0.3, DEFAULT_COSTS)
    assert cost > DEFAULT_COSTS.friction_cost_paise


def test_abandonment_falls_as_cart_value_rises() -> None:
    """People tolerate a confirmation step on a considered purchase.

    A flat rate made the policy allow large carts at *higher* uncertainty than
    small ones, which inverts the risk posture 02 §5 asks for.
    """
    small = abandon_rate(200 * RS, DEFAULT_COSTS)
    large = abandon_rate(40_000 * RS, DEFAULT_COSTS)
    assert small > large
    assert large == pytest.approx(DEFAULT_COSTS.abandon_rate_large)


# ---------------------------------------------------------------------------
# policy
# ---------------------------------------------------------------------------


def test_certain_conformance_allows_and_certain_violation_refuses() -> None:
    assert decide(0.0, 2_000 * RS).verdict == "ALLOW"
    assert decide(1.0, 2_000 * RS).verdict == "REFUSE"


def test_genuine_uncertainty_escalates() -> None:
    """Escalation is the product, not a failure mode (02 §4)."""
    assert decide(0.5, 2_000 * RS).verdict == "ESCALATE"


def test_a_hard_failure_bypasses_the_cost_trade_off() -> None:
    d = decide(0.0, 2_000 * RS, has_hard_failure=True)
    assert d.verdict == "REFUSE"
    assert d.expected_costs == {}
    assert "hard constraint" in d.reason


def test_thresholds_move_with_cart_value() -> None:
    """The property that makes deriving thresholds worthwhile."""
    small_lo, small_hi = thresholds_for(200 * RS)
    big_lo, big_hi = thresholds_for(40_000 * RS)
    assert (small_lo, small_hi) != (big_lo, big_hi)


def test_a_large_cart_escalates_at_lower_uncertainty() -> None:
    """02 §5: 'a Rs 40,000 electronics cart should escalate at much lower
    uncertainty' than a Rs 200 grocery cart."""
    small_allow_below, _ = thresholds_for(200 * RS)
    big_allow_below, _ = thresholds_for(40_000 * RS)
    assert big_allow_below < small_allow_below


def test_the_autonomy_ceiling_disables_allow_entirely() -> None:
    """CERT-In-shaped: above a threshold, a human must be involved."""
    above = HUMAN_IN_THE_LOOP_CEILING_PAISE + 1
    d = decide(0.0, above)
    assert d.verdict != "ALLOW"
    assert "human-in-the-loop ceiling" in d.reason
    # and below the ceiling the same probability allows
    assert decide(0.0, HUMAN_IN_THE_LOOP_CEILING_PAISE - 1).verdict == "ALLOW"


def test_verdicts_are_monotone_in_probability() -> None:
    """As p(violation) rises the verdict must never become more permissive."""
    order = {"ALLOW": 0, "ESCALATE": 1, "REFUSE": 2}
    seen = [order[decide(p / 100, 2_000 * RS).verdict] for p in range(0, 101)]
    assert seen == sorted(seen), "verdict became more permissive as risk rose"


def test_a_thinner_margin_makes_refusing_cheaper() -> None:
    """The operating point moves with the merchant's economics."""
    thin = CostModel(margin=0.03)
    fat = CostModel(margin=0.40)
    thin_lo, _ = thresholds_for(2_000 * RS, thin)
    fat_lo, _ = thresholds_for(2_000 * RS, fat)
    assert thin_lo <= fat_lo


def test_expected_costs_are_reported_for_audit() -> None:
    d = decide(0.4, 2_000 * RS)
    assert set(d.expected_costs) == {"ALLOW", "REFUSE", "ESCALATE"}
    assert all(v >= 0 for v in d.expected_costs.values())


def test_probability_outside_zero_to_one_is_rejected() -> None:
    for bad in (-0.01, 1.01):
        with pytest.raises(ValueError):
            decide(bad, 2_000 * RS)


# ---------------------------------------------------------------------------
# calibration
# ---------------------------------------------------------------------------


def test_ece_is_zero_for_a_perfectly_calibrated_set() -> None:
    probs = [0.0] * 50 + [1.0] * 50
    labels = [0] * 50 + [1] * 50
    assert expected_calibration_error(probs, labels) == pytest.approx(0.0)


def test_ece_catches_overconfidence() -> None:
    """A model that says 0.9 and is right half the time should score badly."""
    probs = [0.9] * 100
    labels = [1] * 50 + [0] * 50
    assert expected_calibration_error(probs, labels) == pytest.approx(0.4, abs=0.01)


def test_isotonic_fit_improves_calibration() -> None:
    raw = [i / 200 for i in range(200)]
    # scores are systematically overconfident: true rate is half the score
    labels = [1 if (i / 200) / 2 > 0.25 else 0 for i in range(200)]
    cal = Calibrator().fit(raw, labels)
    assert cal.fitted
    assert cal.ece_after <= cal.ece_before


def test_an_unfitted_calibrator_passes_scores_through() -> None:
    """Never invent a mapping from too little data."""
    cal = Calibrator()
    assert not cal.fitted
    assert cal.transform(0.42) == pytest.approx(0.42)


def test_refuses_to_fit_on_too_few_points() -> None:
    cal = Calibrator().fit([0.1, 0.9], [0, 1])
    assert not cal.fitted


def test_refuses_to_fit_on_a_single_class() -> None:
    cal = Calibrator().fit([i / 100 for i in range(100)], [0] * 100)
    assert not cal.fitted


def test_calibrated_output_is_always_a_probability() -> None:
    cal = Calibrator().fit([i / 100 for i in range(100)],
                           [0 if i < 50 else 1 for i in range(100)])
    for raw in (-5.0, 0.0, 0.5, 1.0, 5.0):
        assert 0.0 <= cal.transform(raw) <= 1.0


def test_calibrator_round_trips_through_disk(tmp_path) -> None:
    cal = Calibrator().fit([i / 100 for i in range(100)],
                           [0 if i < 50 else 1 for i in range(100)])
    path = cal.save(tmp_path / "cal.json")
    again = Calibrator.load(path)
    assert again.fitted
    assert again.transform(0.7) == pytest.approx(cal.transform(0.7), abs=1e-6)


def test_reliability_bins_cover_the_unit_interval() -> None:
    bins = reliability_bins([i / 100 for i in range(100)], [i % 2 for i in range(100)])
    assert len(bins) == 10
    assert sum(b["n"] for b in bins) == 100
