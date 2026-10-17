"""Synthetic degradation + fleet data (SIH prototype: NO real aircraft data).

Sensors drift towards failure following a power-law wear curve. This stands in
for NASA C-MAPSS style run-to-failure data and keeps the repo self-contained.
Swap this module for real connectors that honour the same function contracts.
"""
from __future__ import annotations

import numpy as np

SENSORS = ["egt_margin", "vibration", "oil_pressure", "fuel_flow"]
BASE = np.array([60.0, 1.0, 55.0, 2.0])
SCALE = np.array([-35.0, 2.5, -12.0, 0.9])  # total drift at end of life (sign = direction)
NOISE = np.array([2.0, 0.12, 1.0, 0.05])
RUL_CAP = 125
WINDOW = 20

FEATURE_NAMES = (
    [f"{s}_mean" for s in SENSORS]
    + [f"{s}_last" for s in SENSORS]
    + [f"{s}_slope" for s in SENSORS]
    + [f"{s}_std" for s in SENSORS]
    + ["age_cycles"]
)


def wear(t: np.ndarray, life: float, onset_frac: float = 0.35, power: float = 1.6) -> np.ndarray:
    onset = onset_frac * life
    x = np.clip((t - onset) / (life - onset), 0, None)
    return x**power


def simulate_history(rng: np.random.Generator, life: int, upto: int, wear_scale: float = 1.0) -> np.ndarray:
    """Sensor history for cycles 1..upto of an engine whose life is `life` cycles."""
    t = np.arange(1, upto + 1)
    h = wear(t, life)[:, None]
    return BASE + SCALE * h * wear_scale + rng.normal(0, 1, (upto, len(SENSORS))) * NOISE


def window_features(hist: np.ndarray, t: int) -> np.ndarray:
    """Feature vector from the last WINDOW cycles of `hist` ending at cycle t (1-indexed)."""
    w = hist[t - WINDOW : t]
    x = np.arange(WINDOW) - (WINDOW - 1) / 2
    slope = (x[:, None] * (w - w.mean(0))).sum(0) / (x**2).sum()
    return np.concatenate([w.mean(0), w[-1], slope, w.std(0), [t]])


def build_training(n_engines: int = 160, seed: int = 7):
    rng = np.random.default_rng(seed)
    X, y, groups, healthy = [], [], [], []
    for e in range(n_engines):
        life = int(np.clip(rng.normal(200, 35), 110, 320))
        hist = simulate_history(rng, life, life, wear_scale=rng.normal(1.0, 0.1))
        for t in range(WINDOW, life, 4):
            X.append(window_features(hist, t))
            y.append(min(life - t, RUL_CAP))
            groups.append(e)
            if t < 0.3 * life:
                healthy.append(hist[t - WINDOW : t].mean(0))
    healthy = np.array(healthy)
    baseline = {"mean": healthy.mean(0), "std": healthy.std(0) + 1e-6}
    return np.array(X), np.array(y, dtype=float), np.array(groups), baseline


def generate_fleet_raw(n: int, seed: int):
    """Returns list of dicts with hidden truth + sensor history features."""
    rng = np.random.default_rng(seed)
    bases = ["Base-A", "Base-B", "Base-C"]
    parts = ["ENG-HPT", "ENG-FUEL", "ENG-BRG"]
    out = []
    for i in range(n):
        life = int(np.clip(rng.normal(200, 35), 110, 320))
        true_rul = float(rng.uniform(3, 45) if rng.random() < 0.3 else rng.uniform(50, 150))
        t = int(max(WINDOW, life - true_rul))
        true_rul = float(life - t)
        hist = simulate_history(rng, life, t, wear_scale=rng.normal(1.0, 0.1))
        in_maint = rng.random() < 0.08
        out.append(
            {
                "aircraft_id": f"AC-{i + 1:03d}",
                "base": bases[i % 3],
                "part_no": parts[int(rng.integers(0, 3))],
                "status": "in_maintenance" if in_maint else "available",
                "remaining_maint_days": int(rng.integers(1, 5)) if in_maint else 0,
                "cycles": t,
                "features": window_features(hist, t),
                "sensor_means": hist[t - WINDOW : t].mean(0),
                "recent_history": hist[-60:].round(3).tolist(),
                "true_rul_synthetic": true_rul,
            }
        )
    return out


def default_resources(n: int):
    return {
        "spares": {
            "ENG-HPT": {"stock": 2, "lead_days": 4, "resupply_qty": 2},
            "ENG-FUEL": {"stock": 1, "lead_days": 3, "resupply_qty": 2},
            "ENG-BRG": {"stock": 1, "lead_days": 6, "resupply_qty": 2},
        },
        "bays": 3,
        "tech_hours_per_day": 24,
    }
