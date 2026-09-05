"""Generate eval/REPORT.md — the eleven sections 04 §6 asks for.

Two guards on the test split, because rule 4 is the one that is easiest to
break by accident and impossible to undo:

* `--split test` refuses unless `--sealed` is passed as well.
* A sealed run records a fingerprint in `eval/.sealed_runs.json`. Running it
  twice is reported loudly, because 05 §Day-20 says the test set runs once and
  a second run after seeing the first is tuning, whatever it is called.

Calibration is fitted on validation and never on test.

    python eval/run_eval.py                    # train+validation
    python eval/run_eval.py --split test --sealed
"""

from __future__ import annotations

import argparse
import json
import sys

sys.stdout.reconfigure(line_buffering=True)
import hashlib
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.generator.make_dataset import load_split
from data.generator.pairs import ALL_VIOLATIONS, RESOLVED_BY
from data.gold.adversarial import load_cases
from eval.baseline import run as run_baseline
from eval.metrics import Outcome, bootstrap_ci, score, wilson_interval
from eval.run_adversarial import classify
from eval.run_rules import verify_all
from warrant.checks.cache import ResponseCache
from warrant.decide.calibration import (
    Calibrator,
    expected_calibration_error,
    reliability_bins,
)
from warrant.decide.costs import DEFAULT_COSTS, CostModel
from warrant.decide.policy import thresholds_for
from warrant.verify import Verifier

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "eval" / "REPORT.md"
SEALED_LOG = ROOT / "eval" / ".sealed_runs.json"


def _fingerprint(pairs) -> str:
    h = hashlib.sha256()
    for p in pairs:
        h.update(p.pair_id.encode())
    return h.hexdigest()[:16]


def _check_sealed(pairs, force: bool) -> str | None:
    fp = _fingerprint(pairs)
    log = json.loads(SEALED_LOG.read_text()) if SEALED_LOG.exists() else {}
    previous = log.get(fp)
    if previous and not force:
        return previous
    log[fp] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    SEALED_LOG.write_text(json.dumps(log, indent=2))
    return None


