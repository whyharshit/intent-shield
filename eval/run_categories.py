"""Measure category-mapping accuracy — kill criterion K2.

Mapping runs on the product *title*; the catalog's `category` is ground truth
and is never shown to the mapper.

**Methodology.** Leaf centroids are seeded from the taxonomy's own descriptions
and then blended with real product titles. Those titles have to come from
somewhere, so the catalog is split 60/40 by a stable hash: centroids are fitted
on the 60, and every number below is measured on the held-out 40. Fitting and
scoring on the same items would report roughly 91% and mean nothing.

**Three outcomes, not two.** Raw accuracy conflates two very different failures:

* **unknown** — the mapper declined. Safe: an unknown category forces
  escalation, so a human sees it.
* **wrong root** — the mapper was confidently wrong. Dangerous: this is how a
  denied item gets silently approved.

K2 as written in 05 tests raw accuracy against ~80%. That threshold treats a
safe abstention as equivalent to a silent misclassification, which is not how
the system behaves or how the cost model scores it. Both numbers are reported;
the dangerous-error rate is the one to argue about.

    python eval/run_categories.py
    python eval/run_categories.py --no-embeddings   # what embeddings buy
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.generator.catalog import CatalogItem, load_catalog
from eval.metrics import wilson_interval
from warrant.checks.categories import CategoryMapper
from warrant.taxonomy import UNKNOWN, default_taxonomy

K2_THRESHOLD = 0.80
FIT_FRACTION = 6  # out of 10


def split_catalog(items: list[CatalogItem]) -> tuple[list, list]:
    """Deterministic 60/40 split for fitting vs scoring the mapper."""
    def bucket(sku: str) -> int:
        return int(hashlib.sha256(f"cat:{sku}".encode()).hexdigest()[:8], 16) % 10

    fit = [i for i in items if bucket(i.sku) < FIT_FRACTION]
    held = [i for i in items if bucket(i.sku) >= FIT_FRACTION]
    return fit, held


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-embeddings", action="store_true")
    ap.add_argument("--no-fit", action="store_true",
                    help="skip prototype fitting, to show what it buys")
    args = ap.parse_args()

    tax = default_taxonomy()
    items = load_catalog()
    fit_items, held = split_catalog(items)

    mapper = CategoryMapper(tax, use_embeddings=not args.no_embeddings)
    if not args.no_fit:
        mapper.fit_examples([(i.title, i.category) for i in fit_items])

    if mapper.degraded and not args.no_embeddings:
        print("WARNING: embeddings unavailable — running degraded\n", file=sys.stderr)

    mapped = mapper.map_many([(i.title, None) for i in held])

    leaf_ok = root_ok = unknown = wrong = 0
    by_method: Counter = Counter()
    by_root: defaultdict = defaultdict(lambda: [0, 0, 0])  # ok, unknown, n
    confusions: Counter = Counter()

    for item, got in zip(held, mapped):
        by_method[got.method] += 1
        by_root[item.root][2] += 1
        if got.leaf_id == UNKNOWN:
            unknown += 1
            by_root[item.root][1] += 1
            continue
        if got.leaf_id == item.category:
            leaf_ok += 1
        if tax.root_of(got.leaf_id) == item.root:
            root_ok += 1
            by_root[item.root][0] += 1
        else:
            wrong += 1
            confusions[(item.root, tax.root_of(got.leaf_id))] += 1

    n = len(held)
    print(f"\ncategory mapping — mapped from title only")
    print(f"fitted on {len(fit_items)} SKUs, scored on {n} held out")
    print(f"embeddings: {'off' if mapper.degraded else 'on'}"
          f"   prototypes: {'off' if args.no_fit else 'on'}\n")

    rlo, rhi = wilson_interval(root_ok, n)
    llo, lhi = wilson_interval(leaf_ok, n)
    print(f"  correct root      {root_ok/n:>7.1%}   [{rlo:.0%}, {rhi:.0%}]"
          f"  <- what the denied-category check needs")
    print(f"  correct leaf      {leaf_ok/n:>7.1%}   [{llo:.0%}, {lhi:.0%}]")
    print(f"  unknown           {unknown/n:>7.1%}   safe — forces escalation")
    print(f"  WRONG root        {wrong/n:>7.1%}   dangerous — silent misclassification")

    print(f"\n{'resolved by':<20}{'n':>7}{'share':>9}")
    for method, count in by_method.most_common():
        print(f"{method:<20}{count:>7}{count/n:>9.1%}")

    print(f"\n{'root':<16}{'correct':>9}{'unknown':>9}{'wrong':>8}{'n':>5}")
    for root in sorted(by_root):
        ok, unk, total = by_root[root]
        print(f"{root:<16}{ok/total:>9.0%}{unk/total:>9.0%}"
              f"{(total-ok-unk)/total:>8.0%}{total:>5}")

    if confusions:
        print(f"\ntop dangerous confusions (true -> predicted)")
        for (truth, got), count in confusions.most_common(6):
            print(f"  {count:>4}  {truth} -> {got}")

    # --- the case the demo rests on --------------------------------------
    alcohol = [(i, g) for i, g in zip(held, mapped) if i.root == "alcohol"]
    if alcohol:
        caught = sum(1 for _, g in alcohol
                     if g.is_known and tax.root_of(g.leaf_id) == "alcohol")
        leaked = [(i, g) for i, g in alcohol
                  if g.is_known and tax.root_of(g.leaf_id) != "alcohol"]
        print(f"\nalcohol -> alcohol: {caught}/{len(alcohol)} = "
              f"{caught/len(alcohol):.0%}")
        print(f"  leaked to a non-alcohol root: {len(leaked)}"
              f"   <- these would pass a no-alcohol mandate")
        for i, g in leaked[:5]:
            print(f"    {i.title[:50]:<50} -> {g.leaf_id}")

    print("\n" + "=" * 70)
    print(f"K2 — kill criterion: category accuracy below ~{K2_THRESHOLD:.0%}?")
    print(f"     correct root {root_ok/n:.1%}   "
          f"dangerous errors {wrong/n:.1%}   abstentions {unknown/n:.1%}")
    if root_ok / n < K2_THRESHOLD:
        print("\n     *** K2 HAS FIRED on raw accuracy ***")
        print("     Judge it on the dangerous-error rate before abandoning:")
        print(f"     {wrong/n:.1%} silent misclassification, {unknown/n:.1%} escalated.")
    else:
        print("\n     K2 has not fired.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
