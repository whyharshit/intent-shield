"""Assemble the labelled dataset: conforming pairs, injected violations, splits.

Splitting is **by mandate**, not by cart (04 §4). Carts from one mandate share
its constraint set and its intent text, so letting them straddle a split would
leak the answer: a model tuned on train would have already seen the exact
mandate it is later scored against.

Violation types are balanced *within* each split rather than sampled freely.
04 §4's 400-pair test set spread over twelve types gives ~15 per type, and a
per-type recall on n=15 carries a 95% interval of roughly +/-25 points — too
wide for the headline table 04 §6 asks for. Generation is free, so the dataset
is larger and each type is quota'd. Recorded as P-005 in DECISIONS.md.

Usage:
    python data/generator/make_dataset.py --build
    python data/generator/make_dataset.py --stats
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data.generator.carts import CatalogIndex, build_conforming_cart, checked_at_for
from data.generator.catalog import DEFAULT_SEED, load_catalog
from data.generator.intents import sample_mandates
from data.generator.pairs import ALL_VIOLATIONS, Pair, ViolationType
from data.generator.violations import INJECTORS

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "gold"

# 60/20/20 by mandate, per 04 §4.
SPLIT_FRACTIONS = {"train": 0.60, "validation": 0.20, "test": 0.20}

N_MANDATES = 4_000
CONFORMING_RATIO = 0.55   # 04 §4: roughly 55% conforming, 45% violating
TIGHT_RATIO = 0.12        # share of conforming carts that sit just under the cap


def _split_of(index: int, total: int) -> str:
    """Assign a mandate to a split by position, so the proportions are exact."""
    train_end = int(total * SPLIT_FRACTIONS["train"])
    val_end = train_end + int(total * SPLIT_FRACTIONS["validation"])
    if index < train_end:
        return "train"
    if index < val_end:
        return "validation"
    return "test"


def build(seed: int = DEFAULT_SEED, n_mandates: int = N_MANDATES) -> dict[str, list[Pair]]:
    rng = random.Random(seed)
    catalog = load_catalog()
    index = CatalogIndex(catalog)
    mandates = sample_mandates(n_mandates, seed, catalog_items=catalog)

    splits: dict[str, list[Pair]] = {"train": [], "validation": [], "test": []}
    # per-split, per-type counters so violations stay balanced inside each split
    type_counts: dict[str, Counter] = {k: Counter() for k in splits}
    failures: Counter = Counter()
    unbuildable = 0

    for i, (mandate, template) in enumerate(mandates):
        split = _split_of(i, len(mandates))
        at = checked_at_for(mandate, rng)
        tight = rng.random() < TIGHT_RATIO
        cart = build_conforming_cart(
            mandate, template, index, rng, f"cart_{i:05d}_a", tight=tight
        )
        if cart is None:
            unbuildable += 1
            continue

        if rng.random() < CONFORMING_RATIO:
            splits[split].append(
                Pair(
                    pair_id=f"pair_{i:05d}_conf",
                    mandate=mandate,
                    cart=cart,
                    checked_at=at,
                    label="conforming",
                    expected_verdict="ALLOW",
                    specificity=template.specificity,
                    template_id=template.id,
                    notes="cart at the cap edge" if tight else "",
                )
            )
            continue

        # violating: pick the least-represented type this split can still take
        counts = type_counts[split]
        order = sorted(ALL_VIOLATIONS, key=lambda v: (counts[v], rng.random()))
        injection = None
        for vtype in order:
            attempt = INJECTORS[vtype](mandate, cart, at, [], index, rng)
            if attempt is not None:
                injection = attempt
                break
            failures[vtype] += 1
        if injection is None:
            unbuildable += 1
            continue

        counts[injection.violation] += 1
        splits[split].append(
            Pair(
                pair_id=f"pair_{i:05d}_viol",
                mandate=mandate,
                cart=injection.cart,
                checked_at=injection.checked_at,
                label="violating",
                violation_types=[injection.violation],
                expected_verdict=injection.expected_verdict,
                prior_approvals=injection.prior_approvals,
                specificity=template.specificity,
                template_id=template.id,
                notes=injection.note,
                violation_detail=injection.detail,
            )
        )

    if unbuildable:
        print(f"note: {unbuildable} mandate(s) produced no usable pair", file=sys.stderr)
    return splits


def write(splits: dict[str, list[Pair]], out_dir: Path = OUT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, pairs in splits.items():
        path = out_dir / f"{name}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for p in pairs:
                f.write(p.model_dump_json() + "\n")
        print(f"wrote {len(pairs):>5} pairs -> {path.relative_to(ROOT)}")


def load_split(name: str, out_dir: Path = OUT_DIR) -> list[Pair]:
    path = out_dir / f"{name}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"{path} not built — run `make dataset`")
    with path.open(encoding="utf-8") as f:
        return [Pair.model_validate_json(line) for line in f if line.strip()]


def _stats(splits: dict[str, list[Pair]]) -> None:
    total = sum(len(v) for v in splits.values())
    print(f"\n{total:,} pairs across {len(splits)} splits\n")
    print(f"{'split':<12}{'pairs':>8}{'conforming':>12}{'violating':>11}{'mandates':>10}")
    for name, pairs in splits.items():
        conf = sum(1 for p in pairs if p.label == "conforming")
        mandates = len({p.mandate.mandate_id for p in pairs})
        print(f"{name:<12}{len(pairs):>8,}{conf:>12,}{len(pairs)-conf:>11,}{mandates:>10,}")

    print(f"\n{'violation type':<28}{'train':>8}{'val':>7}{'test':>7}")
    for v in ALL_VIOLATIONS:
        row = [sum(1 for p in splits[s] if v in p.violation_types)
               for s in ("train", "validation", "test")]
        print(f"{v:<28}{row[0]:>8}{row[1]:>7}{row[2]:>7}")

    print(f"\n{'specificity':<14}{'pairs':>8}{'share':>8}")
    spec = Counter(p.specificity for v in splits.values() for p in v)
    for k, n in spec.most_common():
        print(f"{k:<14}{n:>8,}{n/total:>7.0%}")

    # the leak check the split exists to prevent
    ids = {s: {p.mandate.mandate_id for p in v} for s, v in splits.items()}
    for a in ids:
        for b in ids:
            if a < b:
                overlap = ids[a] & ids[b]
                status = f"LEAK: {len(overlap)}" if overlap else "clean"
                print(f"\nmandate overlap {a}/{b}: {status}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--mandates", type=int, default=N_MANDATES)
    args = ap.parse_args()

    splits = build(args.seed, args.mandates)
    if args.build:
        write(splits)
    if args.stats or not args.build:
        _stats(splits)


if __name__ == "__main__":
    main()
