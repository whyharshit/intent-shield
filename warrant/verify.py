"""The verification pipeline, as far as Milestone 4 builds it.

    category mapping  ->  C3 deterministic checks  ->  provisional verdict

C4 stage 2 (attribute reasoning) and C5 (the expected-cost policy) are not here
yet, so the verdict rule below is provisional and deliberately simple:

    any hard check failed        -> REFUSE
    any check uncertain          -> ESCALATE
    otherwise                    -> ALLOW

That third line is temporary. Once the semantic checker exists, a cart with
soft constraints outstanding must not reach ALLOW without them being judged —
`soft_constraints_pending` records that, so the gap is visible in the metrics
rather than hidden.

**Fail closed everywhere.** Uncertainty escalates; it never allows.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from warrant.checks.categories import CategoryMapper, MappedCategory, default_mapper
from warrant.checks.deterministic import (
    DeterministicChecker,
    DeterministicOutcome,
    PriorApproval,
)
from warrant.models import Cart, CheckResult, IntentMandate, Verdict
from warrant.taxonomy import Taxonomy, default_taxonomy


@dataclass
class VerificationResult:
    verdict: Verdict
    checks: list[CheckResult]
    explanation: str
    mapped: dict[str, MappedCategory] = field(default_factory=dict)
    latency_ms: int = 0
    path: str = "rule"          # which layer settled it
    soft_constraints_pending: bool = False

    @property
    def failed(self) -> list[CheckResult]:
        return [c for c in self.checks if c.result == "fail"]

    @property
    def uncertain(self) -> list[CheckResult]:
        return [c for c in self.checks if c.result == "uncertain"]


def _explain(verdict: Verdict, outcome: DeterministicOutcome) -> str:
    """Plain-English reason, taken from the checks rather than written about them."""
    if verdict == "REFUSE":
        return "; ".join(c.detail for c in outcome.failed[:3])
    if verdict == "ESCALATE":
        return "; ".join(c.detail for c in outcome.uncertain[:3]) or \
            "the cart could not be settled by rules alone"
    passed = [c for c in outcome.checks if c.result == "pass"]
    return f"all {len(passed)} applicable checks passed"


class Verifier:
    def __init__(
        self,
        taxonomy: Taxonomy | None = None,
        mapper: CategoryMapper | None = None,
    ):
        self.tax = taxonomy or default_taxonomy()
        self.mapper = mapper or default_mapper()
        self.checker = DeterministicChecker(self.tax)

    def verify(
        self,
        mandate: IntentMandate,
        cart: Cart,
        now: datetime | None = None,
        priors: list[PriorApproval] | None = None,
    ) -> VerificationResult:
        started = time.perf_counter()
        now = now or datetime.now(timezone.utc)

        # 1. category mapping — from the title, never from merchant_category
        mapped: dict[str, MappedCategory] = {}
        if cart.line_items:
            results = self.mapper.map_many(
                [(li.title, li.description) for li in cart.line_items]
            )
            mapped = {li.line_id: m for li, m in zip(cart.line_items, results)}

        # 2. deterministic checks
        outcome = self.checker.run(mandate, cart, now, mapped, priors)

        # 3. provisional verdict
        if outcome.failed:
            verdict: Verdict = "REFUSE"
            path = "rule"
        elif outcome.uncertain:
            verdict = "ESCALATE"
            path = "category" if any(
                c.check in ("denied_category", "allowed_scope")
                for c in outcome.uncertain
            ) else "rule"
        else:
            verdict = "ALLOW"
            path = "rule"

        pending = not mandate.soft.is_empty and verdict == "ALLOW"

        return VerificationResult(
            verdict=verdict,
            checks=outcome.checks,
            explanation=_explain(verdict, outcome),
            mapped=mapped,
            latency_ms=int((time.perf_counter() - started) * 1000),
            path=path,
            soft_constraints_pending=pending,
        )
