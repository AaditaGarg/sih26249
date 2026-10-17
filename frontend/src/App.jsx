import { useEffect, useState } from "react";
import { api } from "./api";

const BAND = { Critical: "#B83A24", High: "#E08A1E", Medium: "#C9AE3A", Low: "#6F8F72" };
const pct = (x) => (x * 100).toFixed(1) + "%";
const TABS = ["Fleet", "Maintenance queue", "Planner", "Simulator"];

function RulBar({ a }) {
  const S = 140, L = (v) => (v / S) * 100 + "%";
  return (
    <div className="rul" role="img" aria-label={`RUL ${a.rul_p10} to ${a.rul_p90} cycles, median ${a.rul_p50}`}>
      <div className="rul-band" style={{ left: L(a.rul_p10), width: L(a.rul_p90 - a.rul_p10) }} />
      <div className="rul-tick" style={{ left: L(a.rul_p50) }} title="Predicted median" />
      {a.true_rul_synthetic != null && <div className="rul-true" style={{ left: L(a.true_rul_synthetic) }} title="Hidden true RUL (synthetic)" />}
    </div>
  );
}

function Chart({ series, demand }) {
  const W = 680, H = 260, m = { l: 46, r: 12, t: 12, b: 28 };
  const n = series[0].d.days.length;
  const lo = Math.max(0, Math.floor((Math.min(...series.flatMap((s) => s.d.availability_p10)) - 0.03) * 50) / 50);
  const X = (i) => m.l + (i * (W - m.l - m.r)) / (n - 1), Y = (v) => m.t + ((1 - v) * (H - m.t - m.b)) / (1 - lo);
  const pts = (a) => a.map((v, i) => [X(i), Y(v)]);
  const str = (p) => p.map((q) => q.join(",")).join(" ");
  const ticks = [0, 1, 2, 3].map((k) => lo + ((1 - lo) * k) / 3);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Fleet availability over the planning horizon">
      {ticks.map((t) => (<g key={t}><line x1={m.l} x2={W - m.r} y1={Y(t)} y2={Y(t)} className="grid" /><text x={m.l - 6} y={Y(t) + 4} textAnchor="end" className="axis">{pct(t)}</text></g>))}
      {series.map((s) => (<g key={s.name}>
        <polygon points={str([...pts(s.d.availability_p90), ...pts(s.d.availability_p10).reverse()])} fill={s.color} opacity="0.16" />
        <polyline points={str(pts(s.d.availability_mean))} fill="none" stroke={s.color} strokeWidth="2.5" />
      </g>))}
      {demand != null && <g><line x1={m.l} x2={W - m.r} y1={Y(demand)} y2={Y(demand)} className="demand" /><text x={W - m.r} y={Y(demand) - 5} textAnchor="end" className="axis">minimum required</text></g>}
      {[0, Math.floor(n / 2), n - 1].map((i) => <text key={i} x={X(i)} y={H - 8} textAnchor="middle" className="axis">day {i}</text>)}
    </svg>
  );
}

