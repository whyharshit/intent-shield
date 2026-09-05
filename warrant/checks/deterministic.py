"""C3 — the deterministic checker.

Everything here is arithmetic or set membership. No model is consulted, no
network call is made, and every verdict carries the exact comparison that
produced it. This layer should settle the large majority of decisions; if it
does not, the LLM is doing work a join could do and kill criterion K3 fires.

**P-001, resolved.** 03 §1 draws C3 before C4, but "no line item maps to a
denied category" needs the category mapping to exist. Mapping runs first, as a
cheap enrichment step — embeddings and regex, single-digit milliseconds, no
model — and C3 then does pure set membership over its output. The ordering in
the design diagram was an oversight, not a decision; the rule "deterministic
first, model last" is about the *language model*, and the category mapper is
not one.

**Fail closed.** An unmappable line item yields `uncertain`, never `pass`. An
unrecognised category id in a mandate yields `uncertain`, never a silently
empty deny-set. Both route to escalation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from warrant.checks.categories import MappedCategory
from warrant.models import Cart, CheckResult, IntentMandate
from warrant.taxonomy import UNKNOWN, Taxonomy, default_taxonomy

FREQUENCY_WINDOW_DAYS = {"once": 3650, "daily": 1, "weekly": 7, "monthly": 30}

# An unmappable line matters only if enough money rides on it.
#
# Per-line uncertainty compounds across a cart: at ~10% unmappable per line and
# 4.2 lines per cart, most carts contain at least one, which drove the
# escalation rate to 44%. But a Rs 30 bunch of dill leaves that the mapper
# cannot place is not a reason to interrupt a human over a Rs 2,000 grocery
# order, and 02 §5 already argues that what is at stake should scale the
# response. A line is material if it is a meaningful share of the cart, or
# large in absolute terms on a small cart.
#
# This applies ONLY to lines that could not be categorised. A line that *was*
# categorised into a denied category fails regardless of how cheap it is —
# otherwise a small bottle of whisky would slip through. See DECISIONS.md D-032.
#
# The floor is derived, not picked. An escalation costs about Rs 12 of customer
# friction (eval/metrics.py). An unmappable line hides a real violation roughly
# 8% of the time on train. Asking is worth it when
#     line_value x P(violation | unmappable) > friction
#     line_value > 12 / 0.08 = Rs 150
# This is a stand-in for C5: once the expected-cost policy exists it should
# subsume this rule, weighing the amount at risk directly instead of through a
# fixed threshold.
MATERIAL_SHARE = 0.08
MATERIAL_FLOOR_PAISE = 15_000  # Rs 150


def _material(lines, cart: Cart) -> list:
    """The subset of `lines` worth escalating over."""
    if not lines:
        return []
    total = max(cart.total_paise, 1)
    combined = sum(ln.total_amount_paise for ln in lines)
    if combined / total >= MATERIAL_SHARE:
        return list(lines)
    return [ln for ln in lines if ln.total_amount_paise >= MATERIAL_FLOOR_PAISE]


@dataclass
class PriorApproval:
    approved_at: datetime
    amount_paise: int


@dataclass
class DeterministicOutcome:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def failed(self) -> list[CheckResult]:
        return [c for c in self.checks if c.result == "fail"]

    @property
    def uncertain(self) -> list[CheckResult]:
        return [c for c in self.checks if c.result == "uncertain"]

    @property
    def resolved(self) -> bool:
        """True when this layer alone settles the decision.

        A failure is decisive: one breached hard constraint is enough to refuse,
        and nothing a model could say would change it. Uncertainty is not
        decisive — it needs escalation or a semantic opinion.
        """
        return bool(self.failed)


def _ok(check: str, detail: str, refs: list[str] | None = None) -> CheckResult:
    return CheckResult(check=check, result="pass", decided_by="rule",
                       detail=detail, line_refs=refs or [])


def _fail(check: str, detail: str, refs: list[str] | None = None) -> CheckResult:
    return CheckResult(check=check, result="fail", decided_by="rule",
                       detail=detail, line_refs=refs or [])


def _unsure(check: str, detail: str, refs: list[str] | None = None) -> CheckResult:
    return CheckResult(check=check, result="uncertain", decided_by="rule",
                       detail=detail, line_refs=refs or [])


def _skip(check: str, detail: str) -> CheckResult:
    return CheckResult(check=check, result="skipped", decided_by="rule", detail=detail)


def _rupees(paise: int) -> str:
    return f"Rs {paise / 100:,.0f}"


class DeterministicChecker:
    def __init__(self, taxonomy: Taxonomy | None = None):
        self.tax = taxonomy or default_taxonomy()

    # -- individual checks -------------------------------------------------

    def amount_ceiling(self, mandate: IntentMandate, cart: Cart) -> CheckResult:
        cap = mandate.hard.amount_max_paise
        total = cart.total_paise
        if total > cap:
            return _fail(
                "amount_ceiling",
                f"cart total {_rupees(total)} exceeds cap {_rupees(cap)} "
                f"by {_rupees(total - cap)}",
            )
        return _ok(
            "amount_ceiling",
            f"cart total {_rupees(total)} is within cap {_rupees(cap)}",
        )

    def mandate_validity(self, mandate: IntentMandate, now: datetime) -> CheckResult:
        if now >= mandate.hard.expires_at:
            late = now - mandate.hard.expires_at
            return _fail(
                "mandate_validity",
                f"mandate expired {mandate.hard.expires_at:%d %b %Y}, "
                f"{late.days} day(s) before this cart",
            )
        return _ok(
            "mandate_validity",
            f"mandate valid until {mandate.hard.expires_at:%d %b %Y}",
        )

    def merchant_scope(self, mandate: IntentMandate, cart: Cart) -> CheckResult:
        allowed = mandate.hard.merchants_allowed
        if not allowed:
            # P-003: an empty allow-list is no restriction, not deny-all.
            return _skip("merchant_scope", "mandate names no merchant restriction")
        if cart.merchant_id not in allowed:
            return _fail(
                "merchant_scope",
                f"cart placed at {cart.merchant_id}; mandate allows {allowed}",
            )
        return _ok("merchant_scope", f"{cart.merchant_id} is in the allow-list")

    def frequency(
        self,
        mandate: IntentMandate,
        now: datetime,
        priors: list[PriorApproval],
    ) -> CheckResult:
        freq = mandate.hard.frequency
        if not freq:
            return _skip("frequency", "mandate states no frequency")
        window = timedelta(days=FREQUENCY_WINDOW_DAYS[freq])
        recent = [p for p in priors if now - p.approved_at < window]
        limit = 1 if freq != "once" else 1
        if len(recent) + 1 > limit:
            return _fail(
                "frequency",
                f"{len(recent) + 1} orders inside a {freq} window; "
                f"mandate permits {limit}",
            )
        return _ok(
            "frequency",
            f"{len(recent)} prior order(s) in the current {freq} window",
        )

    def usage_count(self, mandate: IntentMandate, priors: list[PriorApproval]) -> CheckResult:
        cap = mandate.hard.max_uses
        if cap is None:
            return _skip("usage_count", "mandate states no usage cap")
        if len(priors) + 1 > cap:
            return _fail(
                "usage_count",
                f"this would be use {len(priors) + 1} of a {cap}-use mandate",
            )
        return _ok("usage_count", f"use {len(priors) + 1} of {cap}")

    def cumulative_spend(
        self, mandate: IntentMandate, cart: Cart, priors: list[PriorApproval]
    ) -> CheckResult:
        cap = mandate.hard.cumulative_cap_paise
        if cap is None:
            return _skip("cumulative_spend", "mandate states no lifetime cap")
        spent = sum(p.amount_paise for p in priors)
        projected = spent + cart.total_paise
        if projected > cap:
            return _fail(
                "cumulative_spend",
                f"lifetime spend would reach {_rupees(projected)} "
                f"against a cap of {_rupees(cap)}",
            )
        return _ok(
            "cumulative_spend",
            f"lifetime spend {_rupees(projected)} of {_rupees(cap)}",
        )

    def delivery_window(self, mandate: IntentMandate, cart: Cart) -> CheckResult:
        by = mandate.hard.deliver_by
        if by is None:
            return _skip("delivery_window", "mandate states no delivery deadline")
        if cart.promised_delivery is None:
            return _unsure(
                "delivery_window",
                f"mandate requires delivery by {by:%d %b}, but the cart "
                f"promises no date",
            )
        if cart.promised_delivery > by:
            return _fail(
                "delivery_window",
                f"promised {cart.promised_delivery:%d %b}, "
                f"deadline {by:%d %b}",
            )
        return _ok(
            "delivery_window",
            f"promised {cart.promised_delivery:%d %b}, within the "
            f"{by:%d %b} deadline",
        )

    def denied_category(
        self, mandate: IntentMandate, cart: Cart, mapped: dict[str, MappedCategory]
    ) -> CheckResult:
        """The whisky check."""
        denied_ids = mandate.hard.categories_denied
        if not denied_ids:
            return _skip("denied_category", "mandate denies no category")
        unknown_ids = self.tax.unknown_ids(denied_ids)
        if unknown_ids:
            return _unsure(
                "denied_category",
                f"mandate names unknown categories {unknown_ids}; "
                f"cannot evaluate the deny-list",
            )
        denied = self.tax.expand(denied_ids)

        hits, unmapped = [], []
        for line in cart.line_items:
            got = mapped.get(line.line_id)
            if got is None or not got.is_known:
                unmapped.append(line)
            elif got.leaf_id in denied:
                hits.append((line, got))

        if hits:
            line, got = hits[0]
            names = ", ".join(f"{ln.title} -> {g.leaf_id}" for ln, g in hits[:3])
            return _fail(
                "denied_category",
                f"{len(hits)} line(s) in a denied category: {names}",
                [ln.line_id for ln, _ in hits],
            )
        material = _material(unmapped, cart)
        if material:
            return _unsure(
                "denied_category",
                f"{len(material)} material line(s) could not be categorised, so "
                f"the deny-list cannot be cleared: "
                f"{', '.join(ln.title[:40] for ln in material[:3])}",
                [ln.line_id for ln in material],
            )
        if unmapped:
            return _ok(
                "denied_category",
                f"no line item falls in {sorted(denied_ids)}; "
                f"{len(unmapped)} immaterial line(s) uncategorised",
                [ln.line_id for ln in unmapped],
            )
        return _ok(
            "denied_category",
            f"no line item falls in {sorted(denied_ids)}",
        )

    def allowed_scope(
        self, mandate: IntentMandate, cart: Cart, mapped: dict[str, MappedCategory]
    ) -> CheckResult:
        allowed_ids = mandate.hard.categories_allowed
        if not allowed_ids:
            return _skip("allowed_scope", "mandate restricts no category")
        unknown_ids = self.tax.unknown_ids(allowed_ids)
        if unknown_ids:
            return _unsure(
                "allowed_scope",
                f"mandate names unknown categories {unknown_ids}",
            )
        allowed = self.tax.expand(allowed_ids)

        outside, restricted, unmapped = [], [], []
        for line in cart.line_items:
            got = mapped.get(line.line_id)
            if got is None or not got.is_known:
                unmapped.append(line)
            elif got.leaf_id not in allowed:
                if self.tax.is_restricted(got.leaf_id):
                    restricted.append((line, got))
                else:
                    outside.append((line, got))

        # An age-gated item on a mandate that never allowed one is decisive.
        # Alcohol on a grocery mandate is a refusal whether or not the customer
        # thought to write "no alcohol", which is exactly the whisky case when
        # the mandate has no explicit deny-list.
        if restricted:
            names = ", ".join(f"{ln.title} -> {g.leaf_id}" for ln, g in restricted[:3])
            return _fail(
                "allowed_scope",
                f"{len(restricted)} restricted line(s) outside the allowed "
                f"scope {sorted(allowed_ids)}: {names}",
                [ln.line_id for ln, _ in restricted],
            )

        # Everything else out of scope is `uncertain`, not `fail`.
        #
        # "Not in the allowed list" is a weaker signal than "explicitly
        # denied", and it rests entirely on a probabilistic mapping. Failing
        # hard on it refused 494 conforming carts on train — "Pineapple Juice"
        # mapped to beverages_soft instead of beverages_restaurant, "Mini
        # Samosa" to starters_snacks instead of snacks_namkeen. Those are the
        # same product under a different leaf, and a customer who wrote
        # "groceries" would call every one of them in scope. Escalating asks a
        # human; refusing loses the sale on a taxonomy artefact. See
        # DECISIONS.md D-031.
        outside_material = _material([ln for ln, _ in outside], cart)
        if outside_material:
            ids = {ln.line_id for ln in outside_material}
            names = ", ".join(
                f"{ln.title} -> {g.leaf_id}" for ln, g in outside if ln.line_id in ids
            )
            return _unsure(
                "allowed_scope",
                f"{len(outside_material)} line(s) appear outside the allowed "
                f"scope {sorted(allowed_ids)}: {names[:160]}",
                sorted(ids),
            )
        material = _material(unmapped, cart)
        if material:
            return _unsure(
                "allowed_scope",
                f"{len(material)} material line(s) could not be categorised",
                [ln.line_id for ln in material],
            )
        if unmapped:
            return _ok(
                "allowed_scope",
                f"all categorised lines fall within {sorted(allowed_ids)}; "
                f"{len(unmapped)} immaterial line(s) uncategorised",
                [ln.line_id for ln in unmapped],
            )
        return _ok("allowed_scope", f"all lines fall within {sorted(allowed_ids)}")

    def unrequested_add_ons(
        self, mandate: IntentMandate, cart: Cart, mapped: dict[str, MappedCategory]
    ) -> CheckResult:
        """V11 ADD_ON_CREEP, as set membership rather than a language judgement.

        04 §2 marks this as needing an LLM. It does not: express shipping, an
        extended warranty and shipment insurance are line items with a type, and
        `services` exists in the taxonomy so that type is checkable (D-012). A
        service line is in scope only when the mandate allowed it explicitly.
        """
        services = set(self.tax.roots["services"].leaf_ids)
        explicitly_allowed = (
            self.tax.expand(mandate.hard.categories_allowed)
            if mandate.hard.categories_allowed
            else set()
        )
        sneaked = []
        for line in cart.line_items:
            got = mapped.get(line.line_id)
            leaf = got.leaf_id if got and got.is_known else (line.merchant_category or "")
            if leaf in services and leaf not in explicitly_allowed:
                sneaked.append((line, leaf))
        if sneaked:
            names = ", ".join(ln.title for ln, _ in sneaked[:3])
            return _fail(
                "unrequested_add_ons",
                f"{len(sneaked)} unrequested add-on(s): {names}",
                [ln.line_id for ln, _ in sneaked],
            )
        return _ok("unrequested_add_ons", "no unrequested service or fee lines")

    def empty_cart(self, cart: Cart) -> CheckResult:
        """A degenerate input that must escalate rather than crash or allow."""
        if not cart.line_items:
            return _unsure("empty_cart", "cart has no line items")
        return _ok("empty_cart", f"{len(cart.line_items)} line item(s)")

    # -- composition -------------------------------------------------------

    def run(
        self,
        mandate: IntentMandate,
        cart: Cart,
        now: datetime,
        mapped: dict[str, MappedCategory],
        priors: list[PriorApproval] | None = None,
    ) -> DeterministicOutcome:
        priors = priors or []
        return DeterministicOutcome(checks=[
            self.empty_cart(cart),
            self.mandate_validity(mandate, now),
            self.amount_ceiling(mandate, cart),
            self.merchant_scope(mandate, cart),
            self.frequency(mandate, now, priors),
            self.usage_count(mandate, priors),
            self.cumulative_spend(mandate, cart, priors),
            self.delivery_window(mandate, cart),
            self.denied_category(mandate, cart, mapped),
            self.allowed_scope(mandate, cart, mapped),
            self.unrequested_add_ons(mandate, cart, mapped),
        ])
