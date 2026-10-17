"""Monte Carlo fleet availability simulator (reactive vs planned policies)."""
from __future__ import annotations

import numpy as np

from .ml import Z80


def simulate(aircraft, res, plan, p, cpd, policy="planned", n_runs=200, seed=0):
    H, D, U = p["horizon_days"], p["service_days"], p["unplanned_days"]
    n = len(aircraft)
    rng = np.random.default_rng(seed)
    start = {r["aircraft_id"]: r["start_day"] for r in (plan or [])} if policy == "planned" else {}
    curves = np.zeros((n_runs, H))
    for run in range(n_runs):
        down = np.zeros((n, H), dtype=bool)
        pool = {k: [v["stock"], v["resupply_qty"]] for k, v in res["spares"].items()}
        events = []
        for i, a in enumerate(aircraft):
            if a["status"] == "in_maintenance":
                down[i, : a["remaining_maint_days"]] = True
                continue
            sigma = max((a["rul_p90"] - a["rul_p10"]) / (2 * Z80), 1.0)
            fail_day = max(rng.normal(a["rul_p50"], sigma), 0.5) / cpd
            s = start.get(a["aircraft_id"])
            if s is not None and s <= fail_day:
                pool[a["part_no"]][0] = max(pool[a["part_no"]][0], 0)  # planned job has its spare reserved by the optimiser
                down[i, s : min(s + D, H)] = True
            elif fail_day < H:
                events.append((fail_day, i, a["part_no"]))
        for fail_day, i, part in sorted(events):
            day = int(np.ceil(fail_day))
            st, rs = pool[part]
            wait = 0
            if st > 0:
                pool[part][0] -= 1
            else:
                lead = res["spares"][part]["lead_days"]
                wait = max(0, lead - day)
            if day < H:
                down[i, day : min(day + U + wait, H)] = True
        curves[run] = 1 - down.mean(axis=0)
    demand_ok = float(np.mean(curves.min(axis=1) * n >= p["min_available"]))
    return {
        "policy": policy,
        "runs": n_runs,
        "days": list(range(H)),
        "availability_mean": curves.mean(0).round(4).tolist(),
        "availability_p10": np.percentile(curves, 10, axis=0).round(4).tolist(),
        "availability_p90": np.percentile(curves, 90, axis=0).round(4).tolist(),
        "mean_availability": round(float(curves.mean()), 4),
        "prob_demand_met_every_day": round(demand_ok, 3),
    }