export default function App() {
  const [tab, setTab] = useState(0);
  const [sum, setSum] = useState(null), [ac, setAc] = useState([]), [queue, setQueue] = useState([]), [met, setMet] = useState(null);
  const [sel, setSel] = useState(null), [plan, setPlan] = useState(null), [sim, setSim] = useState(null);
  const [P, setP] = useState({ bays: 3, spares: 1, minAvail: null });
  const [busy, setBusy] = useState("Training the RUL model on first launch…"), [err, setErr] = useState(null), [approved, setApproved] = useState({});
  const [fleetN, setFleetN] = useState(40), [seed, setSeed] = useState(42);

  async function load() {
    try {
      setErr(null);
      const [s, a, q, m] = await Promise.all([api("/fleet/summary"), api("/aircraft"), api("/maintenance/queue"), api("/model/metrics")]);
      setSum(s); setAc(a); setQueue(q); setMet(m);
      setP((p) => ({ ...p, minAvail: p.minAvail ?? Math.round(0.75 * s.total_aircraft) }));
    } catch (e) { setErr("Can't reach the backend at http://localhost:8000. Start it with: cd backend && uvicorn app.main:app --reload"); }
    setBusy(null);
  }
  useEffect(() => { load(); }, []);

  async function regenerate() {
    setBusy("Generating a new synthetic fleet…"); setPlan(null); setSim(null); setSel(null); setApproved({});
    try { await api("/fleet/generate", { n: fleetN, seed }); setP((p) => ({ ...p, minAvail: Math.round(0.75 * fleetN) })); await load(); } catch (e) { setErr(e.message); setBusy(null); }
  }
  const body = () => ({ bays: P.bays, spares_multiplier: P.spares, min_available: P.minAvail });
  async function runPlan() { setBusy("Solving the maintenance plan…"); try { setPlan(await api("/optimize", body())); setApproved({}); } catch (e) { setErr(e.message); } setBusy(null); }
  async function runSim() {
    setBusy("Running 200 simulated fortnights per policy…");
    try { const [r, p] = await Promise.all([api("/simulate", { ...body(), policy: "reactive" }), api("/simulate", { ...body(), policy: "planned" })]); setSim({ r, p }); } catch (e) { setErr(e.message); }
    setBusy(null);
  }
  async function pick(id) { setSel(await api(`/aircraft/${id}`)); }
  async function approve(id) { await api(`/recommendations/${id}/decision`, { decision: "approve", reason: "Approved from dashboard" }); setApproved((a) => ({ ...a, [id]: true })); }

  const controls = (
    <div className="controls">
      <label>Maintenance bays <b>{P.bays}</b><input type="range" min="1" max="6" value={P.bays} onChange={(e) => setP({ ...P, bays: +e.target.value })} /></label>
      <label>Spares stock ×<b>{P.spares}</b><input type="range" min="0" max="3" step="0.5" value={P.spares} onChange={(e) => setP({ ...P, spares: +e.target.value })} /></label>
      <label>Minimum aircraft available <b>{P.minAvail}</b><input type="range" min="0" max={sum?.total_aircraft || 40} value={P.minAvail ?? 0} onChange={(e) => setP({ ...P, minAvail: +e.target.value })} /></label>
    </div>
  );

  return (
    <div className="app">
      <header>
        <div><h1>SustainIQ</h1><p>Keep the most aircraft flying: predict wear, plan the work, test the outcome.</p></div>
        <span className="badge">Synthetic data only</span>
      </header>
      <nav role="tablist">{TABS.map((t, i) => <button key={t} role="tab" aria-selected={tab === i} onClick={() => setTab(i)}>{t}</button>)}</nav>
      {err && <div className="alert" role="alert">{err} <button onClick={() => { setBusy("Retrying…"); load(); }}>Retry</button></div>}
      {busy && <div className="busy" role="status">{busy}</div>}

      {sum && tab === 0 && (
        <section>
          <div className="hero">
            <div><span className="big">{sum.availability_now_pct}%</span><span className="lbl">available now ({sum.available_now} of {sum.total_aircraft})</span></div>
            <div><span className="big warn">{sum.reactive_availability_forecast_pct}%</span><span className="lbl">expected in 14 days if we only react ({sum.expected_unplanned_failures_next_14d} likely failures)</span></div>
            <div className="regen">
              <label>Aircraft<input type="number" min="5" max="300" value={fleetN} onChange={(e) => setFleetN(+e.target.value)} /></label>
              <label>Seed<input type="number" value={seed} onChange={(e) => setSeed(+e.target.value)} /></label>
              <button onClick={regenerate}>Generate new fleet</button>
            </div>
          </div>
          <div className="layout">
            <div>
              <h2>Flight line</h2>
              <div className="legend">{Object.entries(BAND).map(([k, c]) => <span key={k}><i style={{ background: c }} />{k} risk</span>)}<span><i className="hatch" />In maintenance</span></div>
              <div className="tiles">{ac.map((a) => (
                <button key={a.aircraft_id} className={"tile" + (a.status !== "available" ? " down" : "") + (sel?.aircraft_id === a.aircraft_id ? " on" : "")}
                  style={a.status === "available" ? { background: BAND[a.risk_band] } : undefined} onClick={() => pick(a.aircraft_id)}
                  aria-label={`${a.aircraft_id}, ${a.status === "available" ? a.risk_band + " risk" : "in maintenance"}`}>
                  {a.aircraft_id.slice(3)}
                </button>))}</div>
            </div>
            <aside className="detail">
              {!sel ? <p className="empty">Select an aircraft to see its remaining useful life and the sensors driving the prediction.</p> : (<>
                <h2>{sel.aircraft_id}</h2>
                <p className="meta">{sel.base}, part {sel.part_no}, {sel.cycles} cycles flown</p>
                <p><b>{pct(sel.risk_horizon)}</b> chance of failure within 14 days ({sel.risk_band})</p>
                <RulBar a={sel} />
                <p className="meta">Remaining life: {sel.rul_p10}–{sel.rul_p90} cycles (median {sel.rul_p50}). The dark line marks the hidden true value, available because the data is synthetic.</p>
                <h3>Why the model thinks so</h3>
                <ul>{sel.drivers.map((d) => <li key={d.sensor}>{d.note}</li>)}</ul>
              </>)}
            </aside>
          </div>
          {met && <p className="foot">Held-out model check: {met.rmse_cycles} cycles RMSE, {pct(met.recall_rul_le_30)} of aircraft within 30 cycles of failure flagged, 80% range covers {pct(met.interval_coverage_80)} of true values.</p>}
        </section>
      )}

      {sum && tab === 1 && (
        <section>
          <h2>Aircraft to service, highest risk first</h2>
          {queue.length === 0 ? <p className="empty">No aircraft are above low risk. Generate a new fleet from the Fleet tab.</p> : (
            <div className="scroll"><table><thead><tr><th>Aircraft</th><th>Risk</th><th>14-day failure chance</th><th>Remaining life (cycles)</th><th>Spare</th><th>Main driver</th></tr></thead>
              <tbody>{queue.map((r) => (<tr key={r.aircraft_id}>
                <td><b>{r.aircraft_id}</b></td><td><span className="pill" style={{ background: BAND[r.risk_band] }}>{r.risk_band}</span></td><td>{pct(r.risk_horizon)}</td>
                <td>{r.rul_p10}–{r.rul_p90} (median {r.rul_p50})</td>
                <td>{r.spare_in_stock ? `${r.part_no} in stock` : `${r.part_no} arrives in ${r.spare_lead_days} days`}</td><td>{r.top_driver}</td></tr>))}</tbody></table></div>)}
        </section>
      )}

      {sum && tab === 2 && (
        <section>
          <h2>Maintenance plan for the next 14 days</h2>
          {controls}
          <button className="primary" onClick={runPlan}>Build plan</button>
          {!plan ? <p className="empty">Set the resources you have, then build a plan. Try fewer bays or spares and watch the plan change.</p> : (<>
            <div className="cards">
              <div><span className="big">{plan.objective.expected_aircraft_days_lost_plan}</span><span className="lbl">aircraft-days lost with this plan</span></div>
              <div><span className="big warn">{plan.objective.expected_aircraft_days_lost_reactive}</span><span className="lbl">if we wait for failures</span></div>
              <div><span className="big">{plan.objective.expected_aircraft_days_lost_greedy_risk_ranked}</span><span className="lbl">if we just fix riskiest first</span></div>
            </div>
            {plan.bottlenecks.length > 0 && <p className="alert soft">Limiting resources: {plan.bottlenecks.map((b) => `${b.resource} (${b.used}/${b.capacity})`).join(", ")}</p>}
            {plan.plan.map((r) => (
              <div className="job" key={r.aircraft_id}>
                <div className="job-h"><b>{r.aircraft_id}</b><span>{r.part_no}</span><span>{pct(r.risk_horizon)} risk</span>
                  <button disabled={approved[r.aircraft_id]} onClick={() => approve(r.aircraft_id)}>{approved[r.aircraft_id] ? "Approved" : "Approve"}</button></div>
                <div className="gantt">{Array.from({ length: plan.horizon_days }, (_, d) => <i key={d} className={d >= r.start_day && d < r.start_day + r.duration_days ? "in" : ""} />)}</div>
                <p className="meta">Start day {r.start_day}. {r.reason}</p>
              </div>))}
            {plan.deferred.length > 0 && <p className="meta">Deferred and monitored: {plan.deferred.map((d) => d.aircraft_id).join(", ")}</p>}
            {plan.plan.length === 0 && plan.deferred.length === 0 && <p className="empty">No aircraft need planned work in this horizon.</p>}
          </>)}
        </section>
      )}

      {sum && tab === 3 && (
        <section>
          <h2>What happens if we follow the plan?</h2>
          {controls}
          <button className="primary" onClick={runSim}>Run simulation</button>
          {!sim ? <p className="empty">Compare reacting to failures against following the plan, across many random futures.</p> : (<>
            <div className="legend"><span><i style={{ background: "#B83A24" }} />React to failures</span><span><i style={{ background: "#2F5D7C" }} />Follow the plan</span><span>Shaded band: 10th to 90th percentile</span></div>
            <Chart series={[{ name: "r", d: sim.r, color: "#B83A24" }, { name: "p", d: sim.p, color: "#2F5D7C" }]} demand={P.minAvail / sum.total_aircraft} />
            <div className="cards">
              <div><span className="big">{pct(sim.p.mean_availability)}</span><span className="lbl">average availability, planned</span></div>
              <div><span className="big warn">{pct(sim.r.mean_availability)}</span><span className="lbl">average availability, reactive</span></div>
              <div><span className="big">{pct(sim.p.prob_demand_met_every_day)}</span><span className="lbl">of futures meet the minimum every day (planned); reactive {pct(sim.r.prob_demand_met_every_day)}</span></div>
            </div>
          </>)}
        </section>
      )}
    </div>
  );
}
