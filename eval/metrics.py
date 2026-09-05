"""Metrics, with confidence intervals.

Definitions follow 04 §5. Two points where the definition matters more than the
arithmetic:

**Violation recall counts an escalation as a catch.** 04 §5 defines it as
"violations correctly refused *or escalated*", because a violation routed to a
human is not a loss — it is the product working. But the baseline has no third
outcome, so `refuse_only_recall` is reported alongside; comparing Warrant's
three-way recall against a two-way system's would flatter Warrant (P-004).

**False-positive cost is in rupees, not a rate.** It is the number that decides
whether a merchant switches this on (04 §5), so it is reported as lost margin
on wrongly refused carts, scaled per 1,000 transactions.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field

from data.generator.pairs import ALL_VIOLATIONS, Pair, ViolationType

# Cost-model defaults. Overridden by config later (C5); the sensitivity
# analysis in the report varies these rather than treating them as facts.
DEFAULT_MARGIN = 0.18          # merchant gross margin
DEFAULT_ESCALATION_FRICTION = 12_00   # paise, ~Rs 12 of customer friction


@dataclass
class Outcome:
    """One system's verdict on one pair, reduced to what scoring needs."""

    pair: Pair
    verdict: str          # ALLOW | REFUSE | ESCALATE

    @property
    def flagged(self) -> bool:
        """Did the system decline to let this through unchallenged?"""
        return self.verdict in ("REFUSE", "ESCALATE")


@dataclass
class Metrics:
    n: int
    violations: int
    conforming: int

    recall: float                 # refused or escalated / all violations
    refuse_only_recall: float     # refused / all violations
    precision: float              # true violations / all flagged
    escalation_rate: float
    accuracy: float

    missed_violations: int
    false_positives: int          # conforming carts refused outright
    false_positive_cost_paise: int
    fp_cost_per_1000_paise: int

    per_type_recall: dict[str, tuple[int, int]] = field(default_factory=dict)
    confusion: Counter = field(default_factory=Counter)

    def as_row(self, label: str) -> str:
        return (
            f"{label:<22}{self.recall:>9.1%}{self.precision:>11.1%}"
            f"{self.escalation_rate:>13.1%}"
            f"{self.fp_cost_per_1000_paise/100:>16,.0f}"
        )


def score(outcomes: list[Outcome], margin: float = DEFAULT_MARGIN) -> Metrics:
    violations = [o for o in outcomes if o.pair.is_violating]
    conforming = [o for o in outcomes if not o.pair.is_violating]

    caught = [o for o in violations if o.flagged]
    refused = [o for o in violations if o.verdict == "REFUSE"]
    flagged = [o for o in outcomes if o.flagged]

    # A false positive is a conforming cart *refused*. An escalation is not a
    # false positive: the sale is delayed, not lost, and 02 §4 is explicit that
    # escalation is the product rather than a failure mode.
    false_positives = [o for o in conforming if o.verdict == "REFUSE"]
    fp_cost = sum(int(o.pair.cart.total_paise * margin) for o in false_positives)

    per_type: dict[str, tuple[int, int]] = {}
    for vtype in ALL_VIOLATIONS:
        of_type = [o for o in violations if vtype in o.pair.violation_types]
        per_type[vtype] = (sum(1 for o in of_type if o.flagged), len(of_type))

    confusion: Counter = Counter()
    for o in outcomes:
        confusion[(o.pair.label, o.verdict)] += 1

    n = len(outcomes)
    correct = sum(1 for o in outcomes if o.verdict == o.pair.expected_verdict)

    return Metrics(
        n=n,
        violations=len(violations),
        conforming=len(conforming),
        recall=len(caught) / len(violations) if violations else 0.0,
        refuse_only_recall=len(refused) / len(violations) if violations else 0.0,
        precision=sum(1 for o in flagged if o.pair.is_violating) / len(flagged) if flagged else 0.0,
        escalation_rate=sum(1 for o in outcomes if o.verdict == "ESCALATE") / n if n else 0.0,
        accuracy=correct / n if n else 0.0,
        missed_violations=len(violations) - len(caught),
        false_positives=len(false_positives),
        false_positive_cost_paise=fp_cost,
        fp_cost_per_1000_paise=int(fp_cost / n * 1000) if n else 0,
        per_type_recall=per_type,
        confusion=confusion,
    )


def bootstrap_ci(
    outcomes: list[Outcome],
    stat: str = "recall",
    rounds: int = 1_000,
    seed: int = 1337,
    margin: float = DEFAULT_MARGIN,
) -> tuple[float, float]:
    """95% percentile bootstrap interval for one metric.

    04 §6 asks for headline metrics with intervals. Without them a per-type
    recall on ~28 cases reads as more precise than it is.
    """
    rng = random.Random(seed)
    n = len(outcomes)
    if n == 0:
        return (0.0, 0.0)
    samples = []
    for _ in range(rounds):
        draw = [outcomes[rng.randrange(n)] for _ in range(n)]
        try:
            samples.append(getattr(score(draw, margin), stat))
        except ZeroDivisionError:
            continue
    samples.sort()
    lo = samples[int(0.025 * len(samples))]
    hi = samples[int(0.975 * len(samples)) - 1]
    return (lo, hi)


def wilson_interval(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval — well behaved on the small per-type counts."""
    if n == 0:
        return (0.0, 0.0)
    p = hits / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))
