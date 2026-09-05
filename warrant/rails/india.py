"""Where an escalation actually lands on Indian payment rails.

02 §7 is the part that makes this Razorpay's problem rather than a generic one:
a verdict is only useful if the escalation has somewhere real to go. This module
maps a decision onto UPI-native mechanics.

**These are designed interfaces with clear stubs, not live integrations, and the
README says so.** 05 §Day-18 explicitly permits that and asks for it to be
stated rather than faked. Nothing here moves money or calls a bank; each adapter
returns the instruction a PSP would act on, so the shape can be reviewed and the
routing logic tested.

**NPCI's Unified Agent Protocol is unpublished.** The mandate is modelled in
Warrant's own schema and adapters translate outward, so when the spec lands the
change is a mapping, not an engine rewrite (02 §7 design note).

Mechanics this encodes, all announced rather than invented:

* **AFA above Rs 15,000** — RBI's 2026 e-mandate framework requires an
  additional factor for recurring debits above that ceiling, so an escalation
  there costs nothing extra: the step-up was already mandatory.
* **Pre-debit notification, 24 hours** — RBI requires notice before a debit.
  Warrant's verdict rides along, so the customer sees *what* is about to be
  bought rather than only *that* something is.
* **UPI Circle** — delegated payment authority. A mandate's cumulative cap maps
  onto the delegation limit.
* **Reserve Pay** — blocks funds for later debits, so an approved intent has
  money reserved against it.
* **CERT-In-shaped ceiling** — above a configurable amount `ALLOW` is disabled
  entirely; enforced in `warrant/decide/policy.py`, surfaced here.
* **DPDP purpose limitation** — constraint extraction keeps the constraints and
  discards the conversation they came from, and logs what it discarded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal

from warrant.models import Cart, IntentMandate, Verdict

AFA_THRESHOLD_PAISE = 1_500_000
"""Rs 15,000 — RBI's ceiling for recurring debits without an additional factor."""

PRE_DEBIT_NOTICE = timedelta(hours=24)
"""RBI requires notification at least 24 hours before a debit."""

StepUp = Literal["none", "push_notification", "afa_upi_pin", "blocked"]


@dataclass(frozen=True)
class RailsInstruction:
    """What a PSP should do with this decision. No side effects."""

    step_up: StepUp
    channel: str
    reason: str
    notify_at: datetime | None = None
    debit_not_before: datetime | None = None
    customer_summary: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


def _cart_summary(cart: Cart, limit: int = 3) -> str:
    """What the customer sees in the notification.

    Deliberately concrete. RBI's pre-debit notice tells a customer that a debit
    is coming; the point of carrying the conformance verdict is that they can
    see what is being bought while there is still time to stop it.
    """
    if not cart.line_items:
        return f"Rs {cart.total_paise / 100:,.0f} — no items listed"
    names = [li.title[:48] for li in cart.line_items[:limit]]
    more = len(cart.line_items) - len(names)
    listed = ", ".join(names) + (f", and {more} more" if more > 0 else "")
    return f"Rs {cart.total_paise / 100:,.0f} — {listed}"


