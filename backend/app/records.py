"""Aircraft maintenance records, photo evidence, CSV ingestion and work-order drafts."""
from __future__ import annotations

import csv, io, random, uuid
from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse

from .state import state

router = APIRouter(prefix="/api/v1")
UPLOADS = Path(__file__).resolve().parent.parent / "uploads"
UPLOADS.mkdir(exist_ok=True)
EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
FAULTS = [("HPT-114", "Turbine temperature margin low"), ("FUEL-207", "Fuel flow variation during climb"),
          ("BRG-330", "Bearing vibration above trend"), ("OIL-051", "Oil pressure fluctuation on ground run"),
          ("GEN-402", "Generator output intermittent")]
TYPES = ["Scheduled inspection", "Unscheduled repair", "Snag report", "Part replacement"]
SKILLS = {"ENG-HPT": "Engine hot-section technician", "ENG-FUEL": "Fuel systems technician", "ENG-BRG": "Engine mechanical technician"}
TEMPLATES = {"maintenance_records": "aircraft_id,date,type,fault_code,description,hours_spent\nAC-001,2026-09-12,Snag report,BRG-330,Vibration above trend on ground run,4\n",
             "spares": "part_no,stock,lead_days,resupply_qty\nENG-HPT,2,4,2\nENG-FUEL,1,3,2\nENG-BRG,1,6,2\n"}
_store = {"gen": -1, "rec": {}}


def _fleet():
    with state.lock:
        if not state.aircraft:
            state.generate(40, 42)


def _ac(aid):
    _fleet()
    a = next((x for x in state.aircraft if x["aircraft_id"] == aid), None)
    if not a:
        raise HTTPException(404, "aircraft not found")
    return a


def _records(aid):
    if _store["gen"] != state.gen:
        _store.update(gen=state.gen, rec={})
    if aid not in _store["rec"]:
        rnd, today, out = random.Random(aid), date.today(), []
        for _ in range(rnd.randint(3, 7)):
            t, f = rnd.choice(TYPES), rnd.choice(FAULTS)
            routine = t == "Scheduled inspection"
            out.append({"id": uuid.uuid4().hex[:8], "date": str(today - timedelta(days=rnd.randint(10, 700))), "type": t,
                        "fault_code": "" if routine else f[0], "description": "Routine inspection, no defects found" if routine else f[1],
                        "hours_spent": rnd.choice([2, 4, 6, 8, 12, 16]), "photo_url": None, "source": "synthetic"})
        out.sort(key=lambda r: r["date"], reverse=True)
        _store["rec"][aid] = out
    return _store["rec"][aid]


@router.get("/aircraft/{aid}/records")
def list_records(aid: str):
    _ac(aid)
    return _records(aid)


@router.post("/aircraft/{aid}/records")
async def add_record(aid: str, type: str = Form(...), description: str = Form(...), fault_code: str = Form(""),
                     hours_spent: float = Form(0), photo: UploadFile | None = File(None)):
    _ac(aid)
    url = None
    if photo and photo.filename:
        if photo.content_type not in EXT:
            raise HTTPException(400, "Photo must be a JPEG, PNG, WebP or GIF image.")
        data = await photo.read()
        if len(data) > 5 * 1024 * 1024:
            raise HTTPException(400, "Photo is larger than 5 MB.")
        name = uuid.uuid4().hex + EXT[photo.content_type]
        (UPLOADS / name).write_bytes(data)
        url = f"/uploads/{name}"
    rec = {"id": uuid.uuid4().hex[:8], "date": str(date.today()), "type": type, "fault_code": fault_code,
           "description": description, "hours_spent": hours_spent, "photo_url": url, "source": "user"}
    _records(aid).insert(0, rec)
    state.audit.append(state._audit("maintenance_officer", "record_added", f"{aid} {type} photo={bool(url)}"))
    return rec


@router.get("/aircraft/{aid}/workorder")
def work_order(aid: str):
    a = _ac(aid)
    item = next((r for r in (state.last_plan or {}).get("plan", []) if r["aircraft_id"] == aid), None)
    sp = state.resources["spares"][a["part_no"]]
    return {"aircraft_id": aid, "status": "Draft, needs officer approval",
            "task": f"Inspect and service {a['part_no']}", "planned_start_day": item["start_day"] if item else None,
            "reason": f"{a['risk_horizon']:.0%} chance of failure within 14 days; " + "; ".join(d["note"] for d in a["drivers"][:2]),
            "parts": [{"part_no": a["part_no"], "qty": 1, "in_stock": sp["stock"], "lead_days": sp["lead_days"]}],
            "skills": [SKILLS.get(a["part_no"], "Engine technician")], "estimated_hours": 16, "bay": "Any free bay"}


@router.get("/resources")
def resources():
    _fleet()
    return state.resources


@router.get("/ingest/template/{kind}", response_class=PlainTextResponse)
def template(kind: str):
    if kind not in TEMPLATES:
        raise HTTPException(404, "unknown template")
    return PlainTextResponse(TEMPLATES[kind], headers={"Content-Disposition": f"attachment; filename={kind}.csv"})


@router.post("/ingest/{kind}")
async def ingest(kind: str, file: UploadFile = File(...)):
    if kind not in TEMPLATES:
        raise HTTPException(404, "unknown data type")
    _fleet()
    rows = list(csv.DictReader(io.StringIO((await file.read()).decode("utf-8-sig"))))
    need = TEMPLATES[kind].split("\n")[0].split(",")
    cols = set(rows[0].keys()) if rows else set()
    if not rows or not set(need) <= cols:
        raise HTTPException(400, f"CSV needs these columns: {', '.join(need)}")
    ok, errors, ids = 0, [], {a["aircraft_id"] for a in state.aircraft}
    for i, r in enumerate(rows, start=2):
        try:
            if kind == "maintenance_records":
                if r["aircraft_id"] not in ids:
                    raise ValueError(f"unknown aircraft {r['aircraft_id']}")
                date.fromisoformat(r["date"])
                hrs = float(r["hours_spent"])
                if hrs < 0 or not r["type"].strip():
                    raise ValueError("type is empty or hours are negative")
                _records(r["aircraft_id"]).append({"id": uuid.uuid4().hex[:8], "date": r["date"], "type": r["type"], "fault_code": r["fault_code"],
                                                   "description": r["description"], "hours_spent": hrs, "photo_url": None, "source": "upload"})
                _records(r["aircraft_id"]).sort(key=lambda x: x["date"], reverse=True)
            else:
                if r["part_no"] not in state.resources["spares"]:
                    raise ValueError(f"unknown part {r['part_no']}")
                v = [int(r[k]) for k in ("stock", "lead_days", "resupply_qty")]
                if min(v) < 0:
                    raise ValueError("values must be zero or more")
                state.resources["spares"][r["part_no"]] = {"stock": v[0], "lead_days": v[1], "resupply_qty": v[2]}
                state.last_plan = None
            ok += 1
        except (ValueError, KeyError) as e:
            errors.append({"row": i, "error": str(e)})
    state.audit.append(state._audit("data_steward", f"ingest_{kind}", f"accepted={ok} rejected={len(errors)}"))
    return {"kind": kind, "total": len(rows), "accepted": ok, "rejected": len(errors),
            "quality_score": round(ok / len(rows), 3), "errors": errors[:10]}
