"""Core data model for Warrant.

These are the schemas from 03-technical-design.md §2, with the validation the
design implies but does not spell out. Three rules govern everything here:

1. Money is an integer number of paise. Never a float. Rounding drift in a
   ceiling comparison is an approval that should have been a refusal.
2. Datetimes are timezone-aware. A naive `expires_at` compared against an
   aware `now` raises at runtime, and an expiry check that raises inside the
   payment path is a worse failure than one that refuses.
3. `extra="forbid"` everywhere. An unrecognised field in a mandate or a cart
   means the sender and this service disagree about what is being authorised.
   Fail closed at the boundary rather than silently dropping it.

Arithmetic consistency (line totals, cart totals) is enforced here rather than
in the checker. If a cart claims a total that its line items do not sum to, the
right response is to reject the document, not to decide which number to trust.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "HardConstraints",
    "SoftConstraints",
    "IntentMandate",
    "LineItem",
    "Cart",
    "CheckResult",
    "Decision",
    "Verdict",
    "CheckStatus",
    "DecidedBy",
]

Verdict = Literal["ALLOW", "REFUSE", "ESCALATE"]
CheckStatus = Literal["pass", "fail", "uncertain", "skipped"]
DecidedBy = Literal["rule", "model", "human"]

_HEX64 = r"^[0-9a-f]{64}$"


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


def _require_aware(v: datetime | None) -> datetime | None:
    """Reject naive datetimes; normalise everything to UTC."""
    if v is None:
        return None
    if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
        raise ValueError("datetime must be timezone-aware")
    return v.astimezone(timezone.utc)


# --------------------------------------------------------------------------
# Constraints
# --------------------------------------------------------------------------


class HardConstraints(_Base):
    """Constraints decidable by comparison or set membership.

    Everything in this class is settled by C3 without a model. If a field here
    ever needs an LLM to evaluate, it is in the wrong class.
    """

    amount_max_paise: int = Field(gt=0)
    currency: str = "INR"
    expires_at: datetime
    frequency: Literal["once", "daily", "weekly", "monthly"] | None = None
    max_uses: int | None = Field(default=None, gt=0)
    cumulative_cap_paise: int | None = Field(default=None, gt=0)
    categories_allowed: list[str] = Field(default_factory=list)
    categories_denied: list[str] = Field(default_factory=list)
    merchants_allowed: list[str] = Field(default_factory=list)
    deliver_by: datetime | None = None

    _aware = field_validator("expires_at", "deliver_by")(_require_aware)

    @field_validator("currency")
    @classmethod
    def _iso4217(cls, v: str) -> str:
        if not (len(v) == 3 and v.isalpha() and v.isupper()):
            raise ValueError("currency must be a 3-letter uppercase ISO 4217 code")
        return v

    @field_validator("categories_allowed", "categories_denied", "merchants_allowed")
    @classmethod
    def _clean_ids(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for item in v:
            s = item.strip()
            if not s:
                raise ValueError("identifier entries must not be blank")
            if s not in out:
                out.append(s)
        return out

    @model_validator(mode="after")
    def _coherent(self) -> HardConstraints:
        overlap = set(self.categories_allowed) & set(self.categories_denied)
        if overlap:
            raise ValueError(
                f"categories cannot be both allowed and denied: {sorted(overlap)}"
            )
        if (
            self.cumulative_cap_paise is not None
            and self.cumulative_cap_paise < self.amount_max_paise
        ):
            raise ValueError(
                "cumulative_cap_paise is below amount_max_paise; a single "
                "permitted transaction would breach the lifetime cap"
            )
        return self


class SoftConstraints(_Base):
    """Constraints requiring judgement. These are what C4 stage 2 reasons about.

    `ambiguous_terms` is load-bearing: extraction is instructed to put anything
    it could not pin down here rather than inventing a hard constraint. It
    propagates to lower confidence and a higher escalation rate downstream,
    which is the correct behaviour for a vague intent.
    """

    attribute_requirements: list[str] = Field(default_factory=list)
    brand_preferences: list[str] = Field(default_factory=list)
    brand_exclusions: list[str] = Field(default_factory=list)
    quality_terms: list[str] = Field(default_factory=list)
    ambiguous_terms: list[str] = Field(default_factory=list)

    @field_validator("*")
    @classmethod
    def _strip_blanks(cls, v: list[str]) -> list[str]:
        return [s.strip() for s in v if s and s.strip()]

    @property
    def is_empty(self) -> bool:
        """True when there is nothing for the semantic checker to do."""
        return not (
            self.attribute_requirements
            or self.brand_preferences
            or self.brand_exclusions
            or self.quality_terms
        )


# --------------------------------------------------------------------------
# Mandate
# --------------------------------------------------------------------------


class IntentMandate(_Base):
    """An AP2-shaped Intent Mandate after constraint extraction.

    `hard` and `soft` are the cached output of C2, signed alongside the mandate
    and never recomputed per transaction.
    """

    mandate_id: str = Field(min_length=1)
    subject_did: str = Field(min_length=1)
    raw_intent_text: str = Field(min_length=1)
    hard: HardConstraints
    soft: SoftConstraints = Field(default_factory=SoftConstraints)
    issued_at: datetime
    signature: str = Field(min_length=1)
    signature_alg: Literal["ES256"] = "ES256"

    _aware = field_validator("issued_at")(_require_aware)

    @field_validator("subject_did")
    @classmethod
    def _did_shape(cls, v: str) -> str:
        if not v.startswith("did:"):
            raise ValueError("subject_did must be a DID (did:<method>:<id>)")
        if len(v.split(":")) < 3:
            raise ValueError("subject_did must have a method and a method-specific id")
        return v

    @model_validator(mode="after")
    def _expiry_after_issue(self) -> IntentMandate:
        if self.hard.expires_at <= self.issued_at:
            raise ValueError("mandate expires at or before it was issued")
        if self.hard.deliver_by is not None and self.hard.deliver_by < self.issued_at:
            raise ValueError("deliver_by precedes issuance")
        return self

    def is_expired(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        return now >= self.hard.expires_at


# --------------------------------------------------------------------------
# Cart
# --------------------------------------------------------------------------


class LineItem(_Base):
    line_id: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict)
    quantity: int = Field(gt=0)
    unit_amount_paise: int = Field(ge=0)
    total_amount_paise: int = Field(ge=0)
    merchant_category: str | None = None

    @model_validator(mode="after")
    def _line_arithmetic(self) -> LineItem:
        expected = self.unit_amount_paise * self.quantity
        if self.total_amount_paise != expected:
            raise ValueError(
                f"line total {self.total_amount_paise} != "
                f"unit {self.unit_amount_paise} x qty {self.quantity} = {expected}"
            )
        return self


class Cart(_Base):
    """A proposed cart.

    An empty `line_items` list is deliberately permitted. A zero-item cart is a
    degenerate input the pipeline must handle and escalate on, not something the
    parser should reject — a crash at the boundary tells the caller nothing.
    """

    cart_id: str = Field(min_length=1)
    merchant_id: str = Field(min_length=1)
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal_paise: int = Field(ge=0)
    tax_paise: int = Field(ge=0, default=0)
    shipping_paise: int = Field(ge=0, default=0)
    total_paise: int = Field(ge=0)
    promised_delivery: datetime | None = None

    _aware = field_validator("promised_delivery")(_require_aware)

    @model_validator(mode="after")
    def _cart_arithmetic(self) -> Cart:
        line_sum = sum(li.total_amount_paise for li in self.line_items)
        if self.subtotal_paise != line_sum:
            raise ValueError(
                f"subtotal {self.subtotal_paise} != sum of line totals {line_sum}"
            )
        expected = self.subtotal_paise + self.tax_paise + self.shipping_paise
        if self.total_paise != expected:
            raise ValueError(
                f"total {self.total_paise} != subtotal + tax + shipping = {expected}"
            )
        return self

    @model_validator(mode="after")
    def _unique_line_ids(self) -> Cart:
        ids = [li.line_id for li in self.line_items]
        if len(ids) != len(set(ids)):
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"duplicate line_id(s): {dupes}")
        return self


# --------------------------------------------------------------------------
# Decision
# --------------------------------------------------------------------------


class CheckResult(_Base):
    check: str = Field(min_length=1)
    result: CheckStatus
    decided_by: DecidedBy
    detail: str = ""
    line_refs: list[str] = Field(default_factory=list)


class Decision(_Base):
    """An immutable decision record. One of these per verification.

    `prev_hash` chains records so the log is tamper-evident without a
    blockchain; `record_hash` covers this record plus the previous hash.
    Both are computed by the evidence layer, not here.
    """

    decision_id: str = Field(min_length=1)
    mandate_id: str = Field(min_length=1)
    mandate_hash: str = Field(pattern=_HEX64)
    cart_hash: str = Field(pattern=_HEX64)
    verdict: Verdict
    raw_confidence: float = Field(ge=0.0, le=1.0)
    calibrated_p_violation: float = Field(ge=0.0, le=1.0)
    checks: list[CheckResult] = Field(default_factory=list)
    explanation: str = ""
    expected_costs: dict[str, float] = Field(default_factory=dict)
    latency_ms: int = Field(ge=0)
    timestamp: datetime
    prev_hash: str = Field(pattern=_HEX64)
    record_hash: str = Field(pattern=_HEX64)

    _aware = field_validator("timestamp")(_require_aware)

    @model_validator(mode="after")
    def _verdict_supported(self) -> Decision:
        """A REFUSE must point at something that failed.

        Without this, a bug that drops the failing check still emits a
        plausible-looking refusal, and the audit record — the entire point of
        the log — no longer explains the verdict it carries.
        """
        if self.verdict == "REFUSE" and not any(
            c.result == "fail" for c in self.checks
        ):
            raise ValueError("REFUSE requires at least one failing check")
        return self
