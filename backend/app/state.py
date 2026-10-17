"""In-memory application state (MVP). Replace with PostgreSQL/Timescale per the TRD."""
from __future__ import annotations

import copy
import threading
from datetime import datetime, timezone

from . import synth
from .ml import RULModel, p_fail_within

CYCLES_PER_DAY = 1.2
HORIZON_FOR_RISK_DAYS = 14


def band(risk: float) -> str:
    return "Critical" if risk >= 0.5 else "High" if risk >= 0.2 else "Medium" if risk >= 0.05 else "Low"


class State:
    def __init__(self):
        self.model: RULModel | None = None
        self.aircraft: list[dict] = []
        self.resources: dict = {}
        self.last_plan: dict | None = None
        self.audit: list[dict] = []
        self.lock = threading.RLock()
        self.gen = 0

    def ensure_model(self) -> RULModel:
        with self.lock:
            if self.model is None:
                self.model = RULModel().fit()
            return self.model

    def generate(self, n: int, seed: int):
        with self.lock:
            self._generate(n, seed)
            self.gen += 1

    def _generate(self, n: int, seed: int):
        model = self.ensure_model()
        raw = synth.generate_fleet_raw(n, seed)
        lo, med, hi = model.predict([r["features"] for r in raw])
        self.aircraft = []
        for r, l, m, h in zip(raw, lo, med, hi):
            risk = p_fail_within(m, l, h, HORIZON_FOR_RISK_DAYS * CYCLES_PER_DAY)
            self.aircraft.append({
                **{k: v for k, v in r.items() if k not in ("features", "sensor_means")},
                "rul_p10": round(float(l), 1), "rul_p50": round(float(m), 1), "rul_p90": round(float(h), 1),
                "risk_horizon": round(risk, 4), "risk_band": band(risk),
                "drivers": model.drivers(r["sensor_means"]),
            })
        self.resources = synth.default_resources(n)
        self.last_plan = None
        self.audit.append(self._audit("system", "generate_fleet", f"n={n} seed={seed}"))

    def resources_for(self, spares_multiplier=1.0, bays=None, tech=None):
        res = copy.deepcopy(self.resources)
        for v in res["spares"].values():
            v["stock"] = int(round(v["stock"] * spares_multiplier))
            v["resupply_qty"] = int(round(v["resupply_qty"] * spares_multiplier))
        if bays is not None:
            res["bays"] = bays
        if tech is not None:
            res["tech_hours_per_day"] = tech
        return res

    @staticmethod
    def _audit(actor, action, detail):
        return {"ts": datetime.now(timezone.utc).isoformat(), "actor": actor, "action": action, "detail": detail}


state = State()
