"""Collect the semantic checker's answers into the cache, resumably.

Separating this from scoring is not a convenience — it is what makes the
evaluation trustworthy on a rate-limited provider.

The free tier cannot sustain ~2,400 calls in one pass: measured, about a third
fail with RESOURCE_EXHAUSTED once the per-minute quota bites. If scoring and
collecting happen together, those failures become escalations, and the reported
escalation rate silently measures the API quota rather than the system. Here
they are just work left to do.

So: this script asks only the questions that are not already cached, retries
across passes with a cooldown between them, and converges. `run_rules.py` then
reads a warm cache and scores deterministically in seconds — the same inputs
give the same numbers every time, which is what 05 §Day-20's "the test set runs
once" actually requires.

    python eval/warm_cache.py --splits train,validation
    python eval/warm_cache.py --splits test --passes 12    # the sealed run
"""

from __future__ import annotations

import argparse
import sys

sys.stdout.reconfigure(line_buffering=True)
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.generator.make_dataset import load_split
from warrant.checks.attributes import (
    SYSTEM_PROMPT,
    AttributeAssessment,
    build_prompt,
    collect_constraints,
    _default_provider,
)
from warrant.checks.cache import ResponseCache, cache_key


def pending_questions(pairs, model: str, cache: ResponseCache):
    """The (key, system, user) triples not yet answered."""
    out = []
    for p in pairs:
        constraints = collect_constraints(p.mandate)
        if not constraints or not p.cart.line_items:
            continue
        prompt = build_prompt(p.mandate, p.cart, constraints)
        key = cache_key(model, SYSTEM_PROMPT, prompt)
        if cache.get(key) is None:
            out.append((key, prompt))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--splits", default="train,validation")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--passes", type=int, default=8)
    ap.add_argument("--cooldown", type=int, default=60,
                    help="seconds between passes, to let quotas refill")
    args = ap.parse_args()

    pairs = [p for n in args.splits.split(",") for p in load_split(n.strip())]
    cache = ResponseCache()
    provider = _default_provider()
    model = str(getattr(provider, "model", provider.name))

    print(f"provider: {provider.name}  model: {model}")
    print(f"pairs: {len(pairs):,}   cache: {cache.size:,} entries\n")

    lock = threading.Lock()

    for attempt in range(1, args.passes + 1):
        todo = pending_questions(pairs, model, cache)
        if not todo:
            print(f"\ncache is complete — {cache.size:,} entries")
            break

        stats: Counter = Counter()

        def ask(item):
            key, prompt = item
            parsed = provider.assess(SYSTEM_PROMPT, prompt, AttributeAssessment)
            with lock:
                if parsed is None:
                    stats["failed"] += 1
                    stats[str(getattr(provider, "last_error", "?"))[:44]] += 1
                else:
                    cache.put(key, parsed.model_dump(), note=model)
                    stats["ok"] += 1

        print(f"pass {attempt}/{args.passes}: {len(todo):,} question(s) outstanding")
        started = time.perf_counter()
        if hasattr(provider, "reset_rate_limits"):
            provider.reset_rate_limits()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            list(pool.map(ask, todo))
        elapsed = time.perf_counter() - started

        rate = stats["ok"] / elapsed * 60 if elapsed else 0
        print(f"  answered {stats['ok']:,}  failed {stats['failed']:,}  "
              f"({rate:.0f}/min, {elapsed:.0f}s)")
        for reason, n in stats.most_common():
            if reason not in ("ok", "failed"):
                print(f"    {n:>4}  {reason}")

        if stats["ok"] == 0 and attempt < args.passes:
            print("  no progress this pass; quota is exhausted")
        if attempt < args.passes:
            remaining = len(pending_questions(pairs, model, cache))
            if not remaining:
                print(f"\ncache is complete — {cache.size:,} entries")
                break
            print(f"  {remaining:,} still outstanding; "
                  f"cooling down {args.cooldown}s\n")
            time.sleep(args.cooldown)

    outstanding = len(pending_questions(pairs, model, cache))
    print(f"\n{'=' * 60}")
    print(f"cache: {cache.size:,} entries   outstanding: {outstanding:,}")
    if outstanding:
        print("Re-run to continue. Scoring with an incomplete cache is honest —")
        print("unanswered constraints escalate — but the escalation rate will")
        print("partly measure the API quota rather than the system.")
    else:
        print("Every question answered. Scoring is now deterministic.")
    print("=" * 60)


if __name__ == "__main__":
    main()
