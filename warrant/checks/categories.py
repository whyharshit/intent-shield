"""C4 stage 1 — map a cart line item onto the category taxonomy.

This is the step that catches the whisky case, and it does so without an LLM.

**It maps from the product title, never from `merchant_category`.** That field
carries the generator's ground-truth label; reading it would make the
evaluation circular and the reported accuracy meaningless. In production the
same reasoning applies for a different reason — the merchant's category string
comes from the merchant, in the merchant's own taxonomy, and a cart that wants
to slip something past the check is exactly the cart that would mislabel it.
A merchant hint may *corroborate* a text-derived answer; it may never override
one. See `MappedCategory.method` for which path decided.

Order of resolution (03 §3.2):

1. **Restricted keyword** — a narrow, high-precision list for age-gated goods
   only: "whisky", "lager", "cigarette". These win outright, because the cost
   of letting alcohol through a no-alcohol mandate is far higher than the cost
   of an unnecessary escalation.
2. **Embedding** — cosine against precomputed leaf centroids. The primary path.
3. **Keyword fallback** — the taxonomy's general `keywords`, consulted only
   when the embedding is ambiguous.
4. **UNKNOWN** — below threshold, or the top two leaves too close to call.
   Never a guess. An unknown category forces escalation, which is the correct
   behaviour when the alternative is a confident wrong answer on a payment.

An earlier version ran general keywords *first* for speed, which inverted the
design in 03 §3.2 and dropped root accuracy to 63.9%. The failure was
instructive: an ingredient or flavour word does not identify a product's
category. "Orange Juice" is a beverage, not fruit; "Almond Face Wash" is
skincare; a "tablet" is pharma. Worse, `insurance` carried the keyword
"premium", so *Tuborg Super Premium Danish Beer* mapped to `insurance` and
would have passed a no-alcohol mandate. Keywords now name product types only,
and general keywords no longer pre-empt the embedding. See DECISIONS.md L-009.

Fail closed: if the embedding model cannot be loaded, the mapper degrades to
keywords alone and marks its own confidence accordingly, rather than failing
open and letting everything through as unmatched.
"""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

import numpy as np

from warrant.taxonomy import UNKNOWN, Taxonomy, default_taxonomy

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"

# Weight kept on the hand-written leaf description when prototype titles are
# blended in. Keeps a leaf anchored to its own definition rather than to a few
# possibly-noisy examples.
DESCRIPTION_WEIGHT = 0.35

# Cosine score above which an embedding match is accepted outright.
#
# Chosen by sweeping on a 60% split of the catalog and reading the held-out 40%
# once. The objective weights a silent misclassification at 3x an abstention: a
# wrong category can approve a denied item, whereas an abstention only costs an
# escalation. See eval/run_categories.py and DECISIONS.md D-029.
TAU_HIGH = 0.34
# Minimum margin between the best and second-best leaf. Two leaves scoring
# 0.44 and 0.43 is not a match, it is a coin toss — and a coin toss on a
# denied-category check is exactly what must not happen silently.
TAU_MARGIN = 0.035

Method = Literal["keyword", "embedding", "unknown", "keyword-degraded"]


@dataclass(frozen=True)
class MappedCategory:
    leaf_id: str          # a taxonomy leaf, or UNKNOWN
    score: float
    method: Method
    runner_up: str | None = None

    @property
    def is_known(self) -> bool:
        return self.leaf_id != UNKNOWN


