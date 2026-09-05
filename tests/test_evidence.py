"""Evidence log tests.

03 §3.6 asks specifically for a test that mutates a record and asserts the
chain detects it. That is `test_editing_a_record_breaks_the_chain`; the rest
cover the ways a log can be tampered with that a naive chain would miss —
removing a record, reordering two, truncating the head.
"""

from __future__ import annotations

import sqlite3
from datetime import timedelta

import pytest

from conftest import NOW, cart, line
from warrant.evidence.chain import (
    GENESIS_HASH,
    canonical_json,
    compute_record_hash,
    hash_payload,
    verify_chain,
)
from warrant.evidence.log import EvidenceLog
from warrant.models import CheckResult


@pytest.fixture
def log(tmp_path) -> EvidenceLog:
    return EvidenceLog(tmp_path / "warrant.db")


def _append(log: EvidenceLog, mandate, verdict="ALLOW", n=1, **kw):
    out = []
    for i in range(n):
        out.append(log.append(
            mandate=mandate,
            cart=cart(line(f"line_{i:03d}", unit=10_000 + i, title="Amul Butter")),
            verdict=verdict,
            checks=[CheckResult(check="amount_ceiling", result="pass",
                                decided_by="rule", detail="within cap")],
            explanation="all checks passed",
            raw_confidence=0.02,
            calibrated_p_violation=0.01,
            expected_costs={"ALLOW": 12.5, "REFUSE": 660.0, "ESCALATE": 151.0},
            latency_ms=7,
            timestamp=NOW + timedelta(seconds=i),
            **kw,
        ))
    return out


# ---------------------------------------------------------------------------
# canonicalisation
# ---------------------------------------------------------------------------


def test_key_order_does_not_change_the_hash() -> None:
    """Otherwise verification would fail on formatting rather than tampering."""
    a = {"b": 1, "a": 2, "c": {"z": 3, "y": 4}}
    b = {"c": {"y": 4, "z": 3}, "a": 2, "b": 1}
    assert canonical_json(a) == canonical_json(b)
    assert hash_payload(a) == hash_payload(b)


def test_naive_datetimes_are_rejected() -> None:
    from datetime import datetime

    with pytest.raises(ValueError, match="naive datetime"):
        canonical_json({"t": datetime(2026, 9, 5, 12, 0)})


def test_different_content_gives_a_different_hash() -> None:
    assert hash_payload({"a": 1}) != hash_payload({"a": 2})


# ---------------------------------------------------------------------------
# the chain
# ---------------------------------------------------------------------------


def test_an_empty_log_verifies(log: EvidenceLog) -> None:
    result = log.verify()
    assert result.valid and result.length == 0


def test_a_written_chain_verifies(log: EvidenceLog, mandate) -> None:
    _append(log, mandate, n=5)
    result = log.verify()
    assert result, result.reason
    assert result.length == 5


def test_the_first_record_anchors_to_genesis(log: EvidenceLog, mandate) -> None:
    _append(log, mandate, n=1)
    assert log.all_records()[0]["prev_hash"] == GENESIS_HASH


def test_each_record_chains_to_its_predecessor(log: EvidenceLog, mandate) -> None:
    _append(log, mandate, n=4)
    records = log.all_records()
    for prev, nxt in zip(records, records[1:]):
        assert nxt["prev_hash"] == prev["record_hash"]


def test_editing_a_record_breaks_the_chain(log: EvidenceLog, mandate) -> None:
    """The test 03 §3.6 asks for by name.

    A refusal quietly rewritten to an approval — the exact tampering the log
    exists to make detectable.
    """
    _append(log, mandate, n=5)
    assert log.verify().valid

    records = log.all_records()
    records[2]["verdict"] = "REFUSE"          # was ALLOW
    records[2]["explanation"] = "rewritten after the fact"

    result = verify_chain(records)
    assert not result.valid
    assert result.broken_at == 2
    assert "edited" in result.reason


