"""Run the AP2 reference baseline and report kill-criterion K1.

Deliberately runs on train + validation only. The test split stays sealed until
the final run (rule 4 / 04 §4). K1 is a question about whether the gap exists at
all, and train answers it just as well.

    python eval/run_baseline.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.generator.make_dataset import build, load_split
from data.generator.pairs import ALL_VIOLATIONS, RESOLVED_BY
from eval.baseline import run as run_baseline
from eval.metrics import Outcome, bootstrap_ci, score, wilson_interval

K1_THRESHOLD = 0.50
"""Above this, the baseline catches 'most' violations and K1 fires."""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument(
        "--splits", default="train,validation",
        help="never include 'test' before the final sealed run",
    )
    args = ap.parse_args()

    names = [s.strip() for s in args.splits.split(",")]
    if "test" in names:
        print(
            "refusing to run on the test split.\n"
            "The test set runs once, at the end (04 §4). Use train/validation.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    try:
        pairs = [p for n in names for p in load_split(n)]
    except FileNotFoundError:
        splits = build(args.seed)
        pairs = [p for n in names for p in splits[n]]

    results = run_baseline(pairs)
    outcomes = [Outcome(pair=p, verdict=r.verdict) for p, r in zip(pairs, results)]
    m = score(outcomes)

    print(f"\nAP2 reference baseline  (total_within_intent + merchant_allowed)")
    print(f"splits: {', '.join(names)}   n={m.n:,}  "
          f"({m.violations:,} violating / {m.conforming:,} conforming)\n")

    lo, hi = bootstrap_ci(outcomes, "recall", seed=args.seed)
    plo, phi = bootstrap_ci(outcomes, "precision", seed=args.seed)
    print(f"  violation recall      {m.recall:>7.1%}   95% CI [{lo:.1%}, {hi:.1%}]")
    print(f"  violation precision   {m.precision:>7.1%}   95% CI [{plo:.1%}, {phi:.1%}]")
    print(f"  missed violations     {m.missed_violations:>7,}")
    print(f"  false positives       {m.false_positives:>7,}"
          f"   (conforming carts refused)")
    print(f"  FP cost / 1,000 txns  Rs {m.fp_cost_per_1000_paise/100:>10,.0f}")

    print(f"\n{'violation type':<28}{'caught':>8}{'n':>6}{'recall':>9}   {'expected layer':<10}")
    for vtype in ALL_VIOLATIONS:
        caught, total = m.per_type_recall[vtype]
        r = caught / total if total else 0.0
        lo_t, hi_t = wilson_interval(caught, total)
        print(f"{vtype:<28}{caught:>8}{total:>6}{r:>9.0%}   "
              f"{RESOLVED_BY[vtype]:<10} [{lo_t:.0%}, {hi_t:.0%}]")

    # --- K1 ---------------------------------------------------------------
    print("\n" + "=" * 68)
    caught_types = [v for v in ALL_VIOLATIONS
                    if m.per_type_recall[v][1] and
                    m.per_type_recall[v][0] / m.per_type_recall[v][1] > 0.5]
    print(f"K1 — kill criterion: does the baseline catch most violations?")
    print(f"     recall {m.recall:.1%} vs threshold {K1_THRESHOLD:.0%}")
    print(f"     types caught (>50% recall): {', '.join(caught_types) or 'none'}")
    if m.recall > K1_THRESHOLD:
        print("\n     *** K1 HAS FIRED ***")
        print("     The baseline catches most violations. Either the gap is not")
        print("     real or the dataset is too easy. Stop and reconsider.")
    else:
        print("\n     K1 has not fired. The baseline catches amount and merchant")
        print("     violations and little else, which is the premise of the")
        print("     project. Proceed.")
    print("=" * 68 + "\n")


if __name__ == "__main__":
    main()
