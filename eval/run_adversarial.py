"""Run the 40 hand-written adversarial cases and print every one.

04 §6 point 8 asks for all forty individually, with verdict and expected
verdict. Not a summary — the individual table is the artifact, because an
aggregate hides which kinds of hard case the system fails.

**An escalation on a genuinely ambiguous case is a pass.** 04 §3 says so
explicitly. A case may also list other defensible verdicts in `accept_also`;
those count as passes and are marked, so the distinction between "right" and
"defensible" stays visible rather than being quietly folded into one number.

The most important column is the last one: whether a failure was *unsafe*. A
case that should have escalated but allowed is a different kind of wrong from
one that should have allowed and escalated instead. The first is a hole in the
product; the second is friction.

    python eval/run_adversarial.py
    python eval/run_adversarial.py --verbose
"""

from __future__ import annotations

import argparse
import sys

sys.stdout.reconfigure(line_buffering=True)
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.gold.adversarial import load_cases
from warrant.verify import Verifier

SEVERITY = {"ALLOW": 0, "ESCALATE": 1, "REFUSE": 2}


def classify(expected: str, got: str, accept_also: tuple[str, ...]) -> str:
    if got == expected:
        return "pass"
    if got in accept_also:
        return "defensible"
    return "unsafe" if SEVERITY[got] < SEVERITY[expected] else "over-strict"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    verifier = Verifier()
    cases = load_cases()
    rows, outcomes = [], Counter()

    for case in cases:
        mandate, cart = case.build()
        result = verifier.verify(mandate, cart, case.checked_at)
        outcome = classify(case.expected, result.verdict, case.accept_also)
        outcomes[outcome] += 1
        rows.append((case, result, outcome))

    print(f"\n{len(cases)} adversarial cases  |  provider: "
          f"{verifier.attributes.provider.name if verifier.attributes else 'none'}\n")
    print(f"{'id':<5}{'case':<46}{'expect':<10}{'got':<10}{'outcome':<12}")
    print("-" * 83)
    for case, result, outcome in rows:
        mark = {"pass": "", "defensible": " ~", "over-strict": " !",
                "unsafe": " XX"}[outcome]
        print(f"{case.case_id:<5}{case.name[:44]:<46}{case.expected:<10}"
              f"{result.verdict:<10}{outcome + mark:<12}")
        if args.verbose or outcome == "unsafe":
            print(f"       why hard: {case.why_hard}")
            print(f"       verdict : {result.explanation[:110]}")

    total = len(cases)
    ok = outcomes["pass"] + outcomes["defensible"]
    print("\n" + "=" * 83)
    print(f"exact       {outcomes['pass']:>3}/{total}")
    print(f"defensible  {outcomes['defensible']:>3}/{total}   "
          f"(a listed alternative verdict; still a pass)")
    print(f"over-strict {outcomes['over-strict']:>3}/{total}   "
          f"(refused or escalated where something softer was right — friction)")
    print(f"UNSAFE      {outcomes['unsafe']:>3}/{total}   "
          f"(allowed something that needed a human — a hole in the product)")
    print(f"\npassing     {ok}/{total} = {ok / total:.0%}")

    if outcomes["unsafe"]:
        print("\nunsafe cases, in full:")
        for case, result, outcome in rows:
            if outcome == "unsafe":
                print(f"  {case.case_id} {case.name}")
                print(f"     expected {case.expected}, got {result.verdict}")
                print(f"     {case.why_hard}")

    by_tag: dict[str, Counter] = {}
    for case, _, outcome in rows:
        for tag in case.tags:
            by_tag.setdefault(tag, Counter())[outcome] += 1
    print(f"\n{'tag':<16}{'n':>4}{'passing':>10}")
    for tag in sorted(by_tag, key=lambda t: -sum(by_tag[t].values())):
        counts = by_tag[tag]
        n = sum(counts.values())
        p = counts["pass"] + counts["defensible"]
        print(f"{tag:<16}{n:>4}{p / n:>10.0%}")
    print("=" * 83 + "\n")


if __name__ == "__main__":
    main()
