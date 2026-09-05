from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from warrant.models import Cart, HardConstraints, IntentMandate, LineItem, SoftConstraints

NOW = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
HEX = "a" * 64


@pytest.fixture(scope="session", autouse=True)
def _release_embedding_model():
    """Drop the cached sentence-transformers model before interpreter shutdown.

    Without this the suite passes but the process segfaults on exit (exit 139)
    on Windows: torch's native threads are torn down while the module-level
    LRU cache still holds the model. A non-zero exit fails CI even though every
    test passed, so the cache is cleared while the interpreter is still healthy.
    """
    yield
    try:
        from warrant.checks.categories import default_mapper

        default_mapper.cache_clear()
    except Exception:
        pass
    import gc

    gc.collect()


@pytest.fixture
def hard() -> HardConstraints:
    return HardConstraints(
        amount_max_paise=200_000,  # Rs 2,000 — the mandate from the README
        expires_at=NOW + timedelta(days=30),
        frequency="weekly",
        categories_allowed=["grocery", "produce", "staples", "household"],
        categories_denied=["alcohol", "tobacco"],
    )


@pytest.fixture
def soft() -> SoftConstraints:
    return SoftConstraints(
        brand_preferences=["Indian brands"],
        ambiguous_terms=["for the week"],
    )


@pytest.fixture
def mandate(hard: HardConstraints, soft: SoftConstraints) -> IntentMandate:
    return IntentMandate(
        mandate_id="mnd_001",
        subject_did="did:example:alice",
        raw_intent_text=(
            "groceries for the week, under Rs 2,000, nothing alcoholic, "
            "prefer Indian brands"
        ),
        hard=hard,
        soft=soft,
        issued_at=NOW,
        signature="deadbeef",
    )


def line(
    line_id: str = "line_001",
    unit: int = 10_000,
    qty: int = 1,
    **kw,
) -> LineItem:
    return LineItem(
        line_id=line_id,
        sku=kw.pop("sku", "sku_1"),
        title=kw.pop("title", "Aashirvaad Shudh Chakki Atta"),
        quantity=qty,
        unit_amount_paise=unit,
        total_amount_paise=unit * qty,
        **kw,
    )


def cart(*items: LineItem, tax: int = 0, shipping: int = 0, **kw) -> Cart:
    subtotal = sum(li.total_amount_paise for li in items)
    return Cart(
        cart_id=kw.pop("cart_id", "cart_001"),
        merchant_id=kw.pop("merchant_id", "mrc_bigbasket"),
        line_items=list(items),
        subtotal_paise=subtotal,
        tax_paise=tax,
        shipping_paise=shipping,
        total_paise=subtotal + tax + shipping,
        **kw,
    )
