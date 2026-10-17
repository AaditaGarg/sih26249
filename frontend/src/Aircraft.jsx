import { useState } from "react";
import { api, upload, ORIGIN } from "./api";

const SENS = ["EGT margin", "Vibration", "Oil pressure", "Fuel flow"];
const BAND = { Critical: "#B83A24", High: "#E08A1E", Medium: "#C9AE3A", Low: "#6F8F72" };
const blank = { type: "Snag report", fault_code: "", description: "", hours_spent: "0" };

function Spark({ h, i }) {
  const v = h.map((r) => r[i]), lo = Math.min(...v), hi = Math.max(...v);
  const pts = v.map((x, k) => `${(k / (v.length - 1)) * 120},${28 - ((x - lo) / (hi - lo || 1)) * 26}`).join(" ");
  return <div className="spark"><span>{SENS[i]}</span><svg viewBox="0 0 120 30" aria-hidden="true"><polyline points={pts} fill="none" stroke="#2F5D7C" strokeWidth="2" /></svg><b>{v[v.length - 1].toFixed(2)}</b></div>;
}

export default function Aircraft({ ac }) {
  const [q, setQ] = useState(""), [d, setD] = useState(null), [recs, setRecs] = useState([]), [wo, setWo] = useState(null);
  const [form, setForm] = useState(blank), [file, setFile] = useState(null), [msg, setMsg] = useState(null);

  async function open(id) {
    setMsg(null); setWo(null);
    const [a, r] = await Promise.all([api(`/aircraft/${id}`), api(`/aircraft/${id}/records`)]);
    setD(a); setRecs(r);
  }
  async function submit(e) {
    e.preventDefault();
    const fd = new FormData();
    Object.entries(form).forEach(([k, v]) => fd.append(k, v));
    if (file) fd.append("photo", file);
    try { await upload(`/aircraft/${d.aircraft_id}/records`, fd); setForm(blank); setFile(null); e.target.reset(); setRecs(await api(`/aircraft/${d.aircraft_id}/records`)); setMsg({ ok: "Record saved." }); }
    catch (err) { setMsg({ err: err.message }); }
  }
  const list = ac.filter((a) => a.aircraft_id.toLowerCase().includes(q.toLowerCase()));

  return (
    <section className="split">
      <div>
        <h2>Aircraft</h2>
        <input className="search" placeholder="Search by tail number, e.g. AC-012" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search aircraft" />
        <ul className="ac-list">{list.map((a) => (
          <li key={a.aircraft_id}><button className={d?.aircraft_id === a.aircraft_id ? "on" : ""} onClick={() => open(a.aircraft_id)}>
            <b>{a.aircraft_id}</b><span>{a.base}</span>
            {a.status === "available" ? <i className="pill" style={{ background: BAND[a.risk_band] }}>{a.risk_band}</i> : <i className="pill grey">In maintenance</i>}
          </button></li>))}</ul>
      </div>
      <div>
        {!d ? <p className="empty">Choose an aircraft to see its sensor trends, maintenance history and photos, and to add a new record.</p> : (<>
          <h2>{d.aircraft_id} <small>{d.base}, {d.part_no}</small></h2>
          <p><b>{(d.risk_horizon * 100).toFixed(1)}%</b> chance of failure within 14 days. Remaining life {d.rul_p10}–{d.rul_p90} cycles (median {d.rul_p50}).</p>
          <h3>Sensor trend, last 60 cycles</h3>
          <div className="sparks">{SENS.map((_, i) => <Spark key={i} h={d.recent_history} i={i} />)}</div>
          <ul className="drv">{d.drivers.map((x) => <li key={x.sensor}>{x.note}</li>)}</ul>
          <button className="primary" onClick={async () => setWo(await api(`/aircraft/${d.aircraft_id}/workorder`))}>Draft work order</button>
          {wo && <div className="wo"><b>{wo.task}</b> ({wo.status})<br />{wo.reason}<br />Parts: {wo.parts.map((p) => `${p.qty} × ${p.part_no} (${p.in_stock} in stock, ${p.lead_days}-day lead time)`).join(", ")}<br />Skills: {wo.skills.join(", ")}. About {wo.estimated_hours} hours. {wo.planned_start_day != null ? `Planned start: day ${wo.planned_start_day}.` : "Run the Planner to get a start day."}</div>}

          <h3>Add a record or inspection photo</h3>
          <form className="rec-form" onSubmit={submit}>
            <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} aria-label="Record type">
              {["Snag report", "Scheduled inspection", "Unscheduled repair", "Part replacement"].map((t) => <option key={t}>{t}</option>)}</select>
            <input placeholder="Fault code (optional)" value={form.fault_code} onChange={(e) => setForm({ ...form, fault_code: e.target.value })} />
            <input type="number" min="0" step="0.5" placeholder="Hours" value={form.hours_spent} onChange={(e) => setForm({ ...form, hours_spent: e.target.value })} aria-label="Hours spent" />
            <textarea required placeholder="What was found or done?" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            <label className="file">Photo (JPEG, PNG or WebP, up to 5 MB)<input type="file" accept="image/*" onChange={(e) => setFile(e.target.files[0] || null)} /></label>
            {file && <img className="preview" src={URL.createObjectURL(file)} alt="Selected upload preview" />}
            <button className="primary">Save record</button>
            {msg?.ok && <span className="ok">{msg.ok}</span>}{msg?.err && <span className="bad" role="alert">{msg.err}</span>}
          </form>

          <h3>Maintenance history ({recs.length})</h3>
          {recs.map((r) => (
            <div className="rec" key={r.id}>
              <div><b>{r.date}</b> <span className="pill grey">{r.type}</span> {r.fault_code && <code>{r.fault_code}</code>} <span className="meta">{r.hours_spent} h, {r.source}</span></div>
              <p>{r.description}</p>
              {r.photo_url && <a href={ORIGIN + r.photo_url} target="_blank" rel="noreferrer"><img className="thumb" src={ORIGIN + r.photo_url} alt={`Inspection photo for ${r.type}`} /></a>}
            </div>))}
        </>)}
      </div>
    </section>
  );
}
