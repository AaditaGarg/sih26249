from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
A = "/api/v1"


def setup_module(_):
    assert client.post(f"{A}/fleet/generate", json={"n": 40, "seed": 42}).status_code == 200


def test_model_metrics_are_sane():
    m = client.get(f"{A}/model/metrics").json()
    assert 0.7 <= m["interval_coverage_80"] <= 0.92
    assert m["rmse_cycles"] < 30
    assert m["recall_rul_le_30"] > 0.6


def test_summary_and_queue():
    s = client.get(f"{A}/fleet/summary").json()
    assert s["total_aircraft"] == 40 and 0 < s["availability_now_pct"] <= 100
    q = client.get(f"{A}/maintenance/queue").json()
    assert q == sorted(q, key=lambda r: -r["risk_horizon"])


def test_optimizer_respects_constraints_and_beats_reactive():
    r = client.post(f"{A}/optimize", json={"bays": 2}).json()
    assert r["status"] in ("optimal", "feasible")
    H, D = r["horizon_days"], r["params"]["service_days"]
    for d in range(H):
        assert sum(1 for x in r["plan"] if x["start_day"] <= d < x["start_day"] + D) <= 2
    o = r["objective"]
    assert o["expected_aircraft_days_lost_plan"] <= o["expected_aircraft_days_lost_reactive"] + 1e-6
    assert o["expected_aircraft_days_lost_plan"] <= o["expected_aircraft_days_lost_greedy_risk_ranked"] + 1e-6


def test_simulation_planned_beats_reactive():
    pl = client.post(f"{A}/simulate", json={"policy": "planned", "n_runs": 150}).json()
    re = client.post(f"{A}/simulate", json={"policy": "reactive", "n_runs": 150}).json()
    assert pl["mean_availability"] >= re["mean_availability"] - 0.002
    assert len(pl["availability_mean"]) == 14


def test_decision_audit():
    client.post(f"{A}/optimize", json={})
    plan = client.post(f"{A}/optimize", json={}).json()["plan"]
    if plan:
        r = client.post(f"{A}/recommendations/{plan[0]['aircraft_id']}/decision", json={"decision": "approve"})
        assert r.status_code == 200
        assert client.get(f"{A}/audit").json()[-1]["action"] == "recommendation_approve"


def test_records_photo_and_ingest():
    rs = client.get(f"{A}/aircraft/AC-001/records").json()
    assert len(rs) >= 3
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 20
    r = client.post(f"{A}/aircraft/AC-001/records", data={"type": "Snag report", "description": "crack"},
                    files={"photo": ("x.png", png, "image/png")})
    assert r.status_code == 200 and r.json()["photo_url"].startswith("/uploads/")
    assert client.post(f"{A}/aircraft/AC-001/records", data={"type": "t", "description": "d"},
                       files={"photo": ("x.txt", b"hi", "text/plain")}).status_code == 400
    csv_ok = b"aircraft_id,date,type,fault_code,description,hours_spent\nAC-002,2026-01-05,Snag report,X,desc,3\nAC-999,2026-01-05,Snag report,X,desc,3\n"
    rep = client.post(f"{A}/ingest/maintenance_records", files={"file": ("r.csv", csv_ok, "text/csv")}).json()
    assert rep["accepted"] == 1 and rep["rejected"] == 1
    assert "task" in client.get(f"{A}/aircraft/AC-001/workorder").json()
