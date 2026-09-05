"""Loader and accessor for the category taxonomy.

The taxonomy is the constraint vocabulary. `categories_allowed` and
`categories_denied` on a mandate are sets of leaf ids from this file, so a leaf
id is part of the signed meaning of a mandate — see the note at the top of
data/taxonomy/categories.yaml.

Leaf ids must be unique across all roots. If two roots both defined a leaf
called `beverages`, a denied-category check would be ambiguous about which one
the customer meant, and the failure would be silent.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "taxonomy" / "categories.yaml"

UNKNOWN = "unknown"
"""Sentinel for an item the category mapper could not place.

Never a category in the taxonomy. It exists so C4 stage 1 can decline to guess;
an item that maps to UNKNOWN forces escalation rather than an allow.
"""


@dataclass(frozen=True)
class Leaf:
    id: str
    root: str
    label: str
    description: str
    keywords: tuple[str, ...]
    restricted: bool


@dataclass(frozen=True)
class Root:
    id: str
    label: str
    description: str
    restricted: bool
    leaf_ids: tuple[str, ...]


class Taxonomy:
    def __init__(self, roots: dict[str, Root], leaves: dict[str, Leaf]):
        self.roots = roots
        self.leaves = leaves

    # -- lookups ----------------------------------------------------------

    def __contains__(self, category_id: str) -> bool:
        return category_id in self.leaves or category_id in self.roots

    def leaf(self, leaf_id: str) -> Leaf:
        return self.leaves[leaf_id]

    def root_of(self, leaf_id: str) -> str:
        return self.leaves[leaf_id].root

    def is_restricted(self, category_id: str) -> bool:
        """True if the category, or the root it belongs to, is age-gated or regulated."""
        if category_id in self.leaves:
            leaf = self.leaves[category_id]
            return leaf.restricted or self.roots[leaf.root].restricted
        if category_id in self.roots:
            return self.roots[category_id].restricted
        return False

    def expand(self, category_ids: list[str]) -> set[str]:
        """Expand a mix of root and leaf ids into the set of leaf ids it covers.

        A mandate saying `categories_denied: [alcohol]` must deny every leaf
        under alcohol, not just an item that happened to map to the root.
        """
        out: set[str] = set()
        for cid in category_ids:
            if cid in self.roots:
                out.update(self.roots[cid].leaf_ids)
            elif cid in self.leaves:
                out.add(cid)
            else:
                raise KeyError(f"unknown category id: {cid!r}")
        return out

    def unknown_ids(self, category_ids: list[str]) -> list[str]:
        return [c for c in category_ids if c not in self]

    @property
    def leaf_ids(self) -> list[str]:
        return list(self.leaves)

    @property
    def root_ids(self) -> list[str]:
        return list(self.roots)

    def __repr__(self) -> str:
        return f"<Taxonomy roots={len(self.roots)} leaves={len(self.leaves)}>"


def load_taxonomy(path: Path | str | None = None) -> Taxonomy:
    path = Path(path) if path else DEFAULT_PATH
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    roots: dict[str, Root] = {}
    leaves: dict[str, Leaf] = {}

    for root_id, rspec in (raw.get("roots") or {}).items():
        root_restricted = bool(rspec.get("restricted", False))
        leaf_ids: list[str] = []
        for leaf_id, lspec in (rspec.get("leaves") or {}).items():
            if leaf_id in leaves:
                raise ValueError(
                    f"duplicate leaf id {leaf_id!r} in roots "
                    f"{leaves[leaf_id].root!r} and {root_id!r}"
                )
            if leaf_id in (root_id, UNKNOWN):
                raise ValueError(f"leaf id {leaf_id!r} collides with a reserved id")
            leaves[leaf_id] = Leaf(
                id=leaf_id,
                root=root_id,
                label=lspec["label"],
                description=lspec["description"],
                keywords=tuple(lspec.get("keywords") or ()),
                restricted=bool(lspec.get("restricted", root_restricted)),
            )
            leaf_ids.append(leaf_id)
        roots[root_id] = Root(
            id=root_id,
            label=rspec["label"],
            description=rspec["description"],
            restricted=root_restricted,
            leaf_ids=tuple(leaf_ids),
        )

    overlap = set(roots) & set(leaves)
    if overlap:
        raise ValueError(f"ids used as both root and leaf: {sorted(overlap)}")

    return Taxonomy(roots, leaves)


@functools.lru_cache(maxsize=1)
def default_taxonomy() -> Taxonomy:
    return load_taxonomy()
