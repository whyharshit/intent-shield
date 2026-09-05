"""The append-only decision log.

SQLite, one file, ships in the repo (03 §4). Every verification writes one
immutable record chained to the previous one; `verify()` recomputes the chain.

Append-only is enforced by the schema rather than by convention: triggers reject
UPDATE and DELETE on the decisions table. That does not stop someone with the
file from rewriting it with another tool — nothing short of an external witness
would — but it does mean the application cannot corrupt the log by accident, and
any external edit shows up as a broken chain.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from warrant.evidence.chain import (
    GENESIS_HASH,
    ChainVerification,
    compute_record_hash,
    hash_payload,
    verify_chain,
)
from warrant.models import Cart, CheckResult, Decision, IntentMandate

DEFAULT_DB = Path(os.environ.get("WARRANT_DB_PATH", "data/warrant.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    seq                    INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id            TEXT NOT NULL UNIQUE,
    mandate_id             TEXT NOT NULL,
    mandate_hash           TEXT NOT NULL,
    cart_hash              TEXT NOT NULL,
    verdict                TEXT NOT NULL,
    raw_confidence         REAL NOT NULL,
    calibrated_p_violation REAL NOT NULL,
    checks_json            TEXT NOT NULL,
    explanation            TEXT NOT NULL,
    expected_costs_json    TEXT NOT NULL,
    latency_ms             INTEGER NOT NULL,
    timestamp              TEXT NOT NULL,
    prev_hash              TEXT NOT NULL,
    record_hash            TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_decisions_mandate ON decisions(mandate_id);

-- Append-only. The application cannot rewrite history even by mistake.
CREATE TRIGGER IF NOT EXISTS decisions_no_update
BEFORE UPDATE ON decisions
BEGIN
    SELECT RAISE(ABORT, 'decision log is append-only');
END;

CREATE TRIGGER IF NOT EXISTS decisions_no_delete
BEFORE DELETE ON decisions
BEGIN
    SELECT RAISE(ABORT, 'decision log is append-only');
END;

CREATE TABLE IF NOT EXISTS resolutions (
    decision_id  TEXT PRIMARY KEY,
    resolved_at  TEXT NOT NULL,
    resolved_by  TEXT NOT NULL,
    outcome      TEXT NOT NULL,
    note         TEXT NOT NULL DEFAULT ''
);
"""

_ORDERED_FIELDS = (
    "decision_id", "mandate_id", "mandate_hash", "cart_hash", "verdict",
    "raw_confidence", "calibrated_p_violation", "checks_json", "explanation",
    "expected_costs_json", "latency_ms", "timestamp", "prev_hash", "record_hash",
)


def _record_body(row: dict) -> dict:
    """The hashed view of a row: JSON columns decoded, seq excluded.

    `seq` is a storage detail assigned by SQLite; including it would make the
    hash depend on insertion order in a second, redundant way and would break
    verification of a log exported and re-imported elsewhere.
    """
    return {
        "decision_id": row["decision_id"],
        "mandate_id": row["mandate_id"],
        "mandate_hash": row["mandate_hash"],
        "cart_hash": row["cart_hash"],
        "verdict": row["verdict"],
        "raw_confidence": row["raw_confidence"],
        "calibrated_p_violation": row["calibrated_p_violation"],
        "checks": json.loads(row["checks_json"]),
        "explanation": row["explanation"],
        "expected_costs": json.loads(row["expected_costs_json"]),
        "latency_ms": row["latency_ms"],
        "timestamp": row["timestamp"],
        "prev_hash": row["prev_hash"],
        "record_hash": row["record_hash"],
    }


class EvidenceLog:
    def __init__(self, path: Path | str = DEFAULT_DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    # -- writing -----------------------------------------------------------

    def append(
        self,
        mandate: IntentMandate,
        cart: Cart,
        verdict: str,
        checks: list[CheckResult],
        explanation: str,
        raw_confidence: float,
        calibrated_p_violation: float,
        expected_costs: dict[str, float],
        latency_ms: int,
        timestamp: datetime | None = None,
    ) -> Decision:
        timestamp = timestamp or datetime.now(timezone.utc)
        checks_payload = [c.model_dump() for c in checks]

        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT record_hash FROM decisions ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            prev_hash = row["record_hash"] if row else GENESIS_HASH

            body = {
                "decision_id": f"dec_{uuid.uuid4().hex[:16]}",
                "mandate_id": mandate.mandate_id,
                "mandate_hash": hash_payload(mandate.model_dump(mode="json")),
                "cart_hash": hash_payload(cart.model_dump(mode="json")),
                "verdict": verdict,
                "raw_confidence": raw_confidence,
                "calibrated_p_violation": calibrated_p_violation,
                "checks": checks_payload,
                "explanation": explanation,
                "expected_costs": expected_costs,
                "latency_ms": latency_ms,
                "timestamp": timestamp,
                "prev_hash": prev_hash,
            }
            record_hash = compute_record_hash(body, prev_hash)

            conn.execute(
                f"INSERT INTO decisions ({','.join(_ORDERED_FIELDS)}) "
                f"VALUES ({','.join('?' * len(_ORDERED_FIELDS))})",
                (
                    body["decision_id"], body["mandate_id"], body["mandate_hash"],
                    body["cart_hash"], verdict, raw_confidence,
                    calibrated_p_violation, json.dumps(checks_payload),
                    explanation, json.dumps(expected_costs), latency_ms,
                    timestamp.astimezone(timezone.utc).isoformat(
                        timespec="microseconds"
                    ),
                    prev_hash, record_hash,
                ),
            )
            conn.commit()

        return Decision(
            decision_id=body["decision_id"],
            mandate_id=body["mandate_id"],
            mandate_hash=body["mandate_hash"],
            cart_hash=body["cart_hash"],
            verdict=verdict,  # type: ignore[arg-type]
            raw_confidence=raw_confidence,
            calibrated_p_violation=calibrated_p_violation,
            checks=checks,
            explanation=explanation,
            expected_costs=expected_costs,
            latency_ms=latency_ms,
            timestamp=timestamp,
            prev_hash=prev_hash,
            record_hash=record_hash,
        )

    def record_resolution(
        self, decision_id: str, resolved_by: str, outcome: str, note: str = ""
    ) -> None:
        """A human's answer to an escalation.

        Kept in its own table rather than mutating the decision. The decision
        records what the system concluded before money moved; the resolution
        records what a person decided afterwards. Editing the first to carry
        the second would destroy the evidence value of both.
        """
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO resolutions "
                "(decision_id, resolved_at, resolved_by, outcome, note) "
                "VALUES (?,?,?,?,?)",
                (
                    decision_id,
                    datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                    resolved_by, outcome, note,
                ),
            )
            conn.commit()

    # -- reading -----------------------------------------------------------

    def all_records(self) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM decisions ORDER BY seq").fetchall()
        return [_record_body(dict(r)) for r in rows]

    def for_mandate(self, mandate_id: str) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM decisions WHERE mandate_id = ? ORDER BY seq",
                (mandate_id,),
            ).fetchall()
        return [_record_body(dict(r)) for r in rows]

    def resolution(self, decision_id: str) -> dict | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM resolutions WHERE decision_id = ?", (decision_id,)
            ).fetchone()
        return dict(row) if row else None

    def verify(self) -> ChainVerification:
        return verify_chain(self.all_records())

    def __len__(self) -> int:
        with closing(self._connect()) as conn:
            return conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
