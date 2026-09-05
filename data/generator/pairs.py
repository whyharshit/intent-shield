"""Dataset artefacts: what a labelled (mandate, cart) pair looks like on disk.

These are generator-side records, not service models — they carry the ground
truth the evaluation grades against, which the service never sees.

`prior_approvals` closes a gap in 03 §2 (recorded as P-002 in DECISIONS.md):
the frequency and cumulative-spend checks in C3 need a history of what this
mandate has already authorised, and no model in the technical design carries
one. Without it V9 FREQUENCY_EXCEEDED is unverifiable.

`checked_at` is the verification time. It is a field rather than `now()`
because V8 MANDATE_EXPIRED is expressed by moving the clock past the mandate's
expiry, and because a dataset whose labels depend on when you run it is not a
dataset.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from warrant.models import Cart, IntentMandate, Verdict

ViolationType = Literal[
    "AMOUNT_EXCEEDED",           # V1  rule
    "CATEGORY_DENIED",           # V2  category map
    "CATEGORY_OUT_OF_SCOPE",     # V3  category map
    "ATTRIBUTE_MISMATCH",        # V4  model
    "BRAND_EXCLUSION",           # V5  model
    "QUANTITY_ANOMALY",          # V6  model + heuristic
    "MERCHANT_OUT_OF_SCOPE",     # V7  rule
    "MANDATE_EXPIRED",           # V8  rule
    "FREQUENCY_EXCEEDED",        # V9  rule
    "UNAUTHORIZED_SUBSTITUTION", # V10 model
    "ADD_ON_CREEP",              # V11 rule (see D-012)
    "TIMING_VIOLATION",          # V12 rule
]

ALL_VIOLATIONS: tuple[ViolationType, ...] = (
    "AMOUNT_EXCEEDED",
    "CATEGORY_DENIED",
    "CATEGORY_OUT_OF_SCOPE",
    "ATTRIBUTE_MISMATCH",
    "BRAND_EXCLUSION",
    "QUANTITY_ANOMALY",
    "MERCHANT_OUT_OF_SCOPE",
    "MANDATE_EXPIRED",
    "FREQUENCY_EXCEEDED",
    "UNAUTHORIZED_SUBSTITUTION",
    "ADD_ON_CREEP",
    "TIMING_VIOLATION",
)

# Which layer of the pipeline is *expected* to settle each type. Reported as a
# results column so the split between rules and model is visible — 04 §2's
# "deliberate design point", and the answer to "the LLM is doing the
# interesting work, so this is just prompting" (07 §R4).
RESOLVED_BY: dict[ViolationType, Literal["rule", "category", "model"]] = {
    "AMOUNT_EXCEEDED": "rule",
    "MERCHANT_OUT_OF_SCOPE": "rule",
    "MANDATE_EXPIRED": "rule",
    "FREQUENCY_EXCEEDED": "rule",
    "TIMING_VIOLATION": "rule",
    "ADD_ON_CREEP": "rule",
    "CATEGORY_DENIED": "category",
    "CATEGORY_OUT_OF_SCOPE": "category",
    "ATTRIBUTE_MISMATCH": "model",
    "BRAND_EXCLUSION": "model",
    "QUANTITY_ANOMALY": "model",
    "UNAUTHORIZED_SUBSTITUTION": "model",
}

Specificity = Literal["vague", "normal", "precise"]


class PriorApproval(BaseModel):
    """One earlier approval against the same mandate."""

    model_config = ConfigDict(extra="forbid")

    approved_at: datetime
    amount_paise: int = Field(ge=0)


class Pair(BaseModel):
    """A labelled (mandate, cart) pair — one row of the dataset."""

    model_config = ConfigDict(extra="forbid")

    pair_id: str = Field(min_length=1)
    mandate: IntentMandate
    cart: Cart
    checked_at: datetime

    label: Literal["conforming", "violating"]
    violation_types: list[ViolationType] = Field(default_factory=list)
    expected_verdict: Verdict

    prior_approvals: list[PriorApproval] = Field(default_factory=list)
    specificity: Specificity = "normal"
    template_id: str = ""
    notes: str = ""
    violation_detail: dict[str, str] = Field(default_factory=dict)
    """Machine-checkable specifics of the injected violation.

    `notes` is prose for the report; this is what a test can assert on. Added
    after a label-quality bug where a substitution stayed inside one category
    root and the free-text note was the only record of what had changed.
    """

    @model_validator(mode="after")
    def _label_matches_types(self) -> Pair:
        if self.label == "violating" and not self.violation_types:
            raise ValueError("a violating pair must name at least one violation type")
        if self.label == "conforming" and self.violation_types:
            raise ValueError("a conforming pair must not name violation types")
        if self.label == "conforming" and self.expected_verdict == "REFUSE":
            raise ValueError("a conforming pair must never expect REFUSE")
        return self

    @property
    def is_violating(self) -> bool:
        return self.label == "violating"


class Split(BaseModel):
    """One train/validation/test split, written as JSONL."""

    model_config = ConfigDict(extra="forbid")

    name: Literal["train", "validation", "test"]
    pairs: list[Pair]

    @property
    def mandate_ids(self) -> set[str]:
        return {p.mandate.mandate_id for p in self.pairs}