def _normalise(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s%/-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class CategoryMapper:
    """Maps free-text product titles to taxonomy leaves."""

    def __init__(
        self,
        taxonomy: Taxonomy | None = None,
        model_name: str = DEFAULT_MODEL,
        use_embeddings: bool = True,
    ):
        self.tax = taxonomy or default_taxonomy()
        self.model_name = model_name
        self._model = None
        self._centroids: np.ndarray | None = None
        self._leaf_order: list[str] = []
        self._degraded = not use_embeddings
        self._fitted = False
        self._keyword_patterns = self._compile_keywords()
        if use_embeddings:
            self._try_load_embeddings()

    # -- keyword path -----------------------------------------------------

    def _compile_keywords(self) -> list[tuple[re.Pattern, str, bool]]:
        """One pattern per leaf, tagged with whether the leaf is restricted.

        Keywords match on word boundaries. Substring matching caused three
        separate defects while building the catalog — "bra" inside "Chhabra",
        "kheer" inside "Kheera", "bread" inside "breaded" — so it is not used
        here either.
        """
        patterns = []
        for leaf in self.tax.leaves.values():
            if not leaf.keywords:
                continue
            alts = sorted(
                (re.escape(k.lower()) for k in leaf.keywords), key=len, reverse=True
            )
            patterns.append(
                (
                    re.compile(r"\b(?:" + "|".join(alts) + r")\b", re.I),
                    leaf.id,
                    self.tax.is_restricted(leaf.id),
                )
            )
        return patterns

    def _keyword_hits(self, text: str, restricted_only: bool) -> list[tuple[str, int]]:
        """Every leaf whose keywords appear, with the length of the match."""
        hits = []
        for pattern, leaf_id, restricted in self._keyword_patterns:
            if restricted_only and not restricted:
                continue
            m = pattern.search(text)
            if m:
                hits.append((leaf_id, len(m.group(0))))
        return hits

    def _restricted_match(self, text: str) -> str | None:
        """Age-gated goods, decided on keywords alone.

        Deliberately asymmetric. A false positive here costs an escalation; a
        false negative lets whisky through a mandate that forbids it. The
        taxonomy's restricted keywords are product nouns ("whisky", "lager",
        "cigarette"), so this is precise in practice.
        """
        hits = self._keyword_hits(text, restricted_only=True)
        if not hits:
            return None
        return max(hits, key=lambda h: h[1])[0]

    def _fallback_match(self, text: str) -> str | None:
        """General keywords, consulted only when the embedding is unsure.

        Requires an unambiguous answer: if two leaves both match at the same
        length, this declines rather than pick one. A coin toss on a
        denied-category check is exactly what must not happen silently.
        """
        hits = self._keyword_hits(text, restricted_only=False)
        if not hits:
            return None
        best = max(h[1] for h in hits)
        winners = {leaf for leaf, length in hits if length == best}
        return winners.pop() if len(winners) == 1 else None

    # -- embedding path ---------------------------------------------------

    def _leaf_document(self, leaf_id: str) -> str:
        """Text describing a leaf, used to build its centroid."""
        leaf = self.tax.leaves[leaf_id]
        root = self.tax.roots[leaf.root]
        return ". ".join(
            [leaf.label, leaf.description, root.label, ", ".join(leaf.keywords)]
        )

    def fit_examples(self, examples: list[tuple[str, str]]) -> None:
        """Blend real product titles into each leaf's centroid.

        A hand-written category description and a real product title do not
        occupy the same region of embedding space. "Consumer electronics,
        headphones and accessories" is prose; "Boult X1 with Dual Dynamic
        Drivers, BoomX Rich Bass, IPX5" is a spec dump. Scoring the second
        against the first gave cosines around 0.15 and sent most of the
        electronics catalog to UNKNOWN.

        Averaging in a few labelled titles per leaf fixes that. `examples` is
        (title, leaf_id) and **must come from the training split only** — using
        the items the mapper is later scored on would make the accuracy
        meaningless.
        """
        if self._model is None or self._centroids is None:
            return
        by_leaf: dict[str, list[str]] = {}
        for title, leaf_id in examples:
            if leaf_id in self.tax.leaves:
                by_leaf.setdefault(leaf_id, []).append(_normalise(title))
        if not by_leaf:
            return

        flat = [(leaf, t) for leaf, ts in by_leaf.items() for t in ts]
        vecs = np.asarray(
            self._model.encode(
                [t for _, t in flat], normalize_embeddings=True, show_progress_bar=False
            ),
            dtype=np.float32,
        )
        sums: dict[str, np.ndarray] = {}
        counts: dict[str, int] = {}
        for (leaf, _), v in zip(flat, vecs):
            sums[leaf] = sums.get(leaf, np.zeros_like(v)) + v
            counts[leaf] = counts.get(leaf, 0) + 1

        # The description still carries weight, so a leaf with one noisy example
        # is not dragged away from its own definition.
        blended = self._centroids.copy()
        for i, leaf_id in enumerate(self._leaf_order):
            if leaf_id not in sums:
                continue
            proto = sums[leaf_id] / counts[leaf_id]
            mixed = DESCRIPTION_WEIGHT * blended[i] + (1 - DESCRIPTION_WEIGHT) * proto
            norm = np.linalg.norm(mixed)
            if norm > 0:
                blended[i] = mixed / norm
        self._centroids = blended
        self._fitted = True

    def _try_load_embeddings(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            self._degraded = True
            return
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            self._model = SentenceTransformer(
                self.model_name, cache_folder=str(CACHE_DIR)
            )
            self._leaf_order = list(self.tax.leaves)
            docs = [self._leaf_document(c) for c in self._leaf_order]
            vecs = self._model.encode(
                docs, normalize_embeddings=True, show_progress_bar=False
            )
            self._centroids = np.asarray(vecs, dtype=np.float32)
        except Exception:
            # A missing model download, no network, a corrupted cache. Degrade
            # to keywords rather than failing the whole verification path.
            self._model = None
            self._centroids = None
            self._degraded = True

    @property
    def fitted(self) -> bool:
        """True once prototype titles have been blended into the centroids."""
        return self._fitted

    @property
    def degraded(self) -> bool:
        """True when running without embeddings. Reported, never hidden."""
        return self._degraded

    def _embed_match(self, texts: list[str]) -> list[tuple[str, float, str | None]]:
        if self._model is None or self._centroids is None:
            return [(UNKNOWN, 0.0, None)] * len(texts)
        vecs = np.asarray(
            self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False),
            dtype=np.float32,
        )
        sims = vecs @ self._centroids.T
        out = []
        for row in sims:
            order = np.argsort(-row)
            best, second = int(order[0]), int(order[1])
            top, runner = float(row[best]), float(row[second])
            leaf = self._leaf_order[best]
            runner_id = self._leaf_order[second]
            if top >= TAU_HIGH and (top - runner) >= TAU_MARGIN:
                out.append((leaf, top, runner_id))
            else:
                out.append((UNKNOWN, top, runner_id))
        return out

    # -- public API -------------------------------------------------------

    def map_one(self, title: str, description: str | None = None) -> MappedCategory:
        return self.map_many([(title, description)])[0]

    def map_many(
        self, items: Iterable[tuple[str, str | None]]
    ) -> list[MappedCategory]:
        """Map a batch. Batched because encoding one string at a time is slow."""
        items = list(items)
        texts = [_normalise(f"{t} {d or ''}".strip()) for t, d in items]

        results: list[MappedCategory | None] = [None] * len(texts)
        needs_embedding: list[int] = []

        # 1. restricted goods win outright
        for i, text in enumerate(texts):
            leaf = self._restricted_match(text)
            if leaf:
                results[i] = MappedCategory(
                    leaf_id=leaf,
                    score=1.0,
                    method="keyword-degraded" if self._degraded else "keyword",
                )
            else:
                needs_embedding.append(i)

        # 2. embeddings, then 3. keyword fallback where they were unsure
        for i in needs_embedding:
            results[i] = MappedCategory(UNKNOWN, 0.0, "unknown")
        if needs_embedding and self._model is not None:
            matched = self._embed_match([texts[i] for i in needs_embedding])
            for i, (leaf, score, runner) in zip(needs_embedding, matched):
                if leaf != UNKNOWN:
                    results[i] = MappedCategory(leaf, score, "embedding", runner)
                    continue
                fallback = self._fallback_match(texts[i])
                results[i] = (
                    MappedCategory(fallback, score, "keyword", runner)
                    if fallback
                    else MappedCategory(UNKNOWN, score, "unknown", runner)
                )
        elif needs_embedding:
            # degraded: no embeddings, so general keywords are all there is
            for i in needs_embedding:
                fallback = self._fallback_match(texts[i])
                if fallback:
                    results[i] = MappedCategory(fallback, 0.0, "keyword-degraded")

        return [r for r in results if r is not None]


@functools.lru_cache(maxsize=1)
def default_mapper() -> CategoryMapper:
    """Shared mapper. Centroids are computed once per process."""
    return CategoryMapper()