def fit_calibration(seed: int) -> Calibrator:
    """Isotonic on the validation split only (03 §3.4, rule 4)."""
    pairs = load_split("validation")
    verifier = Verifier(use_model=False)
    results = verify_all(pairs, verifier, workers=1)
    raw = [r.raw_confidence for r in results]
    labels = [1 if p.is_violating else 0 for p in pairs]
    cal = Calibrator().fit(raw, labels)
    cal.save()
    return cal


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--split", default="train,validation")
    ap.add_argument("--sealed", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--no-model", action="store_true",
                    help="rules and categories only; report says so")
    args = ap.parse_args()

    names = [s.strip() for s in args.split.split(",")]
    if "test" in names and not args.sealed:
        print(
            "The test split runs once, at the end (04 §4, rule 4).\n"
            "Pass --sealed to confirm this is that run.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    pairs = [p for n in names for p in load_split(n)]
    reran = None
    if "test" in names:
        reran = _check_sealed(pairs, args.force)

    if args.no_model:
        import os
        os.environ["WARRANT_PROVIDER"] = "none"

    print("fitting calibration on validation...")
    cal = Calibrator.load()
    if not cal.fitted:
        cal = fit_calibration(args.seed)
    print(f"  {'fitted' if cal.fitted else 'NOT fitted'}  "
          f"n_effective={cal.n_effective}  "
          f"ECE {cal.ece_before:.3f} -> {cal.ece_after:.3f}")

    print(f"scoring {len(pairs):,} pairs...")
    verifier = Verifier(calibrator=cal, use_model=not args.no_model)
    results = verify_all(pairs, verifier, args.workers)
    warrant = [Outcome(pair=p, verdict=r.verdict) for p, r in zip(pairs, results)]
    base = [Outcome(pair=p, verdict=r.verdict)
            for p, r in zip(pairs, run_baseline(pairs))]
    wm, bm = score(warrant), score(base)

    print("running the 40 adversarial cases...")
    adv_rows = []
    for case in load_cases():
        m, c = case.build()
        r = verifier.verify(m, c, case.checked_at, case.priors())
        adv_rows.append((case, r, classify(case.expected, r.verdict, case.accept_also)))
    adv = Counter(o for _, _, o in adv_rows)

    cache = ResponseCache()
    degraded = sum(1 for r in results if r.degraded)
    lo, hi = bootstrap_ci(warrant, "recall", seed=args.seed)
    plo, phi = bootstrap_ci(warrant, "precision", seed=args.seed)
    lat = sorted(r.latency_ms for r in results)
    lat_rule = sorted(r.latency_ms for r in results if not r.consulted_model)

    def pct(xs, q):
        return xs[min(int(len(xs) * q), len(xs) - 1)] if xs else 0

    w = []
    a = w.append
    a("# Warrant — evaluation report\n")
    a(f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · "
      f"splits: **{', '.join(names)}** · seed {args.seed}\n")
    if reran:
        a(f"> **This test split was already run on {reran}.** 05 §Day-20 says "
          f"the test set runs once. Numbers below are from a repeat run and "
          f"should be read as such.\n")
    if args.no_model:
        a(
            "> ## These are not the system's numbers\n>\n"
            "> This run had the semantic checker **switched off**\n"
            "> (`--no-model`), so every soft constraint went unassessed and\n"
            "> escalated on the fail-closed path. Recall is inflated toward\n"
            "> 100% by escalating nearly everything, and precision sits near\n"
            "> the base rate.\n>\n"
            "> The rule and category layers below are real. The headline\n"
            "> metrics are not. Re-run without `--no-model` once the model\n"
            "> quota allows.\n"
        )
    if degraded:
        a(f"> **{degraded}/{len(results)} pairs had an unavailable semantic "
          f"checker** and escalated on the fail-closed path. Recall is "
          f"inflated and precision deflated by that. Not clean numbers.\n")

    a("\n## 1. Dataset composition\n")
    a(f"| | |\n|---|---|\n| pairs | {wm.n:,} |\n| violating | {wm.violations:,} |")
    a(f"| conforming | {wm.conforming:,} |")
    a(f"| cached model answers | {cache.size:,} |\n")

    a("\n## 2. Headline metrics\n")
    a("| metric | Warrant | baseline (`total_within_intent` + `merchant_allowed`) |")
    a("|---|---|---|")
    a(f"| violation recall | **{wm.recall:.1%}** [{lo:.1%}, {hi:.1%}] | {bm.recall:.1%} |")
    a(f"| refuse-only recall | {wm.refuse_only_recall:.1%} | {bm.recall:.1%} |")
    a(f"| precision | {wm.precision:.1%} [{plo:.1%}, {phi:.1%}] | {bm.precision:.1%} |")
    a(f"| escalation rate | {wm.escalation_rate:.1%} | n/a (two outcomes) |")
    a(f"| false positives | {wm.false_positives:,} | {bm.false_positives:,} |")
    a(f"| **FP cost / 1,000 txns** | **Rs {wm.fp_cost_per_1000_paise/100:,.0f}** | "
      f"Rs {bm.fp_cost_per_1000_paise/100:,.0f} |")
    a(f"| missed violations | {wm.missed_violations:,} | {bm.missed_violations:,} |\n")
    a("Recall counts an escalation as a catch, per 04 §5. The baseline has no "
      "third outcome, so refuse-only recall is the like-for-like column.\n")

    a("\n## 3. Per violation type\n")
    a("| type | baseline | Warrant | n | 95% CI | expected layer |")
    a("|---|---|---|---|---|---|")
    for v in ALL_VIOLATIONS:
        wc, n = wm.per_type_recall[v]
        bc, _ = bm.per_type_recall[v]
        clo, chi = wilson_interval(wc, n)
        a(f"| `{v}` | {bc/n if n else 0:.0%} | **{wc/n if n else 0:.0%}** | {n} | "
          f"[{clo:.0%}, {chi:.0%}] | {RESOLVED_BY[v]} |")

    a("\n## 4. Baseline comparison\n")
    a(f"The baseline catches {sum(1 for v in ALL_VIOLATIONS if bm.per_type_recall[v][0])} "
      f"of 12 violation types. Its precision is {bm.precision:.0%} with "
      f"{bm.false_positives} false positives — it is not inaccurate about what "
      f"it checks, it is incomplete.\n")

    a("\n## 5. Calibration\n")
    a(f"Isotonic regression, fitted on validation only. "
      f"ECE {cal.ece_before:.3f} → **{cal.ece_after:.3f}** on "
      f"n_effective={cal.n_effective}.\n")
    if cal.ece_after < 0.01:
        a(
            "\n> An ECE at or near zero is a warning, not a triumph. The\n"
            "> pipeline emits only five distinct raw scores by provenance, and\n"
            "> isotonic regression fits five points exactly. This number will\n"
            "> mean something once the semantic checker contributes a genuinely\n"
            "> graded confidence — see DECISIONS.md L-016.\n"
        )
    probs = [r.calibrated_p_violation for r in results]
    labels = [1 if p.is_violating else 0 for p in pairs]
    a(f"Post-calibration ECE on this split: "
      f"**{expected_calibration_error(probs, labels):.3f}**\n")
    a("\n| predicted | observed | n |\n|---|---|---|")
    for b in reliability_bins(probs, labels):
        if b["n"]:
            a(f"| {b['predicted']:.2f} | {b['observed']:.2f} | {b['n']} |")
    a("\nMost decisions are settled by rules, which produce a hard 0 or 1 with "
      "no gradation to calibrate. The effective calibration set is much "
      "smaller than the validation split — see DECISIONS.md L-016.\n")

    a("\n## 6. Cost curve and operating point\n")
    a("| cart value | allow below p | refuse above p | escalation band |")
    a("|---|---|---|---|")
    for rs in (200, 500, 2_000, 5_000, 15_000, 40_000):
        alo, ahi = thresholds_for(rs * 100)
        a(f"| Rs {rs:,} | {alo:.3f} | {ahi:.3f} | {ahi-alo:.3f} |")
    a("\nThresholds are derived from the expected-cost model, not chosen. Both "
      "move with cart value, and a large cart escalates at *lower* uncertainty "
      "— 02 §5.\n")

    a("\n## 7. Sensitivity to cost parameters\n")
    a("| parameter | value | allow-below p @ Rs 2,000 |\n|---|---|---|")
    for label, model in (
        ("default", DEFAULT_COSTS),
        ("p_dispute 0.15", CostModel(p_dispute=0.15)),
        ("p_dispute 0.60", CostModel(p_dispute=0.60)),
        ("margin 0.03", CostModel(margin=0.03)),
        ("margin 0.40", CostModel(margin=0.40)),
        ("friction Rs 50", CostModel(friction_cost_paise=5_000)),
    ):
        alo, _ = thresholds_for(200_000, model)
        a(f"| {label} | | {alo:.3f} |")
    a("\n`p_dispute` is the least defensible number in the model and is varied "
      "hardest. See warrant/decide/costs.py — every field states its source.\n")

    a("\n## 8. Adversarial cases — all 40\n")
    a(f"**{adv['pass'] + adv['defensible']}/40 passing.** "
      f"exact {adv['pass']}, defensible {adv['defensible']}, "
      f"over-strict {adv['over-strict']}, **unsafe {adv['unsafe']}**\n")
    a("\nAn escalation on a genuinely ambiguous case is a pass (04 §3). "
      "*Unsafe* means the system allowed something that needed a human — the "
      "only column that represents a hole in the product.\n")
    a("\n| id | case | expected | got | outcome |\n|---|---|---|---|---|")
    for case, r, outcome in adv_rows:
        a(f"| {case.case_id} | {case.name} | {case.expected} | {r.verdict} | "
          f"{'**' + outcome + '**' if outcome == 'unsafe' else outcome} |")

    a("\n## 9. Full escalation list — unedited\n")
    esc = [(p, r) for p, r in zip(pairs, results) if r.verdict == "ESCALATE"]
    a(f"{len(esc):,} escalations. Every one, as 04 §6 point 9 requires.\n")
    a("\n| pair | label | why |\n|---|---|---|")
    for p, r in esc:
        a(f"| `{p.pair_id}` | {p.label} | {r.explanation[:150].replace('|', '/')} |")

    a("\n## 10. Latency\n")
    a(f"| path | p50 | p95 | max |\n|---|---|---|---|")
    a(f"| overall | {pct(lat,0.5)}ms | {pct(lat,0.95)}ms | {lat[-1] if lat else 0}ms |")
    if lat_rule:
        a(f"| rules only | {pct(lat_rule,0.5)}ms | {pct(lat_rule,0.95)}ms | "
          f"{lat_rule[-1]}ms |")
    a(f"\nThe 300ms p95 budget in 03 §5 applies to the deterministic path.\n")

    a("\n## 11. Known failure modes\n")
    a("Written by hand, not generated. See DECISIONS.md for the full list.\n")
    a("\n1. **Substitution is the weakest violation type** — it needs world "
      "knowledge about what counts as materially equivalent, and the taxonomy "
      "is coarse there.")
    a("2. **Category accuracy is per item; carts compound it.** 82% per line at "
      "4.2 lines per cart means a cart clears cleanly about half the time.")
    a("3. **The taxonomy has near-duplicate leaves across roots** "
      "(`beverages_soft` vs `beverages_restaurant`), which drives most "
      "remaining category errors.")
    a("4. **Escalation is high.** Every uncertainty escalates; the cost policy "
      "narrows this but does not eliminate it.")
    a("5. **Data is synthetic in its labels.** Products and prices are real; "
      "mandates, carts and violations are generated. No public corpus of "
      "agent-initiated disputes exists.\n")

    REPORT.write_text("\n".join(w), encoding="utf-8")
    print(f"\nwrote {REPORT.relative_to(ROOT)}  ({len(w)} lines)")
    print(f"  recall {wm.recall:.1%}  precision {wm.precision:.1%}  "
          f"escalation {wm.escalation_rate:.1%}  "
          f"FP cost Rs {wm.fp_cost_per_1000_paise/100:,.0f}/1k")
    print(f"  adversarial {adv['pass'] + adv['defensible']}/40, "
          f"unsafe {adv['unsafe']}")


if __name__ == "__main__":
    main()