def test_removing_a_record_breaks_the_chain(log: EvidenceLog, mandate) -> None:
    _append(log, mandate, n=5)
    records = log.all_records()
    del records[2]
    result = verify_chain(records)
    assert not result.valid
    assert result.broken_at == 2


def test_reordering_records_breaks_the_chain(log: EvidenceLog, mandate) -> None:
    _append(log, mandate, n=5)
    records = log.all_records()
    records[1], records[3] = records[3], records[1]
    assert not verify_chain(records).valid


def test_truncating_the_head_is_detected(log: EvidenceLog, mandate) -> None:
    """Dropping the earliest records would otherwise leave a self-consistent
    chain that simply starts later."""
    _append(log, mandate, n=5)
    records = log.all_records()[2:]
    result = verify_chain(records)
    assert not result.valid
    assert result.broken_at == 0
    assert "genesis" in result.reason


def test_a_forged_record_hash_is_detected(log: EvidenceLog, mandate) -> None:
    """Editing content and recomputing that record's own hash is not enough —
    the following record still carries the old prev_hash."""
    _append(log, mandate, n=4)
    records = log.all_records()
    records[1]["verdict"] = "REFUSE"
    records[1]["record_hash"] = compute_record_hash(records[1], records[1]["prev_hash"])
    result = verify_chain(records)
    assert not result.valid
    assert result.broken_at == 2


# ---------------------------------------------------------------------------
# append-only enforcement
# ---------------------------------------------------------------------------


def test_the_database_rejects_updates(log: EvidenceLog, mandate) -> None:
    _append(log, mandate, n=1)
    with sqlite3.connect(log.path) as conn:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("UPDATE decisions SET verdict='REFUSE'")


def test_the_database_rejects_deletes(log: EvidenceLog, mandate) -> None:
    _append(log, mandate, n=1)
    with sqlite3.connect(log.path) as conn:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("DELETE FROM decisions")


# ---------------------------------------------------------------------------
# dispute evidence
# ---------------------------------------------------------------------------


def test_a_decision_binds_to_its_mandate_and_cart(log: EvidenceLog, mandate) -> None:
    """02 §6: the record must prove *which* cart was checked against *which*
    mandate, or it proves nothing in a dispute."""
    decision = _append(log, mandate, n=1)[0]
    assert decision.mandate_hash == hash_payload(mandate.model_dump(mode="json"))
    assert len(decision.cart_hash) == 64


def test_the_audit_trail_for_one_mandate_is_retrievable(log: EvidenceLog, mandate) -> None:
    _append(log, mandate, n=3)
    other = mandate.model_copy(deep=True)
    other.mandate_id = "mnd_other"
    _append(log, other, n=2)

    assert len(log.for_mandate(mandate.mandate_id)) == 3
    assert len(log.for_mandate("mnd_other")) == 2
    assert log.verify().valid


def test_human_resolution_is_recorded_beside_the_decision_not_inside_it(
    log: EvidenceLog, mandate
) -> None:
    """Editing the decision to carry the outcome would destroy both records:
    what the system concluded, and what the person decided afterwards."""
    decision = _append(log, mandate, verdict="ESCALATE", n=1)[0]
    log.record_resolution(decision.decision_id, "reviewer@merchant", "approved", "fine")

    resolved = log.resolution(decision.decision_id)
    assert resolved["outcome"] == "approved"
    assert log.verify().valid, "recording a resolution must not disturb the chain"


def test_checks_survive_the_round_trip(log: EvidenceLog, mandate) -> None:
    """The per-check breakdown is the evidence. If it does not round-trip, the
    log records a verdict without its reasons."""
    decision = _append(log, mandate, n=1)[0]
    stored = log.all_records()[0]
    assert stored["checks"][0]["check"] == "amount_ceiling"
    assert stored["checks"][0]["decided_by"] == "rule"
    assert stored["explanation"] == decision.explanation
