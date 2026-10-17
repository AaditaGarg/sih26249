import { useEffect, useState } from "react";
import { api, upload, BASE } from "./api";

function UploadCard({ kind, title, hint, onDone }) {
  const [f, setF] = useState(null), [rep, setRep] = useState(null), [err, setErr] = useState(null);
  async function go() {
    setErr(null); setRep(null);
    const fd = new FormData(); fd.append("file", f);
    try { setRep(await upload(`/ingest/${kind}`, fd)); onDone(); } catch (e) { setErr(e.message); }
  }
  return (
    <div className="up">
      <h3>{title}</h3><p className="meta">{hint}</p>
      <a href={`${BASE}/ingest/template/${kind}`}>Download CSV template</a>
      <input type="file" accept=".csv" onChange={(e) => setF(e.target.files[0] || null)} aria-label={`${title} CSV file`} />
      <button className="primary" disabled={!f} onClick={go}>Upload and check</button>
      {err && <p className="bad" role="alert">{err}</p>}
      {rep && <div className="rep"><b>{rep.accepted} of {rep.total} rows accepted</b> (data quality {(rep.quality_score * 100).toFixed(0)}%)
        {rep.errors.map((x) => <div key={x.row} className="bad">Row {x.row}: {x.error}</div>)}</div>}
    </div>
  );
}

export default function Data({ onChange }) {
  const [res, setRes] = useState(null), [audit, setAudit] = useState([]), [met, setMet] = useState(null);
  const refresh = () => { api("/resources").then(setRes); api("/audit").then(setAudit); api("/model/metrics").then(setMet); };
  useEffect(refresh, []);
  return (
    <section>
      <h2>Bring in your data</h2>
      <p className="meta">Maintenance records and spares usually sit in separate systems. Upload them here and the planner uses them straight away.</p>
      <div className="ups">
        <UploadCard kind="maintenance_records" title="Maintenance records" hint="Columns: aircraft_id, date (YYYY-MM-DD), type, fault_code, description, hours_spent." onDone={() => { refresh(); onChange(); }} />
        <UploadCard kind="spares" title="Spares inventory" hint="Columns: part_no, stock, lead_days, resupply_qty. Known parts only." onDone={() => { refresh(); onChange(); }} />
      </div>
      {res && (<><h3>Current resources</h3><div className="scroll"><table><thead><tr><th>Part</th><th>In stock</th><th>Lead time (days)</th><th>Resupply qty</th></tr></thead>
        <tbody>{Object.entries(res.spares).map(([p, v]) => <tr key={p}><td>{p}</td><td>{v.stock}</td><td>{v.lead_days}</td><td>{v.resupply_qty}</td></tr>)}</tbody></table></div>
        <p className="meta">{res.bays} maintenance bays, {res.tech_hours_per_day} technician hours per day.</p></>)}
      {met && <><h3>Model check on held-out engines</h3><p className="meta">{met.rmse_cycles} cycles RMSE, {(met.recall_rul_le_30 * 100).toFixed(0)}% recall within 30 cycles of failure, 80% range covers {(met.interval_coverage_80 * 100).toFixed(0)}%. Data: {met.data}.</p></>}
      <h3>Audit trail</h3>
      <div className="scroll"><table><thead><tr><th>Time</th><th>Who</th><th>Action</th><th>Detail</th></tr></thead>
        <tbody>{[...audit].reverse().slice(0, 25).map((a, i) => <tr key={i}><td>{a.ts.slice(0, 19).replace("T", " ")}</td><td>{a.actor}</td><td>{a.action}</td><td>{a.detail}</td></tr>)}</tbody></table></div>
    </section>
  );
}
