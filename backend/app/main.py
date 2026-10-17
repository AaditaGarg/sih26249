"""SustainIQ backend (SIH26249 MVP). Synthetic data only."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from fastapi.staticfiles import StaticFiles

from . import optimizer, records, simulator
from .schemas import Decision, GenerateRequest, PlanParams, SimulateRequest
from .state import CYCLES_PER_DAY, HORIZON_FOR_RISK_DAYS, state

app = FastAPI(title="SustainIQ API", version="0.1.0",
              description="Predictive maintenance & fleet availability decision support (SIH26249). Synthetic data only.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
API = "/api/v1"
app.include_router(records.router)
app.mount("/uploads", StaticFiles(directory=records.UPLOADS), name="uploads")


@app.on_event("startup")
def warm_up():
    with state.lock:
        if not state.aircraft:
            state.generate(40, 42)


def _need_fleet():
    with state.lock:
        if not state.aircraft:
            state.generate(40, 42)


def _params(req: PlanParams, n: int):
    p = req.model_dump()
    p["min_available"] = req.min_available if req.min_available is not None else int(0.75 * n)
    return p


@app.get(f"{API}/health")
def health():
    return {"status": "ok", "model_loaded": state.model is not None, "fleet_size": len(state.aircraft),
            "data": "synthetic"}


@app.post(f"{API}/fleet/generate")
def generate(req: GenerateRequest):
    state.generate(req.n, req.seed)
    return {"fleet_size": len(state.aircraft), "seed": req.seed}


@app.get(f"{API}/model/metrics")
def metrics():
    return state.ensure_model().metrics


@app.get(f"{API}/fleet/summary")
def summary():
    _need_fleet()
    ac = state.aircraft
    n = len(ac)
    avail = sum(1 for a in ac if a["status"] == "available")
    dist = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
    for a in ac:
        if a["status"] == "available":
            dist[a["risk_band"]] += 1
    expected_loss = sum(a["risk_horizon"] for a in ac if a["status"] == "available")
    return {
        "total_aircraft": n,
        "available_now": avail,
        "in_maintenance": n - avail,
        "availability_now_pct": round(100 * avail / n, 1),
        "risk_distribution": dist,
        "expected_unplanned_failures_next_14d": round(expected_loss, 2),
        "reactive_availability_forecast_pct": round(100 * (avail - expected_loss) / n, 1),
        "risk_horizon_days": HORIZON_FOR_RISK_DAYS,
        "resources": state.resources,
        "data": "synthetic",
    }


@app.get(f"{API}/aircraft")
def list_aircraft():
    _need_fleet()
    return [{k: a[k] for k in ("aircraft_id", "base", "part_no", "status", "rul_p50", "risk_horizon", "risk_band")}
            for a in state.aircraft]


@app.get(f"{API}/aircraft/{{aircraft_id}}")
def aircraft_detail(aircraft_id: str):
    _need_fleet()
    a = next((x for x in state.aircraft if x["aircraft_id"] == aircraft_id), None)
    if not a:
        raise HTTPException(404, "aircraft not found")
    return a


@app.get(f"{API}/maintenance/queue")
def queue():
    _need_fleet()
    res = state.resources
    rows = []
    for a in state.aircraft:
        if a["status"] != "available" or a["risk_band"] == "Low":
            continue
        sp = res["spares"][a["part_no"]]
        rows.append({
            "aircraft_id": a["aircraft_id"], "risk_band": a["risk_band"], "risk_horizon": a["risk_horizon"],
            "rul_p10": a["rul_p10"], "rul_p50": a["rul_p50"], "rul_p90": a["rul_p90"],
            "part_no": a["part_no"], "spare_in_stock": sp["stock"] > 0,
            "spare_lead_days": sp["lead_days"], "top_driver": a["drivers"][0]["note"],
        })
    rows.sort(key=lambda r: -r["risk_horizon"])
    return rows


@app.post(f"{API}/optimize")
def optimize(req: PlanParams = PlanParams()):
    _need_fleet()
    p = _params(req, len(state.aircraft))
    res = state.resources_for(req.spares_multiplier, req.bays, req.tech_hours_per_day)
    out = optimizer.solve_plan(state.aircraft, res, p, CYCLES_PER_DAY)
    out["params"] = {k: p[k] for k in ("horizon_days", "service_days", "unplanned_days", "min_available")}
    state.last_plan = out
    return out


@app.post(f"{API}/simulate")
def simulate(req: SimulateRequest = SimulateRequest()):
    _need_fleet()
    p = _params(req, len(state.aircraft))
    res = state.resources_for(req.spares_multiplier, req.bays, req.tech_hours_per_day)
    plan = None
    if req.policy == "planned":
        plan = optimizer.solve_plan(state.aircraft, res, p, CYCLES_PER_DAY)["plan"]
    return simulator.simulate(state.aircraft, res, plan, p, CYCLES_PER_DAY, req.policy, req.n_runs, req.seed)


@app.post(f"{API}/recommendations/{{aircraft_id}}/decision")
def decide(aircraft_id: str, d: Decision):
    if not state.last_plan:
        raise HTTPException(409, "run /optimize first")
    item = next((r for r in state.last_plan["plan"] if r["aircraft_id"] == aircraft_id), None)
    if not item:
        raise HTTPException(404, "no recommendation for this aircraft in the latest plan")
    state.audit.append(state._audit(d.actor, f"recommendation_{d.decision}",
                                    f"{aircraft_id} start_day={item['start_day']} reason={d.reason}"))
    return {"aircraft_id": aircraft_id, "decision": d.decision, "recorded": True}


@app.get(f"{API}/audit")
def audit():
    return state.audit
