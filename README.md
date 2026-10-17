# SustainIQ – Predictive Maintenance & Fleet Availability (SIH26249)

Decision-support MVP for **SIH 2026 PS 26249: Air Power – Predictive Maintenance & Fleet Availability**.
It predicts Remaining Useful Life (RUL) with calibrated uncertainty, then plans maintenance to maximise
**fleet availability** under spares, bay and technician constraints, and simulates the outcome.

> **Data:** synthetic only. No real or classified aircraft data is used. Replace `backend/app/synth.py`
> with real connectors that keep the same contracts.

## Repo layout
```
backend/   FastAPI service (ML, optimiser, simulator)
frontend/  (next: React dashboard)
```

## Run the backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload          # http://localhost:8000/docs
pytest -q                              # run tests
```
Docker: `docker build -t sustainiq-backend backend && docker run -p 8000:8000 sustainiq-backend`

## API (`/api/v1`)
| Endpoint | Purpose |
|---|---|
| `POST /fleet/generate` | Create a synthetic fleet `{n, seed}` |
| `GET /fleet/summary` | Availability now, risk distribution, reactive forecast |
| `GET /aircraft`, `/aircraft/{id}` | Fleet list, RUL band, risk, sensor drivers |
| `GET /maintenance/queue` | Ranked at-risk aircraft with spare feasibility |
| `POST /optimize` | CP-SAT plan; compares vs reactive and greedy baselines |
| `POST /simulate` | Monte Carlo availability, `policy: reactive \| planned` |
| `POST /recommendations/{id}/decision` | Approve/reject, written to audit log |
| `GET /model/metrics`, `/audit`, `/health` | Held-out metrics, audit trail, health |

## How it works
1. **RUL model** – quantile gradient boosting (p10/p50/p90) + conformal calibration; split by engine.
2. **Risk** – P(failure within 14 days) from the calibrated RUL distribution.
3. **Optimiser** – OR-Tools CP-SAT chooses a service day (or deferral) per at-risk aircraft to minimise
   expected aircraft-days lost, with spare lead times, bays, technician hours and a soft minimum-available demand.
4. **Simulator** – samples failures from the RUL distribution; compares reactive vs planned policies over many runs.

## Known MVP limitations
- In-memory state (no database); no auth/RBAC yet (planned in the TRD).
- Interval coverage on the small synthetic test split is slightly below the nominal 80% – measured, not hidden.
- Simulator ignores bay queueing for unplanned repairs.
- Gains shown are on synthetic data and depend on the assumed parameters.
