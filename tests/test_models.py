"""Schema tests.

Half of these assert that valid documents parse. The other half assert that
malformed ones are *rejected* — which matters more. Every rejection here is a
case where accepting the document would have let a bad number reach a
comparison in C3 and produce a confident, wrong verdict.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from conftest import HEX, NOW, cart, line
from warrant.models import (
    Cart,
    CheckResult,
    Decision,
    HardConstraints,
    IntentMandate,
    LineItem,
    SoftConstraints,
)

# ---------------------------------------------------------------------------
# accepts
# ---------------------------------------------------------------------------


def test_mandate_round_trips(mandate: IntentMandate) -> None:
    again = IntentMandate.model_validate_json(mandate.model_dump_json())
    assert again == mandate
    assert again.hard.amount_max_paise == 200_000


def test_cart_totals_add_up() -> None:
    c = cart(line(unit=50_000, qty=2), line("line_002", unit=25_000), tax=5_000, shipping=4_000)
    assert c.subtotal_paise == 125_000
    assert c.total_paise == 134_000


def test_empty_cart_is_accepted_not_rejected() -> None:
    """A zero-item cart is a degenerate input the pipeline must escalate on.

    Rejecting it at the schema boundary would turn an adversarial test case
    (04 §3) into a parse error that tells the caller nothing.
    """
    c = Cart(cart_id="c1", merchant_id="m1", subtotal_paise=0, total_paise=0)
    assert c.line_items == []


def test_soft_constraints_default_empty_and_report_emptiness() -> None:
    s = SoftConstraints()
    assert s.is_empty
    assert not SoftConstraints(attribute_requirements=["size 10"]).is_empty


def test_soft_constraints_drop_blank_entries() -> None:
    s = SoftConstraints(brand_preferences=["  Amul ", "", "   "])
    assert s.brand_preferences == ["Amul"]


def test_datetimes_are_normalised_to_utc() -> None:
    ist = timezone(timedelta(hours=5, minutes=30))
    h = HardConstraints(amount_max_paise=1, expires_at=datetime(2026, 12, 1, 17, 30, tzinfo=ist))
    assert h.expires_at.tzinfo == timezone.utc
    assert h.expires_at.hour == 12


def test_expiry_check(mandate: IntentMandate) -> None:
    assert not mandate.is_expired(NOW)
    assert mandate.is_expired(NOW + timedelta(days=31))


def test_duplicate_category_ids_are_collapsed() -> None:
    h = HardConstraints(
        amount_max_paise=1,
        expires_at=NOW + timedelta(days=1),
        categories_denied=["alcohol", "alcohol", "tobacco"],
    )
    assert h.categories_denied == ["alcohol", "tobacco"]


# ---------------------------------------------------------------------------
# rejects
# ---------------------------------------------------------------------------


def test_naive_datetime_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        HardConstraints(amount_max_paise=1, expires_at=datetime(2026, 12, 1, 0, 0))


def test_zero_or_negative_cap_rejected() -> None:
    for bad in (0, -1):
        with pytest.raises(ValidationError):
            HardConstraints(amount_max_paise=bad, expires_at=NOW + timedelta(days=1))


def test_category_cannot_be_allowed_and_denied() -> None:
    with pytest.raises(ValidationError, match="both allowed and denied"):
        HardConstraints(
            amount_max_paise=1,
            expires_at=NOW + timedelta(days=1),
            categories_allowed=["grocery", "alcohol"],
            categories_denied=["alcohol"],
        )


def test_cumulative_cap_below_per_transaction_cap_rejected() -> None:
    with pytest.raises(ValidationError, match="below amount_max_paise"):
        HardConstraints(
            amount_max_paise=200_000,
            cumulative_cap_paise=100_000,
            expires_at=NOW + timedelta(days=1),
        )


def test_line_total_must_equal_unit_times_quantity() -> None:
    with pytest.raises(ValidationError, match="line total"):
        LineItem(
            line_id="l1",
            sku="s",
            title="t",
            quantity=3,
            unit_amount_paise=10_000,
            total_amount_paise=20_000,  # should be 30,000
        )


def test_cart_subtotal_must_equal_sum_of_lines() -> None:
    with pytest.raises(ValidationError, match="sum of line totals"):
        Cart(
            cart_id="c",
            merchant_id="m",
            line_items=[line(unit=10_000)],
            subtotal_paise=99_999,
            total_paise=99_999,
        )


def test_cart_total_must_include_tax_and_shipping() -> None:
    """The adversarial case where shipping pushes a conforming cart over the cap.

    If the schema let `total_paise` disagree with subtotal + tax + shipping,
    the amount check in C3 could read a total that no line item supports.
    """
    with pytest.raises(ValidationError, match="subtotal \\+ tax \\+ shipping"):
        Cart(
            cart_id="c",
            merchant_id="m",
            line_items=[line(unit=190_000)],
            subtotal_paise=190_000,
            shipping_paise=15_000,
            total_paise=190_000,  # ignores the shipping
        )


def test_duplicate_line_ids_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate line_id"):
        cart(line("line_001"), line("line_001"))


def test_unknown_field_rejected() -> None:
    """extra='forbid': the sender and this service must agree on the document."""
    with pytest.raises(ValidationError):
        HardConstraints(
            amount_max_paise=1,
            expires_at=NOW + timedelta(days=1),
            amount_max_rupees=2000,  # plausible-looking, silently ignored otherwise
        )


def test_mandate_expiring_before_issuance_rejected(soft: SoftConstraints) -> None:
    with pytest.raises(ValidationError, match="expires at or before"):
        IntentMandate(
            mandate_id="m",
            subject_did="did:example:alice",
            raw_intent_text="x",
            hard=HardConstraints(amount_max_paise=1, expires_at=NOW - timedelta(days=1)),
            soft=soft,
            issued_at=NOW,
            signature="sig",
        )


@pytest.mark.parametrize("bad_did", ["alice", "did:alice", ""])
def test_malformed_did_rejected(bad_did: str) -> None:
    with pytest.raises(ValidationError):
        IntentMandate(
            mandate_id="m",
            subject_did=bad_did,
            raw_intent_text="x",
            hard=HardConstraints(amount_max_paise=1, expires_at=NOW + timedelta(days=1)),
            issued_at=NOW,
            signature="sig",
        )


def test_non_es256_algorithm_rejected() -> None:
    with pytest.raises(ValidationError):
        IntentMandate(
            mandate_id="m",
            subject_did="did:example:alice",
            raw_intent_text="x",
            hard=HardConstraints(amount_max_paise=1, expires_at=NOW + timedelta(days=1)),
            issued_at=NOW,
            signature="sig",
            signature_alg="HS256",
        )


# ---------------------------------------------------------------------------
# decision record
# ---------------------------------------------------------------------------


def _decision(**kw) -> Decision:
    base = dict(
        decision_id="dec_1",
        mandate_id="mnd_001",
        mandate_hash=HEX,
        cart_hash=HEX,
        verdict="ALLOW",
        raw_confidence=0.9,
        calibrated_p_violation=0.05,
        checks=[CheckResult(check="amount_ceiling", result="pass", decided_by="rule")],
        latency_ms=12,
        timestamp=NOW,
        prev_hash=HEX,
        record_hash=HEX,
    )
    base.update(kw)
    return Decision(**base)


def test_decision_accepts_a_well_formed_allow() -> None:
    assert _decision().verdict == "ALLOW"


def test_refuse_requires_a_failing_check() -> None:
    """An audit record that refuses must say what failed, or it isn't evidence."""
    with pytest.raises(ValidationError, match="REFUSE requires"):
        _decision(verdict="REFUSE")

    ok = _decision(
        verdict="REFUSE",
        checks=[
            CheckResult(
                check="category_denied",
                result="fail",
                decided_by="rule",
                detail="line_002 -> alcohol in denied set",
                line_refs=["line_002"],
            )
        ],
    )
    assert ok.verdict == "REFUSE"


@pytest.mark.parametrize("p", [-0.01, 1.01])
def test_probabilities_must_be_probabilities(p: float) -> None:
    with pytest.raises(ValidationError):
        _decision(calibrated_p_violation=p)


def test_hashes_must_be_sha256_hex() -> None:
    for bad in ("not-a-hash", "ABC" * 21 + "A", "a" * 63):
        with pytest.raises(ValidationError):
            _decision(record_hash=bad)


def test_unknown_verdict_rejected() -> None:
    with pytest.raises(ValidationError):
        _decision(verdict="MAYBE")
