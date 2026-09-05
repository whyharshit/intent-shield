"""Taxonomy tests.

Leaf ids are part of the signed meaning of a mandate, so the structural
guarantees here (uniqueness, root/leaf disjointness) are correctness
properties, not tidiness.
"""

from __future__ import annotations

import pytest

from warrant.taxonomy import UNKNOWN, Taxonomy, default_taxonomy, load_taxonomy


@pytest.fixture(scope="module")
def tax() -> Taxonomy:
    return default_taxonomy()


def test_shape_matches_the_spec(tax: Taxonomy) -> None:
    # 03 §3.2 asks for ~12 roots and ~60 leaves covering Indian retail
    assert 12 <= len(tax.roots) <= 14
    assert 60 <= len(tax.leaves) <= 90


def test_every_root_named_in_the_brief_is_present(tax: Taxonomy) -> None:
    required = {
        "grocery", "produce", "staples", "personal_care", "household",
        "alcohol", "tobacco", "apparel", "footwear", "electronics",
        "pharma", "restaurant",
    }
    assert required <= set(tax.root_ids)


def test_leaf_ids_are_globally_unique(tax: Taxonomy) -> None:
    assert len(tax.leaf_ids) == len(set(tax.leaf_ids))


def test_roots_and_leaves_do_not_share_ids(tax: Taxonomy) -> None:
    assert not set(tax.root_ids) & set(tax.leaf_ids)


def test_every_leaf_has_a_description_and_keywords(tax: Taxonomy) -> None:
    """C4 stage 1 seeds embedding centroids from `description` and its regex
    fast path from `keywords`. A leaf missing either is a silent hole in the
    category mapper."""
    for leaf in tax.leaves.values():
        assert leaf.description.strip(), leaf.id
        assert leaf.keywords, leaf.id


def test_alcohol_and_tobacco_are_restricted(tax: Taxonomy) -> None:
    assert tax.is_restricted("alcohol")
    assert tax.is_restricted("whisky")
    assert tax.is_restricted("cigarettes")
    assert not tax.is_restricted("fresh_vegetables")


def test_restriction_is_inherited_from_the_root(tax: Taxonomy) -> None:
    assert tax.leaves["whisky"].root == "alcohol"
    assert tax.is_restricted("beer")


def test_expand_turns_a_root_into_all_its_leaves(tax: Taxonomy) -> None:
    """`categories_denied: [alcohol]` must deny every leaf beneath it."""
    leaves = tax.expand(["alcohol"])
    assert "whisky" in leaves and "beer" in leaves and "wine" in leaves
    assert "fresh_fruits" not in leaves


def test_expand_accepts_roots_and_leaves_together(tax: Taxonomy) -> None:
    out = tax.expand(["alcohol", "fresh_fruits"])
    assert "fresh_fruits" in out
    assert "whisky" in out


def test_expand_rejects_an_unknown_id(tax: Taxonomy) -> None:
    """Fail closed: an unrecognised category must not silently expand to nothing."""
    with pytest.raises(KeyError):
        tax.expand(["groceries"])  # plausible typo for "grocery"


def test_unknown_sentinel_is_not_a_category(tax: Taxonomy) -> None:
    assert UNKNOWN not in tax


def test_services_root_exists_for_add_on_creep(tax: Taxonomy) -> None:
    """V11 ADD_ON_CREEP is a set-membership test, not a language judgement."""
    assert "services" in tax.root_ids
    assert {"shipping_delivery", "warranty_protection", "insurance"} <= set(
        tax.roots["services"].leaf_ids
    )


def test_duplicate_leaf_across_roots_is_rejected(tmp_path) -> None:
    bad = tmp_path / "dup.yaml"
    bad.write_text(
        """
version: 1
roots:
  a:
    label: A
    description: d
    leaves:
      shared: {label: S, description: d, keywords: [x]}
  b:
    label: B
    description: d
    leaves:
      shared: {label: S, description: d, keywords: [x]}
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate leaf id"):
        load_taxonomy(bad)
