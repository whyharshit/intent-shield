"""Run the rules + category pipeline and compare it against the baseline.

Train and validation only. The test split stays sealed.

Also reports kill criterion K3: if the deterministic path resolves under 40% of
cases, every transaction ends up at a language model and the latency and cost
make the system unusable.

    python eval/run_rules.py
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.generator.make_dataset import build, load_split
from data.generator.pairs import ALL_VIOLATIONS, RESOLVED_BY, Pair
from eval.baseline import run as run_baseline
from eval.metrics import Outcome, bootstrap_ci, score, wilson_interval
from warrant.checks.deterministic import PriorApproval
from warrant.verify import Verifier

K3_THRESHOLD = 0.40


def verify_all(pairs: list[Pair], verifier: Verifier):
    out = []
    for p in pairs:
        priors = [
            PriorApproval(approved_at=a.approved_at, amount_paise=a.amount_paise)
            for a in p.prior_approvals
        ]
        out.append(verifier.verify(p.mandate, p.cart, p.checked_at, priors))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--splits", default="train,validation")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    names = [s.strip() for s in args.splits.split(",")]
    if "test" in names:
        print("refusing to run on the test split (04 §4).", file=sys.stderr)
        raise SystemExit(2)

    try:
        pairs = [p for n in names for p in load_split(n)]
    except FileNotFoundError:
        splits = build(args.seed)
        pairs = [p for n in names for p in splits[n]]
    if args.limit:
        pairs = pairs[: args.limit]

    verifier = Verifier()
    if verifier.mapper.degraded:
        print("WARNING: embeddings unavailable — mapper degraded\n", file=sys.stderr)

    results = verify_all(pairs, verifier)
    warrant = [Outcome(pair=p, verdict=r.verdict) for p, r in zip(pairs, results)]
    base = [
        Outcome(pair=p, verdict=r.verdict)
        for p, r in zip(pairs, run_baseline(pairs))
    ]

    wm, bm = score(warrant), score(base)

    print(f"\nrules + category mapping   splits: {', '.join(names)}   n={wm.n:,}")
    print(f"({wm.violations:,} violating / {wm.conforming:,} conforming)\n")

    print(f"{'':<22}{'recall':>9}{'precision':>11}{'escalation':>13}{'FP cost/1k':>16}")
    print(f"{'baseline (AP2)':<22}{bm.recall:>9.1%}{bm.precision:>11.1%}"
          f"{bm.escalation_rate:>13.1%}{bm.fp_cost_per_1000_paise/100:>16,.0f}")
    print(f"{'Warrant (rules)':<22}{wm.recall:>9.1%}{wm.precision:>11.1%}"
          f"{wm.escalation_rate:>13.1%}{wm.fp_cost_per_1000_paise/100:>16,.0f}")

    lo, hi = bootstrap_ci(warrant, "recall", seed=args.seed)
    plo, phi = bootstrap_ci(warrant, "precision", seed=args.seed)
    print(f"\n  recall            {wm.recall:>7.1%}  95% CI [{lo:.1%}, {hi:.1%}]")
    print(f"  refuse-only       {wm.refuse_only_recall:>7.1%}"
          f"  (comparable with the two-way baseline)")
    print(f"  precision         {wm.precision:>7.1%}  95% CI [{plo:.1%}, {phi:.1%}]")
    print(f"  missed violations {wm.missed_violations:>7,}")
    print(f"  false positives   {wm.false_positives:>7,}  conforming carts REFUSED")
    print(f"  FP cost / 1,000   Rs {wm.fp_cost_per_1000_paise/100:>8,.0f}")

    print(f"\n{'violation type':<28}{'baseline':>10}{'warrant':>10}{'n':>6}"
          f"   {'layer':<9}")
    for vtype in ALL_VIOLATIONS:
        wc, total = wm.per_type_recall[vtype]
        bc, _ = bm.per_type_recall[vtype]
        wr = wc / total if total else 0.0
        br = bc / total if total else 0.0
        mark = "  <-- new" if wr > br + 0.2 else ""
        print(f"{vtype:<28}{br:>10.0%}{wr:>10.0%}{total:>6}   "
              f"{RESOLVED_BY[vtype]:<9}{mark}")

    # --- verdict distribution --------------------------------------------
    print(f"\n{'verdict':<12}{'conforming':>12}{'violating':>11}")
    for verdict in ("ALLOW", "REFUSE", "ESCALATE"):
        c = wm.confusion[("conforming", verdict)]
        v = wm.confusion[("violating", verdict)]
        print(f"{verdict:<12}{c:>12,}{v:>11,}")

    # --- K3 ---------------------------------------------------------------
    #
    # K3 asks how much traffic reaches a *language model* — 05 phrases it as
    # "every transaction hitting an LLM means unusable latency and cost". An
    # escalation goes to a human, not to a model, so it is not LLM traffic.
    # The number that matters is how much would reach C4 stage 2.
    settled = sum(1 for r in results if r.verdict in ("REFUSE", "ALLOW")
                  and not r.soft_constraints_pending)
    escalated = sum(1 for r in results if r.verdict == "ESCALATE")
    pending = sum(1 for r in results if r.soft_constraints_pending)
    lat = sorted(r.latency_ms for r in results)

    print(f"\n{'path':<34}{'n':>7}{'share':>9}")
    print(f"{'settled by rules alone':<34}{settled:>7}{settled/wm.n:>9.1%}")
    print(f"{'escalated (uncertain)':<34}{escalated:>7}{escalated/wm.n:>9.1%}")
    print(f"{'would reach the semantic checker':<34}{pending:>7}{pending/wm.n:>9.1%}")
    print(f"\nlatency p50 {lat[len(lat)//2]}ms   "
          f"p95 {lat[int(len(lat)*0.95)]}ms   max {lat[-1]}ms")

    no_model = 1 - pending / wm.n
    print("\n" + "=" * 70)
    print("K3 — kill criterion: does too much traffic reach a language model?")
    print(f"     {no_model:.1%} settled without a model "
          f"({settled/wm.n:.1%} by rules, {escalated/wm.n:.1%} to a human)")
    print(f"     {pending/wm.n:.1%} would reach C4 stage 2")
    if no_model < K3_THRESHOLD:
        print("\n     *** K3 HAS FIRED *** too much traffic reaches the model.")
    else:
        print("\n     K3 has not fired.")
    if wm.escalation_rate > 0.25:
        print(f"\n     NOTE: escalation is {wm.escalation_rate:.1%}, too high to ship.")
        print("     Every uncertainty escalates because C5 does not exist yet.")
        print("     The expected-cost policy should weigh the amount at risk and")
        print("     bring this down. Treat it as an upper bound, not a result.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