def route(
    verdict: Verdict,
    mandate: IntentMandate,
    cart: Cart,
    explanation: str,
    now: datetime | None = None,
    afa_threshold_paise: int = AFA_THRESHOLD_PAISE,
) -> RailsInstruction:
    """Map a verdict onto a UPI-native action."""
    now = now or datetime.now(timezone.utc)
    summary = _cart_summary(cart)

    if verdict == "REFUSE":
        return RailsInstruction(
            step_up="blocked",
            channel="agent_response",
            reason=explanation,
            customer_summary=summary,
            metadata={
                "action": "decline_and_return_structured_reason",
                # the agent can re-plan or re-prompt its user; a bare decline
                # tells it nothing it can act on (02 §4)
                "agent_may_retry": "true",
            },
        )

    if verdict == "ALLOW":
        return RailsInstruction(
            step_up="none",
            channel="pre_debit_notification",
            reason="cart conforms to the signed intent",
            notify_at=now,
            debit_not_before=now + PRE_DEBIT_NOTICE,
            customer_summary=summary,
            metadata={
                "action": "proceed_after_notice_window",
                "notice_hours": str(int(PRE_DEBIT_NOTICE.total_seconds() // 3600)),
                "verdict_rides_along": "true",
            },
        )

    # ESCALATE — the interesting case, and the one 02 §7 is really about.
    if cart.total_paise >= afa_threshold_paise:
        return RailsInstruction(
            step_up="afa_upi_pin",
            channel="upi_afa",
            reason=(
                f"{explanation}. Cart is Rs {cart.total_paise / 100:,.0f}, at or "
                f"above the Rs {afa_threshold_paise / 100:,.0f} AFA ceiling, so "
                f"UPI PIN re-authentication is required regardless"
            ),
            notify_at=now,
            customer_summary=summary,
            metadata={
                "action": "request_upi_pin",
                "rbi_afa_required_anyway": "true",
                "friction_is_free": "true",
            },
        )

    return RailsInstruction(
        step_up="push_notification",
        channel="upi_push",
        reason=explanation,
        notify_at=now,
        customer_summary=summary,
        metadata={
            "action": "one_tap_approve_or_reject",
            "mandate_debit": "held_pending_response",
        },
    )


# ---------------------------------------------------------------------------
# UPI Circle / Reserve Pay mapping
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DelegationMapping:
    """A mandate expressed as UPI Circle delegated authority."""

    per_transaction_cap_paise: int
    delegation_limit_paise: int
    expires_at: datetime
    reserve_pay_block_paise: int | None
    notes: list[str] = field(default_factory=list)


def to_upi_circle(mandate: IntentMandate) -> DelegationMapping:
    """Map a mandate onto UPI Circle delegation and a Reserve Pay block.

    The cumulative cap is the natural delegation limit. When a mandate states
    none, the per-transaction cap times its usage count is the closest honest
    equivalent, and the gap is recorded rather than silently assumed away —
    an unbounded delegation is not something to infer from silence.
    """
    hard = mandate.hard
    notes: list[str] = []

    if hard.cumulative_cap_paise is not None:
        limit = hard.cumulative_cap_paise
    elif hard.max_uses is not None:
        limit = hard.amount_max_paise * hard.max_uses
        notes.append(
            "mandate states no cumulative cap; delegation limit derived from "
            f"amount_max x max_uses ({hard.max_uses})"
        )
    else:
        limit = hard.amount_max_paise
        notes.append(
            "mandate states neither a cumulative cap nor a usage count; "
            "delegation limited to a single transaction rather than assuming "
            "open-ended authority"
        )

    # Reserve Pay blocks funds so an approved intent has money behind it. Only
    # meaningful for a mandate that expects repeated debits.
    reserve = limit if (hard.frequency and hard.frequency != "once") else None
    if reserve is None:
        notes.append("one-off mandate; no Reserve Pay block proposed")

    return DelegationMapping(
        per_transaction_cap_paise=hard.amount_max_paise,
        delegation_limit_paise=limit,
        expires_at=hard.expires_at,
        reserve_pay_block_paise=reserve,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# DPDP purpose limitation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MinimisationRecord:
    """What was kept from the conversation, and what was thrown away.

    DPDP 2023 requires consent for a specified purpose. A conversational agent
    collects budget, recipients, sizes and rejection reasons as a by-product;
    the purpose here is conformance checking, so only the constraints are
    retained. Logging what was discarded is what makes the claim auditable
    rather than a promise.
    """

    retained_fields: list[str]
    discarded_chars: int
    discarded_categories: list[str]
    purpose: str = "cart conformance verification"


def minimise(raw_conversation: str, mandate: IntentMandate) -> MinimisationRecord:
    retained = []
    hard, soft = mandate.hard, mandate.soft
    if hard.amount_max_paise:
        retained.append("amount_max")
    if hard.expires_at:
        retained.append("expires_at")
    if hard.categories_allowed or hard.categories_denied:
        retained.append("categories")
    if hard.merchants_allowed:
        retained.append("merchants_allowed")
    if hard.deliver_by:
        retained.append("deliver_by")
    if not soft.is_empty:
        retained.append("soft_constraints")

    kept_chars = len(mandate.raw_intent_text)
    return MinimisationRecord(
        retained_fields=retained,
        discarded_chars=max(0, len(raw_conversation) - kept_chars),
        discarded_categories=[
            "conversational context",
            "browsing and rejection history",
            "unrelated preferences volunteered in dialogue",
        ],
    )
