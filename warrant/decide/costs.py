"""The cost model — every number here is an assumption, and each says so.

02 §5 derives the decision thresholds from expected cost rather than picking
them. That only works if the inputs are stated openly enough to be argued with,
so each field carries its source and the eval runs a sensitivity analysis over
the ones that actually move the answer.

All money is paise.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class CostModel:
    """Inputs to the expected-cost calculation.

    Defaults are deliberately conservative and generic. A real deployment
    replaces them with the merchant's own numbers, which is the point: the
    operating point moves with the merchant's economics rather than with a
    threshold someone picked.
    """

    margin: float = 0.18
    """Merchant gross margin. A refused conforming cart loses this, not the
    whole cart value. Indian grocery retail runs thinner than this and
    electronics thinner still; 18% is a mid-range placeholder."""

    p_dispute: float = 0.35
    """Probability that a wrongly approved violating cart becomes a dispute.
    Not every bad purchase is disputed — some are returned, some absorbed.
    This is the single least defensible number in the model, and the
    sensitivity analysis varies it hardest."""

    chargeback_cost_paise: int = 150_000
    """Rs 1,500 — scheme fee plus handling for one dispute, independent of the
    cart value. Representative of published card-scheme dispute fees."""

    ratio_cost_paise: int = 250_000
    """Rs 2,500 — the amortised cost of one more dispute counting against a
    dispute-ratio threshold. Visa tightened the merchant threshold to 1.5% in
    April 2026; crossing it means fines, remediation, or losing the ability to
    accept payments. This is the term that makes a dispute cost more than the
    cart, and it is a genuine estimate rather than a published figure."""

    churn_cost_paise: int = 30_000
    """Rs 300 — goodwill lost when a legitimate purchase is wrongly blocked,
    beyond the lost margin on that order."""

    friction_cost_paise: int = 1_200
    """Rs 12 — the fixed cost of asking: the customer's attention and the
    operational cost of handling one review."""

    abandon_rate_small: float = 0.22
    """Fraction of escalated *small* purchases the customer abandons.

    A confirmation prompt on a Rs 200 grocery top-up is pure annoyance; the
    purchase is low-consideration and easily dropped.

    Abandonment matters more than any other term for the escalation rate, and
    the first version of this model left it out entirely. With only a fixed
    Rs 12 friction cost, escalation was so much cheaper than either error that
    it won across p(violation) from 0.02 to 0.84 — the policy escalated almost
    everything, which is exactly the failure 02 §4 warns about ("too high =
    useless")."""

    abandon_rate_large: float = 0.04
    """Fraction of escalated *large* purchases the customer abandons.

    Friction tolerance rises with how considered a purchase is, and above
    Rs 15,000 RBI already requires additional-factor authentication for
    recurring debits — a step-up there is expected rather than surprising.

    Modelling this as flat was an error. With a constant rate, the cost of
    escalating grew with cart value faster than the cost of wrongly allowing
    did near the decision boundary, so the policy *allowed* large carts at
    higher uncertainty than small ones — the opposite of what 02 §5 requires
    ("a Rs 40,000 electronics cart should escalate at much lower
    uncertainty"). See DECISIONS.md D-036."""

    abandon_decay_anchor_paise: int = 1_500_000
    """Rs 15,000 — where the abandonment rate has fully decayed to
    `abandon_rate_large`. Chosen to match the RBI AFA threshold."""

    human_error_rate: float = 0.05
    """Humans resolving escalations are not perfect either. Ignoring this would
    make escalation look free of risk, which it is not."""

    def with_overrides(self, **kw) -> CostModel:
        return replace(self, **{k: v for k, v in kw.items() if v is not None})


DEFAULT_COSTS = CostModel()


def abandon_rate(cart_value_paise: int, costs: CostModel) -> float:
    """How often an escalated purchase is abandoned, as a function of value.

    Decays linearly from `abandon_rate_small` at Rs 0 to `abandon_rate_large`
    at the anchor (Rs 15,000, the RBI AFA threshold), flat above it. People
    tolerate a confirmation step on a considered purchase and resent it on a
    routine one.
    """
    anchor = max(costs.abandon_decay_anchor_paise, 1)
    t = min(cart_value_paise / anchor, 1.0)
    return costs.abandon_rate_small + t * (
        costs.abandon_rate_large - costs.abandon_rate_small
    )


def cost_of_wrongly_allowing(cart_value_paise: int, costs: CostModel) -> float:
    """What it costs to approve a cart that should not have been approved.

    The cart value is refunded, the dispute is handled, and the dispute counts
    against the ratio. Only a fraction become disputes.
    """
    return costs.p_dispute * (
        cart_value_paise + costs.chargeback_cost_paise + costs.ratio_cost_paise
    )


def cost_of_wrongly_refusing(cart_value_paise: int, costs: CostModel) -> float:
    """What it costs to block a cart that should have gone through.

    Lost margin on this order, plus goodwill. Note this scales with cart value
    far more weakly than wrongly allowing does — which is why the thresholds
    move with value, and why a large cart should escalate at lower uncertainty.
    """
    return cart_value_paise * costs.margin + costs.churn_cost_paise


def cost_of_escalating(
    cart_value_paise: int, p_violation: float, costs: CostModel
) -> float:
    """What it costs to ask the human.

    Three terms, and the middle one is the one that keeps the escalation rate
    honest:

    1. fixed friction — attention and handling
    2. **abandonment** — some fraction of interrupted checkouts never complete,
       costing the margin on a sale that would have been fine
    3. residual human error — the reviewer can be wrong too
    """
    lost_if_abandoned = (
        cart_value_paise * costs.margin + costs.churn_cost_paise
    )
    # only conforming carts are lost to abandonment; a violating cart that the
    # customer walks away from was never a sale worth keeping
    abandonment = (
        abandon_rate(cart_value_paise, costs) * (1 - p_violation) * lost_if_abandoned
    )
    human_wrong = costs.human_error_rate * (
        p_violation * cost_of_wrongly_allowing(cart_value_paise, costs)
        + (1 - p_violation) * cost_of_wrongly_refusing(cart_value_paise, costs)
    )
    return costs.friction_cost_paise + abandonment + human_wrong
