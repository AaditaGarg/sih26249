"""Resource-aware maintenance planner (OR-Tools CP-SAT).

Chooses, for each at-risk aircraft, a service start day (or deferral) that
minimises expected aircraft-days lost, subject to spares, bays, technician
hours and a soft minimum-available-aircraft demand.
"""
from __future__ import annotations

from ortools.sat.python import cp_model

from .ml import p_fail_within

SCALE = 100  # integer scaling for CP-SAT costs


def _cap(res, part, d):
    sp = res["spares"][part]
    return sp["stock"] + (sp["resupply_qty"] if d >= sp["lead_days"] else 0)


def _cost(a, s, H, D, U, cpd):
    pf_s = p_fail_within(a["rul_p50"], a["rul_p10"], a["rul_p90"], s * cpd) if s > 0 else 0.0
    d_eff = min(D, H - s)
    return (1 - pf_s) * d_eff + pf_s * U


def _defer_cost(a, H, U, cpd):
    return p_fail_within(a["rul_p50"], a["rul_p10"], a["rul_p90"], H * cpd) * U


def _maint_count(aircraft, d):
    return sum(1 for a in aircraft if a["status"] == "in_maintenance" and a["remaining_maint_days"] > d)


def solve_plan(aircraft, res, p, cpd, time_limit=10.0):
    H, D, U = p["horizon_days"], p["service_days"], p["unplanned_days"]
    n = len(aircraft)
    cands = [a for a in aircraft if a["status"] == "available" and a["risk_horizon"] >= p["risk_floor"]]
    m = cp_model.CpModel()
    x = {}
    for a in cands:
        for s in range(H):
            x[a["aircraft_id"], s] = m.NewBoolVar(f"x_{a['aircraft_id']}_{s}")
        x[a["aircraft_id"], "defer"] = m.NewBoolVar(f"d_{a['aircraft_id']}")
        m.AddExactlyOne([x[a["aircraft_id"], s] for s in range(H)] + [x[a["aircraft_id"], "defer"]])

    def started_covering(d):
        return [x[a["aircraft_id"], s] for a in cands for s in range(H) if s <= d < s + D]

    slack = []
    for d in range(H):
        free_bays = max(0, res["bays"] - _maint_count(aircraft, d))
        cover = started_covering(d)
        m.Add(sum(cover) <= free_bays)
        m.Add(sum(cover) * p["tech_hours_per_job_day"] <= res["tech_hours_per_day"])
        sl = m.NewIntVar(0, n, f"slack_{d}")
        slack.append(sl)
        m.Add(n - _maint_count(aircraft, d) - sum(cover) + sl >= p["min_available"])
        for part in res["spares"]:
            started = [x[a["aircraft_id"], s] for a in cands if a["part_no"] == part for s in range(d + 1)]
            if started:
                m.Add(sum(started) <= _cap(res, part, d))

    obj = []
    for a in cands:
        for s in range(H):
            obj.append(int(round(SCALE * _cost(a, s, H, D, U, cpd))) * x[a["aircraft_id"], s])
        obj.append(int(round(SCALE * _defer_cost(a, H, U, cpd))) * x[a["aircraft_id"], "defer"])
    obj += [int(p["shortfall_penalty"] * SCALE) * sl for sl in slack]
    m.Minimize(sum(obj))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = 4
    status = solver.Solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": "infeasible", "plan": [], "deferred": []}

    plan, deferred = [], []
    for a in cands:
        chosen = next((s for s in range(H) if solver.Value(x[a["aircraft_id"], s])), None)
        base = {"aircraft_id": a["aircraft_id"], "part_no": a["part_no"], "risk_horizon": a["risk_horizon"],
                "rul_p50": a["rul_p50"], "drivers": a["drivers"]}
        if chosen is None:
            deferred.append({**base, "reason": "Deferral minimises expected loss given resource limits (monitor closely)."})
        else:
            plan.append({**base, "action": "service", "start_day": chosen, "duration_days": D,
                         "reason": f"Risk {a['risk_horizon']:.0%} within {H}d, RUL p50 {a['rul_p50']:.0f} cycles; "
                                   f"day {chosen} is the best slot with a spare, bay and technicians available."})
    plan.sort(key=lambda r: (r["start_day"], -r["risk_horizon"]))
    plan_loss = sum(_cost(next(c for c in cands if c["aircraft_id"] == r["aircraft_id"]), r["start_day"], H, D, U, cpd) for r in plan)
    plan_loss += sum(_defer_cost(next(c for c in cands if c["aircraft_id"] == r["aircraft_id"]), H, U, cpd) for r in deferred)
    shortfall = sum(solver.Value(s) for s in slack)
    reactive_loss = sum(_defer_cost(a, H, U, cpd) for a in cands)
    greedy = _greedy(cands, aircraft, res, p, cpd)
    return {
        "status": "optimal" if status == cp_model.OPTIMAL else "feasible",
        "horizon_days": H,
        "plan": plan,
        "deferred": deferred,
        "objective": {
            "expected_aircraft_days_lost_plan": round(plan_loss, 2),
            "expected_aircraft_days_lost_reactive": round(reactive_loss, 2),
            "expected_aircraft_days_lost_greedy_risk_ranked": round(greedy, 2),
            "demand_shortfall_aircraft_days": shortfall,
            "availability_gain_vs_reactive_pct_points": round(100 * (reactive_loss - plan_loss) / (n * H), 2),
        },
        "bottlenecks": _bottlenecks(plan, res, aircraft, H, D),
    }


def _greedy(cands, aircraft, res, p, cpd):
    H, D, U = p["horizon_days"], p["service_days"], p["unplanned_days"]
    bay = [0] * H
    tech = [0] * H
    used = {part: [0] * H for part in res["spares"]}
    loss = 0.0
    for a in sorted(cands, key=lambda c: -c["risk_horizon"]):
        placed = False
        for s in range(H):
            days = [d for d in range(s, min(s + D, H))]
            if any(bay[d] + 1 > max(0, res["bays"] - _maint_count(aircraft, d)) for d in days):
                continue
            if any((bay[d] + 1) * p["tech_hours_per_job_day"] > res["tech_hours_per_day"] for d in days):
                continue
            if any(used[a["part_no"]][d] + 1 > _cap(res, a["part_no"], d) for d in range(s, H)):
                continue
            for d in days:
                bay[d] += 1
            for d in range(s, H):
                used[a["part_no"]][d] += 1
            loss += _cost(a, s, H, D, U, cpd)
            placed = True
            break
        if not placed:
            loss += _defer_cost(a, H, U, cpd)
    return loss


def _bottlenecks(plan, res, aircraft, H, D):
    out = []
    for part in res["spares"]:
        used = sum(1 for r in plan if r["part_no"] == part)
        cap = _cap(res, part, H - 1)
        if used >= cap:
            out.append({"resource": f"spare:{part}", "used": used, "capacity": cap})
    peak = 0
    for d in range(H):
        peak = max(peak, sum(1 for r in plan if r["start_day"] <= d < r["start_day"] + D))
    if peak >= res["bays"]:
        out.append({"resource": "bays", "used": peak, "capacity": res["bays"]})
    return out
