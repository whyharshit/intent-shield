"""The verification pipeline, end to end.

    category mapping -> C3 rules -> C4.2 semantic -> calibration -> C5 policy

Ordering follows the governing rule. Comparisons and set membership run first
and settle most carts for free. A language model is consulted only when hard
constraints pass, categories are clean, and soft constraints remain — and it
returns per-constraint verdicts, never a decision. The decision is an
expected-cost argmin over a calibrated probability.

**Fail closed at every stage.** An unmappable category, an unavailable model, an
unparseable response, an unknown constraint — each produces uncertainty, and
uncertainty escalates. Nothing in this file can turn a failure into an ALLOW.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from warrant.checks.attributes import AttributeChecker, AttributeOutcome
from warrant.checks.categories import CategoryMapper, MappedCategory, default_mapper
from warrant.checks.deterministic import (
    DeterministicChecker,
    DeterministicOutcome,
    PriorApproval,
)
from warrant.decide.calibration import Calibrator
from warrant.decide.costs import DEFAULT_COSTS, CostModel
from warrant.decide.policy import PolicyDecision, decide
from warrant.models import Cart, CheckResult, IntentMandate, Verdict
from warrant.taxonomy import Taxonomy, default_taxonomy

# Raw score assigned when rules or categories leave a cart uncertain.
#
# Not a probability yet — it is the input to calibration, which learns what it
# actually means from the validation split. Distinct values per source so
# isotonic regression can separate them.
SCORE_CLEAN = 0.02
SCORE_SOFT_UNCERTAIN = 0.45
SCORE_RULE_UNCERTAIN = 0.55
SCORE_SOFT_VIOLATED = 0.90
SCORE_HARD_FAILURE = 1.0


@dataclass
class VerificationResult:
    verdict: Verdict
    checks: list[CheckResult]
    explanation: str
    raw_confidence: float = 0.0
    calibrated_p_violation: float = 0.0
    expected_costs: dict[str, float] = field(default_factory=dict)
    mapped: dict[str, MappedCategory] = field(default_factory=dict)
    latency_ms: int = 0
    path: str = "rule"
    consulted_model: bool = False
    degraded: bool = False
    degraded_reason: str = ""

    @property
    def failed(self) -> list[CheckResult]:
        return [c for c in self.checks if c.result == "fail"]

    @property
    def uncertain(self) -> list[CheckResult]:
        return [c for c in self.checks if c.result == "uncertain"]


def _explain(verdict: Verdict, checks: list[CheckResult]) -> str:
    failed = [c for c in checks if c.result == "fail"]
    unsure = [c for c in checks if c.result == "uncertain"]
    if verdict == "REFUSE" and failed:
        return "; ".join(c.detail for c in failed[:3])
    if verdict == "ESCALATE":
        if unsure:
            return "; ".join(c.detail for c in unsure[:3])
        return "the expected cost of deciding exceeded the cost of asking"
    if verdict == "REFUSE":
        return "the cart is more likely than not to violate the mandate"
    passed = [c for c in checks if c.result == "pass"]
    return f"all {len(passed)} applicable checks passed"


def _score(
    rules: DeterministicOutcome, attrs: AttributeOutcome | None
) -> tuple[float, str]:
    """Raw score for this cart, plus which layer produced it.

    Deliberately coarse. Calibration learns the mapping from these to empirical
    violation rates; inventing a finer-grained score here would be a guess
    dressed as precision.
    """
    if rules.failed:
        return SCORE_HARD_FAILURE, "rule"
    if attrs and attrs.failed:
        return SCORE_SOFT_VIOLATED, "model"
    if attrs and attrs.uncertain:
        return SCORE_SOFT_UNCERTAIN, "model"
    if rules.uncertain:
        source = "category" if any(
            c.check in ("denied_category", "allowed_scope") for c in rules.uncertain
        ) else "rule"
        return SCORE_RULE_UNCERTAIN, source
    return SCORE_CLEAN, "rule"


class Verifier:
    def __init__(
        self,
        taxonomy: Taxonomy | None = None,
        mapper: CategoryMapper | None = None,
        attribute_checker: AttributeChecker | None = None,
        calibrator: Calibrator | None = None,
        costs: CostModel | None = None,
        use_model: bool = True,
    ):
        self.tax = taxonomy or default_taxonomy()
        self.mapper = mapper or default_mapper()
        self.checker = DeterministicChecker(self.tax)
        self.attributes = attribute_checker or (AttributeChecker() if use_model else None)
        self.calibrator = calibrator or Calibrator()
        self.costs = costs or DEFAULT_COSTS

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
        rules = self.checker.run(mandate, cart, now, mapped, priors)
        checks = list(rules.checks)

        # 3. the semantic checker — only when the rules left nothing decisive
        #    and there are soft constraints to judge. A cart already refused by
        #    a hard constraint never reaches a model.
        attrs: AttributeOutcome | None = None
        if not rules.failed and self.attributes and not mandate.soft.is_empty:
            attrs = self.attributes.run(mandate, cart)
            checks.extend(attrs.checks)

        # 4. score -> calibrated probability
        raw, path = _score(rules, attrs)
        p_violation = self.calibrator.transform(raw)

        # 5. expected-cost decision
        policy: PolicyDecision = decide(
            p_violation,
            cart.total_paise,
            self.costs,
            has_hard_failure=bool(rules.failed),
        )

        return VerificationResult(
            verdict=policy.verdict,
            checks=checks,
            explanation=_explain(policy.verdict, checks),
            raw_confidence=raw,
            calibrated_p_violation=p_violation,
            expected_costs=policy.expected_costs,
            mapped=mapped,
            latency_ms=int((time.perf_counter() - started) * 1000),
            path=path,
            consulted_model=bool(attrs and attrs.consulted_model),
            degraded=bool(attrs and attrs.degraded),
            degraded_reason=attrs.degraded_reason if attrs else "",
        )
