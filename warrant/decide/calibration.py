"""Calibration — turning a raw score into a probability that means something.

The cost model in `policy.py` consumes `p_violation` and multiplies it by real
rupee amounts. That arithmetic is only meaningful if 0.8 actually means "wrong
about 20% of the time". A raw score from a model or a heuristic is not a
probability, so it is mapped through isotonic regression fitted on the
**validation split only** (03 §3.4, and rule 4).

Isotonic rather than Platt scaling: it makes no assumption about the shape of
the mapping beyond monotonicity, and with a few hundred points that is the
safer choice.

**A caveat worth stating plainly.** Most decisions are settled by rules, which
produce a hard 0 or 1 rather than a score to calibrate. Only the fraction that
reaches the semantic checker has a genuinely graded confidence, so the
calibration set is much smaller than the validation split. Reported as
`n_effective` alongside the ECE so the number is read with that in mind.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "calibration.json"


def expected_calibration_error(
    probs: list[float], labels: list[int], bins: int = 10
) -> float:
    """Expected Calibration Error: mean |confidence - accuracy| per bin.

    The headline number for "does 0.8 mean 0.8?".
    """
    if not probs:
        return 0.0
    p = np.asarray(probs, dtype=float)
    y = np.asarray(labels, dtype=float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = 0.0
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p > lo) & (p <= hi) if i > 0 else (p >= lo) & (p <= hi)
        if not mask.any():
            continue
        total += mask.mean() * abs(p[mask].mean() - y[mask].mean())
    return float(total)


def reliability_bins(
    probs: list[float], labels: list[int], bins: int = 10
) -> list[dict]:
    """Points for a reliability diagram: predicted vs observed, per bin."""
    p = np.asarray(probs, dtype=float)
    y = np.asarray(labels, dtype=float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    out = []
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p > lo) & (p <= hi) if i > 0 else (p >= lo) & (p <= hi)
        if not mask.any():
            out.append({"bin_lo": lo, "bin_hi": hi, "n": 0,
                        "predicted": None, "observed": None})
            continue
        out.append({
            "bin_lo": float(lo), "bin_hi": float(hi), "n": int(mask.sum()),
            "predicted": float(p[mask].mean()),
            "observed": float(y[mask].mean()),
        })
    return out


@dataclass
class Calibrator:
    """Maps raw score -> calibrated P(violation)."""

    fitted: bool = False
    n_effective: int = 0
    ece_before: float = 0.0
    ece_after: float = 0.0
    _model: object | None = field(default=None, repr=False)

    def fit(self, raw_scores: list[float], labels: list[int]) -> "Calibrator":
        """Fit on validation only. Never on train, never on test."""
        if len(raw_scores) != len(labels):
            raise ValueError("scores and labels must be the same length")
        if len(set(labels)) < 2 or len(raw_scores) < 20:
            # Not enough signal to fit anything meaningful. Stay unfitted and
            # pass scores through rather than invent a mapping from noise.
            self.fitted = False
            self.n_effective = len(raw_scores)
            return self

        from sklearn.isotonic import IsotonicRegression

        self.ece_before = expected_calibration_error(raw_scores, labels)
        model = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        model.fit(np.asarray(raw_scores, dtype=float), np.asarray(labels, dtype=float))
        self._model = model
        self.fitted = True
        self.n_effective = len(raw_scores)
        self.ece_after = expected_calibration_error(
            [float(x) for x in model.predict(np.asarray(raw_scores, dtype=float))],
            labels,
        )
        return self

    def transform(self, raw: float) -> float:
        if not self.fitted or self._model is None:
            return float(min(max(raw, 0.0), 1.0))
        return float(np.clip(self._model.predict([raw])[0], 0.0, 1.0))

    def transform_many(self, raws: list[float]) -> list[float]:
        if not self.fitted or self._model is None:
            return [float(min(max(r, 0.0), 1.0)) for r in raws]
        return [float(x) for x in np.clip(
            self._model.predict(np.asarray(raws, dtype=float)), 0.0, 1.0
        )]

    # -- persistence -------------------------------------------------------

    def save(self, path: Path = DEFAULT_PATH) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "fitted": self.fitted,
            "n_effective": self.n_effective,
            "ece_before": self.ece_before,
            "ece_after": self.ece_after,
        }
        if self.fitted and self._model is not None:
            payload["x"] = [float(v) for v in self._model.X_thresholds_]
            payload["y"] = [float(v) for v in self._model.y_thresholds_]
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path = DEFAULT_PATH) -> "Calibrator":
        if not path.exists():
            return cls()
        payload = json.loads(path.read_text(encoding="utf-8"))
        cal = cls(
            fitted=bool(payload.get("fitted")),
            n_effective=int(payload.get("n_effective", 0)),
            ece_before=float(payload.get("ece_before", 0.0)),
            ece_after=float(payload.get("ece_after", 0.0)),
        )
        if cal.fitted and "x" in payload:
            from sklearn.isotonic import IsotonicRegression

            model = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            model.fit(np.asarray(payload["x"]), np.asarray(payload["y"]))
            cal._model = model
        return cal
