"""C5 — the decision policy.

Given a calibrated P(violation) and a cart value, pick the action with the
lowest expected cost. Three outcomes, and the thresholds fall out of the cost
model rather than being chosen (02 §5).

The important property is that **both thresholds move with cart value**. A
Rs 200 grocery cart should rarely escalate; a Rs 40,000 electronics cart should
escalate at much lower uncertainty. A fixed threshold cannot express that, which
is the argument for deriving one.

Two overrides sit on top of the argmin, and both exist because a pure
expected-cost calculation would otherwise do something a regulator or a customer
would object to:

* **Hard failures never reach the policy.** A breached hard constraint is a
  refusal. The expected-cost calculation is for uncertainty, not for a cart that
  demonstrably exceeds its cap.
* **A CERT-In-shaped autonomy ceiling.** Above a configurable amount, ALLOW is
  disabled entirely and the only outcomes are REFUSE or ESCALATE. CERT-In's
  2025-26 report proposed mandating human-in-the-loop control for agentic
  actions above a financial threshold; this implements that shape.
"""

from __future__ import annotations

from dataclasses import dataclass

from warrant.decide.costs import (
    DEFAULT_COSTS,
    CostModel,
    cost_of_escalating,
    cost_of_wrongly_allowing,
    cost_of_wrongly_refusing,
)
from warrant.models import Verdict

HUMAN_IN_THE_LOOP_CEILING_PAISE = 5_000_000
"""Rs 50,000. Above this, ALLOW is disabled — see the CERT-In note above.
Configurable per deployment; the number itself is a placeholder, the mechanism
is the point."""


@dataclass(frozen=True)
class PolicyDecision:
    verdict: Verdict
    expected_costs: dict[str, float]
    reason: str

    @property
    def margin_over_runner_up(self) -> float:
        """How much cheaper the chosen action was than the next best.

        A decision made by a hair is worth surfacing in the review UI; one made
        by a wide margin is not.
        """
        ordered = sorted(self.expected_costs.values())
        return ordered[1] - ordered[0] if len(ordered) > 1 else 0.0


def decide(
    p_violation: float,
    cart_value_paise: int,
    costs: CostModel | None = None,
    *,
    has_hard_failure: bool = False,
    ceiling_paise: int = HUMAN_IN_THE_LOOP_CEILING_PAISE,
) -> PolicyDecision:
    costs = costs or DEFAULT_COSTS

    if has_hard_failure:
        return PolicyDecision(
            verdict="REFUSE",
            expected_costs={},
            reason="a hard constraint was breached; no cost trade-off applies",
        )

    if not 0.0 <= p_violation <= 1.0:
        raise ValueError(f"p_violation must be a probability, got {p_violation}")

    e_allow = p_violation * cost_of_wrongly_allowing(cart_value_paise, costs)
    e_refuse = (1 - p_violation) * cost_of_wrongly_refusing(cart_value_paise, costs)
    e_escalate = cost_of_escalating(cart_value_paise, p_violation, costs)

    options: dict[str, float] = {
        "ALLOW": e_allow,
        "REFUSE": e_refuse,
        "ESCALATE": e_escalate,
    }

    if cart_value_paise >= ceiling_paise:
        options.pop("ALLOW")
        verdict = min(options, key=options.__getitem__)
        return PolicyDecision(
            verdict=verdict,  # type: ignore[arg-type]
            expected_costs={"ALLOW": e_allow, "REFUSE": e_refuse, "ESCALATE": e_escalate},
            reason=(
                f"cart value Rs {cart_value_paise / 100:,.0f} is at or above the "
                f"Rs {ceiling_paise / 100:,.0f} human-in-the-loop ceiling, so "
                f"ALLOW is disabled; {verdict} had the lower expected cost"
            ),
        )

    verdict = min(options, key=options.__getitem__)
    return PolicyDecision(
        verdict=verdict,  # type: ignore[arg-type]
        expected_costs=options,
        reason=(
            f"expected cost Rs {options[verdict] / 100:,.2f} at "
            f"p(violation)={p_violation:.2f} on a Rs {cart_value_paise / 100:,.0f} "
            f"cart; next best was Rs "
            f"{sorted(options.values())[1] / 100:,.2f}"
        ),
    )


def thresholds_for(
    cart_value_paise: int,
    costs: CostModel | None = None,
    steps: int = 2001,
) -> tuple[float, float]:
    """The two p(violation) boundaries at a given cart value.

    Returns (allow_below, refuse_above): allow while p is under the first,
    refuse once p is over the second, escalate in between. Found by scanning
    rather than solved in closed form — the escalation cost depends on p, so
    the crossing points move, and a scan is honest about that.

    Returns (0.0, 0.0) when the value is above the autonomy ceiling and ALLOW
    is unavailable at any p.
    """
    costs = costs or DEFAULT_COSTS
    grid = [i / (steps - 1) for i in range(steps)]
    verdicts = [
        decide(p, cart_value_paise, costs).verdict for p in grid
    ]

    allow_below = 0.0
    for p, v in zip(grid, verdicts):
        if v == "ALLOW":
            allow_below = p
        else:
            break

    refuse_above = 1.0
    for p, v in zip(reversed(grid), reversed(verdicts)):
        if v == "REFUSE":
            refuse_above = p
        else:
            break

    return allow_below, refuse_above
