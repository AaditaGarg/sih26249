"""RUL model: quantile gradient boosting + conformal calibration (CQR).

Split is by engine (never by row) to avoid leakage. Intervals are calibrated on
a held-out engine set so the nominal 80% interval has measured coverage.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor

from . import synth

Z80 = 1.2816  # z for a central 80% interval


def _norm_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def p_fail_within(med: float, lo: float, hi: float, cycles: float) -> float:
    """P(RUL <= cycles) using a normal fitted to the calibrated 80% interval, truncated at 0."""
    sigma = max((hi - lo) / (2 * Z80), 1.0)
    p0 = _norm_cdf((0 - med) / sigma)
    p = (_norm_cdf((cycles - med) / sigma) - p0) / max(1 - p0, 1e-9)
    return float(min(max(p, 0.0), 1.0))


@dataclass
class RULModel:
    models: dict = field(default_factory=dict)
    qhat: float = 0.0
    baseline: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)

    def fit(self, n_engines: int = 160, seed: int = 7) -> "RULModel":
        X, y, g, baseline = synth.build_training(n_engines, seed)
        self.baseline = baseline
        ids = np.unique(g)
        rng = np.random.default_rng(seed)
        rng.shuffle(ids)
        n = len(ids)
        tr, cal, te = ids[: int(0.6 * n)], ids[int(0.6 * n) : int(0.8 * n)], ids[int(0.8 * n) :]
        m = lambda s: np.isin(g, s)
        for name, alpha in (("lo", 0.1), ("med", 0.5), ("hi", 0.9)):
            self.models[name] = GradientBoostingRegressor(
                loss="quantile", alpha=alpha, n_estimators=120, max_depth=3,
                learning_rate=0.08, subsample=0.8, random_state=seed,
            ).fit(X[m(tr)], y[m(tr)])
        # Conformalized quantile regression on the calibration engines.
        lo, _, hi = self._raw(X[m(cal)])
        scores = np.maximum(lo - y[m(cal)], y[m(cal)] - hi)
        k = min(math.ceil((len(scores) + 1) * 0.8) / len(scores), 1.0)
        self.qhat = float(np.quantile(scores, k))
        # Held-out metrics.
        lo, med, hi = self.predict(X[m(te)])
        yt = y[m(te)]
        near = yt <= 30
        alert = med <= 30
        self.metrics = {
            "rmse_cycles": round(float(np.sqrt(np.mean((med - yt) ** 2))), 2),
            "mae_cycles": round(float(np.mean(np.abs(med - yt))), 2),
            "interval_coverage_80": round(float(np.mean((yt >= lo) & (yt <= hi))), 3),
            "mean_interval_width": round(float(np.mean(hi - lo)), 1),
            "recall_rul_le_30": round(float((alert & near).sum() / max(near.sum(), 1)), 3),
            "precision_rul_le_30": round(float((alert & near).sum() / max(alert.sum(), 1)), 3),
            "test_engines": int(len(te)),
            "rul_cap": synth.RUL_CAP,
            "data": "synthetic run-to-failure (not real aircraft data)",
        }
        return self

    def _raw(self, X):
        lo = self.models["lo"].predict(X)
        med = self.models["med"].predict(X)
        hi = self.models["hi"].predict(X)
        return lo, med, hi

    def predict(self, X):
        lo, med, hi = self._raw(np.atleast_2d(X))
        lo, hi = lo - self.qhat, hi + self.qhat
        lo = np.clip(np.minimum(lo, med), 0, None)
        hi = np.maximum(hi, med)
        return lo, med, hi

    def drivers(self, sensor_means: np.ndarray, top: int = 3):
        """Plain-language drivers: how far each sensor sits from its healthy baseline."""
        z = (sensor_means - self.baseline["mean"]) / self.baseline["std"]
        order = np.argsort(-np.abs(z))[:top]
        return [
            {
                "sensor": synth.SENSORS[i],
                "z_score": round(float(z[i]), 2),
                "direction": "above" if z[i] > 0 else "below",
                "note": f"{synth.SENSORS[i]} is {abs(z[i]):.1f} sd {'above' if z[i] > 0 else 'below'} healthy baseline",
            }
            for i in order
        ]
