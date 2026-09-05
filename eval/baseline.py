"""The baseline: what the shipping AP2 reference implementations actually check.

Tenzro's public `ap2ValidateMandatePair` returns two booleans —
`total_within_intent` and `merchant_allowed`. Amount, and merchant allow-list.
That is the state of the art this project claims to improve on, so it is
implemented here faithfully and scored on the same test set.

This is not a strawman. It is a real implementation of a real spec, and the
comparison table is, per 04 §5, the single most persuasive artifact in the
submission — provided the baseline is implemented honestly. Two notes on that:

* `merchant_allowed` treats an empty allow-list as "no restriction" (P-003 in
  DECISIONS.md). The alternative reading — empty means deny-all — would have
  the baseline refuse nearly every cart, inflating its recall to near 1.0 and
  making the comparison meaningless in Warrant's favour.
* The baseline has no third outcome. It cannot escalate. Warrant's headline
  recall counts an escalation as a catch, which is not a comparison the
  baseline can participate in, so `run_eval` reports refuse-only recall
  alongside it (P-004).

If this baseline catches most violations, kill criterion K1 has fired: the gap
is not real, or the dataset is too easy.
"""

from __future__ import annotations

from dataclasses import dataclass

from data.generator.pairs import Pair
from warrant.models import Cart, IntentMandate


@dataclass(frozen=True)
class BaselineResult:
    verdict: str                 # "ALLOW" or "REFUSE" — there is no third option
    total_within_intent: bool
    merchant_allowed: bool

    @property
    def flagged(self) -> bool:
        return self.verdict == "REFUSE"


def validate_mandate_pair(mandate: IntentMandate, cart: Cart) -> BaselineResult:
    """Port of `ap2ValidateMandatePair`."""
    total_within_intent = cart.total_paise <= mandate.hard.amount_max_paise

    allow_list = mandate.hard.merchants_allowed
    merchant_allowed = (not allow_list) or (cart.merchant_id in allow_list)

    ok = total_within_intent and merchant_allowed
    return BaselineResult(
        verdict="ALLOW" if ok else "REFUSE",
        total_within_intent=total_within_intent,
        merchant_allowed=merchant_allowed,
    )


def run(pairs: list[Pair]) -> list[BaselineResult]:
    return [validate_mandate_pair(p.mandate, p.cart) for p in pairs]
