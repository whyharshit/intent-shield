"""Warrant review UI — escalation queue and decision inspector.

Styled with the Razorpay design tokens in design_of_ui/01-design-tokens.md: one
saturated accent (#305EFF) used decisively, ink navy for text, ice-blue bands
instead of borders, Inter for body. The point is that a reviewer looking at this
sees something that belongs beside Razorpay's own surfaces.

Three things it has to do (02 §8, 05 §Day-19):

1. **The escalation queue** — every cart the system declined to decide, with
   enough context for a human to resolve it in a few seconds.
2. **The decision inspector** — every check, what it found, and *which layer
   decided it*. That last column is the argument: rules and comparisons decide,
   the model judges attributes.
3. **Baseline vs Warrant, side by side** — the whisky case, which the reference
   AP2 check approves and this refuses.

    streamlit run ui/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.generator.make_dataset import load_split
from eval.baseline import validate_mandate_pair
from warrant.checks.deterministic import PriorApproval
from warrant.evidence.log import EvidenceLog
from warrant.rails.india import route
from warrant.verify import Verifier

INK, ACCENT, ICE, DARK = "#192839", "#305EFF", "#EDF4F7", "#0B1F2A"
MUTED, LINE = "#40566D", "#D7E3EA"

VERDICT_STYLE = {
    "ALLOW":    ("#0F7A52", "#E6F6EF"),
    "REFUSE":   ("#B3261E", "#FDECEA"),
    "ESCALATE": ("#8A5A00", "#FFF4E0"),
}
RESULT_MARK = {"pass": "✓", "fail": "✕", "uncertain": "?", "skipped": "–"}

st.set_page_config(page_title="Warrant — intent conformance",
                   page_icon="🛡️", layout="wide")

st.markdown(f"""<style>
  html, body, [class*="css"] {{ font-family: Inter, system-ui, sans-serif; }}
  .stApp {{ background: #FFFFFF; color: {INK}; }}
  h1, h2, h3 {{ color: {INK}; letter-spacing: -0.02em; }}
  .wr-hero {{ background:{ICE}; border-radius:12px; padding:22px 26px; margin-bottom:18px; }}
  .wr-eyebrow {{ color:{MUTED}; font-size:12px; letter-spacing:.10em;
                 text-transform:uppercase; font-weight:600; }}
  .wr-verdict {{ display:inline-block; padding:5px 14px; border-radius:999px;
                 font-weight:700; font-size:13px; letter-spacing:.03em; }}
  .wr-card {{ background:#FFF; border:1px solid {LINE}; border-radius:12px;
              padding:16px 18px; margin-bottom:10px; }}
  .wr-band {{ background:{ICE}; border-radius:12px; padding:16px 18px; }}
  .wr-dark {{ background:{DARK}; color:#FFF; border-radius:12px; padding:18px 22px; }}
  .wr-kpi {{ font-size:30px; font-weight:700; color:{INK}; line-height:1.1; }}
  .wr-kpi-l {{ font-size:12px; color:{MUTED}; text-transform:uppercase;
               letter-spacing:.08em; }}
  .wr-mono {{ font-family:ui-monospace,Menlo,Consolas,monospace; font-size:12.5px; }}
  .wr-rule {{ color:{ACCENT}; font-weight:600; }}
</style>""", unsafe_allow_html=True)


def badge(verdict: str) -> str:
    fg, bg = VERDICT_STYLE[verdict]
    return (f'<span class="wr-verdict" style="color:{fg};background:{bg}">'
            f'{verdict}</span>')


@st.cache_resource(show_spinner="Loading verifier…")
def get_verifier() -> Verifier:
    return Verifier()


@st.cache_data(show_spinner="Loading pairs…")
def get_pairs(split: str):
    return load_split(split)


def rupees(paise: int) -> str:
    return f"₹{paise / 100:,.0f}"


def render_checks(result) -> None:
    st.markdown("**Checks** — the `decided by` column is the argument")
    rows = []
    for c in result.checks:
        if c.result == "skipped":
            continue
        layer = ("rule" if c.decided_by == "rule" else "model")
        rows.append({
            "": RESULT_MARK[c.result],
            "check": c.check,
            "result": c.result,
            "decided by": layer,
            "detail": c.detail[:120],
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)
    by_rule = sum(1 for c in result.checks if c.decided_by == "rule"
                  and c.result != "skipped")
    by_model = sum(1 for c in result.checks if c.decided_by == "model")
    st.caption(f"{by_rule} settled by comparison · {by_model} judged by a model"
               + ("  ·  the model was never consulted" if not by_model else ""))


def render_cart(pair) -> None:
    st.dataframe(
        [{"line": li.line_id, "item": li.title[:60], "qty": li.quantity,
          "amount": rupees(li.total_amount_paise)} for li in pair.cart.line_items],
        use_container_width=True, hide_index=True,
    )


# --------------------------------------------------------------------------
st.markdown(
    f'<div class="wr-hero"><div class="wr-eyebrow">Razorpay AI Buildathon · '
    f'Track 02</div>'
    f'<h1 style="margin:.15em 0 .1em">Warrant</h1>'
    f'<div style="font-size:17px;color:{MUTED};max-width:60ch">'
    f'Cryptography proves the mandate wasn\'t altered. It does not prove the '
    f'cart honours the intent. <span style="color:{ACCENT};font-weight:600">'
    f'This is the missing check.</span></div></div>',
    unsafe_allow_html=True,
)

tab_demo, tab_queue, tab_audit = st.tabs(
    ["The 30 seconds", "Escalation queue", "Audit trail"]
)

# --------------------------------------------------------------------------
with tab_demo:
    st.subheader("₹1,830 of whisky against “groceries, under ₹2,000, no alcohol”")
    st.caption("Real products at real Karnataka excise prices. "
               "Amount passes. Merchant passes. Signature verifies.")

    pairs = get_pairs("train")
    candidates = [p for p in pairs if p.violation_types == ["CATEGORY_DENIED"]]
    pair = candidates[0] if candidates else pairs[0]

    st.markdown(f"**Intent** — _{pair.mandate.raw_intent_text}_")
    render_cart(pair)

    base = validate_mandate_pair(pair.mandate, pair.cart)
    verifier = get_verifier()
    result = verifier.verify(
        pair.mandate, pair.cart, pair.checked_at,
        [PriorApproval(a.approved_at, a.amount_paise) for a in pair.prior_approvals],
    )

    left, right = st.columns(2)
    with left:
        st.markdown('<div class="wr-card">', unsafe_allow_html=True)
        st.markdown("##### Baseline — the AP2 reference check")
        st.markdown(badge(base.verdict), unsafe_allow_html=True)
        st.markdown(
            f"<div class='wr-mono' style='margin-top:10px'>"
            f"total_within_intent = <b>{base.total_within_intent}</b><br>"
            f"merchant_allowed &nbsp;&nbsp;= <b>{base.merchant_allowed}</b></div>"
            f"<div style='color:{MUTED};margin-top:10px;font-size:13px'>"
            f"Two booleans. That is the whole check.</div>",
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)
    with right:
        st.markdown('<div class="wr-card">', unsafe_allow_html=True)
        st.markdown("##### Warrant")
        st.markdown(badge(result.verdict), unsafe_allow_html=True)
        st.markdown(
            f"<div style='margin-top:10px;font-size:13.5px'>{result.explanation}"
            f"</div><div style='color:{MUTED};margin-top:8px;font-size:12.5px'>"
            f"p(violation) {result.calibrated_p_violation:.2f} · "
            f"{result.latency_ms} ms · settled by {result.path}</div>",
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    render_checks(result)

    rails = route(result.verdict, pair.mandate, pair.cart, result.explanation)
    st.markdown(
        f'<div class="wr-dark"><div class="wr-eyebrow" '
        f'style="color:#9FB6C4">On Indian rails</div>'
        f'<div style="font-size:16px;margin-top:6px"><b>{rails.step_up}</b> '
        f'via <span class="wr-mono">{rails.channel}</span></div>'
        f'<div style="opacity:.85;font-size:13px;margin-top:6px">'
        f'{rails.reason[:180]}</div></div>',
        unsafe_allow_html=True,
    )

# --------------------------------------------------------------------------
with tab_queue:
    st.subheader("Escalations — the cases it refused to guess on")
    st.caption("Escalation is the product, not a failure mode. "
               "A vague intent producing more human check-ins is correct.")

    split = st.selectbox("Split", ["validation", "train"], index=0)
    limit = st.slider("Pairs to verify", 20, 300, 60, step=20)
    queue_pairs = get_pairs(split)[:limit]
    verifier = get_verifier()

    results = [
        verifier.verify(
            p.mandate, p.cart, p.checked_at,
            [PriorApproval(a.approved_at, a.amount_paise) for a in p.prior_approvals],
        )
        for p in queue_pairs
    ]
    escalations = [(p, r) for p, r in zip(queue_pairs, results)
                   if r.verdict == "ESCALATE"]

    c1, c2, c3 = st.columns(3)
    for col, value, label in (
        (c1, len(queue_pairs), "verified"),
        (c2, len(escalations), "escalated"),
        (c3, f"{len(escalations)/max(len(queue_pairs),1):.0%}", "escalation rate"),
    ):
        col.markdown(f'<div class="wr-band"><div class="wr-kpi">{value}</div>'
                     f'<div class="wr-kpi-l">{label}</div></div>',
                     unsafe_allow_html=True)

    st.markdown("")
    if not escalations:
        st.info("No escalations in this slice.")
    for pair, result in escalations[:40]:
        with st.expander(
            f"{pair.pair_id} · {rupees(pair.cart.total_paise)} · "
            f"{result.explanation[:80]}"
        ):
            st.markdown(f"**Intent** — _{pair.mandate.raw_intent_text}_")
            render_cart(pair)
            render_checks(result)
            a, b, _ = st.columns([1, 1, 3])
            if a.button("Approve", key=f"ok_{pair.pair_id}"):
                st.success("Recorded. Written beside the decision, never into it.")
            if b.button("Reject", key=f"no_{pair.pair_id}"):
                st.success("Recorded.")

# --------------------------------------------------------------------------
with tab_audit:
    st.subheader("Tamper-evident decision log")
    st.caption("In a dispute the merchant produces not just “the signature was "
               "valid” but the check that ran before the money moved.")
    try:
        log = EvidenceLog()
        chain = log.verify()
        st.markdown(
            f'<div class="wr-band"><div class="wr-kpi">'
            f'{"valid" if chain.valid else "BROKEN"}</div>'
            f'<div class="wr-kpi-l">chain over {chain.length} record(s)</div></div>',
            unsafe_allow_html=True,
        )
        if not chain.valid:
            st.error(f"Broken at record {chain.broken_at}: {chain.reason}")
        records = log.all_records()[-25:]
        if records:
            st.dataframe(
                [{"decision": r["decision_id"][:16], "mandate": r["mandate_id"],
                  "verdict": r["verdict"], "p": f"{r['calibrated_p_violation']:.2f}",
                  "explanation": r["explanation"][:80]} for r in records],
                use_container_width=True, hide_index=True,
            )
        else:
            st.info("No decisions logged yet.")
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Evidence log unavailable: {exc}")
