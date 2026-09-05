"""Hash-chained decision records — tamper-evident without a blockchain.

Each record's hash covers its own canonical content plus the previous record's
hash, so editing any record breaks every hash after it. Anyone holding the log
can recompute the chain and find the first index that does not match.

Why this matters for the actual problem (02 §6): in a dispute, the merchant can
produce more than "the signature was valid". They can produce the check that ran
before the money moved, what it found, and why it allowed or refused — and show
that the record has not been edited since.

Canonicalisation is the load-bearing detail. Two serialisations of the same
record must produce the same bytes, or verification fails on formatting rather
than on tampering: keys sorted, no insignificant whitespace, UTF-8, datetimes
in UTC with a fixed representation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

GENESIS_HASH = "0" * 64
"""`prev_hash` of the first record in a chain. Not a real hash — a fixed
sentinel, so the first record is chained to something rather than to nothing."""

_HASH_FIELDS = ("record_hash",)
"""Excluded when hashing a record: a hash cannot cover itself."""


def _canonical(value: Any) -> Any:
    """Convert to a form with exactly one JSON representation."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("naive datetime in an evidence record")
        return value.astimezone(timezone.utc).isoformat(timespec="microseconds")
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if isinstance(value, float):
        # Floats reach the log through expected_costs. repr round-trips
        # exactly in Python, which keeps recomputation stable.
        return repr(value)
    return value


def canonical_json(payload: dict) -> str:
    return json.dumps(
        _canonical(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def compute_record_hash(record: dict, prev_hash: str) -> str:
    """sha256(canonical(record without its own hash) + prev_hash)."""
    body = {k: v for k, v in record.items() if k not in _HASH_FIELDS}
    body["prev_hash"] = prev_hash
    return hashlib.sha256(
        (canonical_json(body) + prev_hash).encode("utf-8")
    ).hexdigest()


def hash_payload(payload: dict) -> str:
    """Content hash for a mandate or a cart, used to bind a decision to them."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ChainVerification:
    valid: bool
    length: int
    broken_at: int | None = None
    reason: str = ""

    def __bool__(self) -> bool:
        return self.valid


def verify_chain(records: Iterable[dict]) -> ChainVerification:
    """Walk the log and return the first index where the chain breaks.

    Three ways a chain can fail, and they are reported distinctly because they
    mean different things: a record whose content no longer matches its hash
    (the record was edited), a record whose `prev_hash` does not match its
    predecessor (a record was inserted, removed or reordered), and a first
    record not anchored to the genesis sentinel (the head of the log was
    truncated).
    """
    prev = GENESIS_HASH
    count = 0

    for i, record in enumerate(records):
        count = i + 1
        declared_prev = record.get("prev_hash")
        if declared_prev != prev:
            return ChainVerification(
                valid=False, length=count, broken_at=i,
                reason=(
                    "chain is truncated at the head: first record is not "
                    "anchored to the genesis hash"
                    if i == 0 else
                    f"record {i} claims a predecessor that does not match "
                    f"record {i - 1} — a record was inserted, removed or reordered"
                ),
            )

        expected = compute_record_hash(record, prev)
        if record.get("record_hash") != expected:
            return ChainVerification(
                valid=False, length=count, broken_at=i,
                reason=f"record {i} has been edited since it was written",
            )
        prev = expected

    return ChainVerification(valid=True, length=count)
