"use client";
import { useState } from "react";

export type Performance = {
  queue_backlog_requests: number;
  oldest_queued_seconds: number;
  estimated_deadline_risk_jobs: number;
  successful_jobs: number;
  successful_within_60_minutes: number;
  unsuccessful_terminal_jobs: number;
  deadline_attainment: number | null;
  sub_hour_attainment: number | null;
  estimates_calibrated: boolean;
  estimator_source: string;
  measurement_modes: string[];
  tokens_per_second_wall_clock_24h: number;
  end_to_end_seconds: { p50: number | null; p95: number | null; p99: number | null };
};
type Operations = {
  performance: Performance;
  capacity: {
    actual_warm_gpus: number;
    warm_worker_count: number;
    capacity_measurement_mode: string;
    required_gpus_estimate: number;
    recommended_start_count: number;
    recommended_stop_instance_ids: string[];
    blocked_by: string[];
  };
  economics: {
    estimated_cost_micro_usd: number;
    gross_margin: number | null;
    provider_invoiced_micro_usd: number | null;
    unattributed_successful_requests: number;
    instances: { instance_id: string; observed_active_seconds: number; observed_idle_seconds: number; unobserved_seconds: number }[];
  };
  workers: { id: string; mode: string; telemetry_fresh: boolean; gpu_utilization: number | null; dispatch_limit: number; hard_limit: number }[];
};
const seconds = (value: number | null) => value === null ? "No data" : value.toFixed(1) + "s";
const percentage = (value: number | null) => value === null ? "No data" : (value * 100).toFixed(1) + "%";

function Measures({ data }: { data: Performance }) {
  return <>
    <p>{data.measurement_modes.join(" / ") || "No execution observations"} · {data.estimator_source} · {data.estimates_calibrated ? "Operator-calibrated estimate" : "Uncalibrated estimate"}. No SLA.</p>
    <div className="stats">
      <section><small>Queued requests</small><strong>{data.queue_backlog_requests}</strong><p>Oldest: {seconds(data.oldest_queued_seconds)}</p></section>
      <section><small>Estimated deadline-risk jobs</small><strong>{data.estimated_deadline_risk_jobs}</strong><p>Includes capacity and backlog uncertainty.</p></section>
      <section><small>Successful jobs within 60 minutes</small><strong>{data.successful_within_60_minutes} / {data.successful_jobs}</strong><p>{percentage(data.sub_hour_attainment)} · {data.unsuccessful_terminal_jobs} unsuccessful terminal jobs excluded.</p></section>
    </div>
    <div className="scroll"><table><thead><tr><th>Successful job latency</th><th>p50</th><th>p95</th><th>p99</th><th>Requested target attainment</th></tr></thead>
      <tbody><tr><td>Acceptance → all requests terminal</td><td>{seconds(data.end_to_end_seconds.p50)}</td><td>{seconds(data.end_to_end_seconds.p95)}</td><td>{seconds(data.end_to_end_seconds.p99)}</td><td>{percentage(data.deadline_attainment)}</td></tr></tbody></table></div>
    <p>24-hour accepted-job window (plus older queued jobs). Input + output throughput: {data.tokens_per_second_wall_clock_24h.toFixed(3)} tokens/s averaged over 24 wall-clock hours. Mock counts use synthetic byte units.</p>
  </>;
}

export default function SchedulingPerformance({ data }: { data: Performance | null }) {
  const [token, setToken] = useState("");
  const [report, setReport] = useState<Operations | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function loadOperations() {
    setBusy(true); setError(""); setReport(null);
    try {
      const r = await fetch("/operations/report", { headers: { Authorization: "Bearer " + token }, cache: "no-store" });
      const body = await r.json();
      if (!r.ok) throw new Error(body.error?.message || "Operator report unavailable");
      setReport(body); setToken("");
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }
  return <section aria-labelledby="scheduling-title">
    <h2 id="scheduling-title">Scheduling and performance</h2>
    {data ? <Measures data={data} /> : <p>No performance data loaded.</p>}
    <details><summary>Operator capacity and economics</summary>
      <p>Requires the separate read-only metrics credential. Tenant credentials cannot access platform-wide data. The credential is used for one request, cleared on success, and never saved to browser storage.</p>
      <label>Metrics credential<input type="password" autoComplete="off" value={token} onChange={e => setToken(e.target.value)} /></label>
      <button disabled={busy || !token} onClick={loadOperations}>{busy ? "Loading…" : "Load operator report"}</button>
      <button onClick={() => { setToken(""); setReport(null); }}>Clear</button>
      {error && <p role="alert">{error}</p>}
      {report && <>
        <h3>Platform performance</h3><Measures data={report.performance} />
        <div className="stats">
          <section><small>{report.capacity.capacity_measurement_mode}: warm workers / GPU need estimate</small><strong>{report.capacity.warm_worker_count} / {report.capacity.required_gpus_estimate}</strong><p>{report.capacity.actual_warm_gpus} registered vLLM GPU workers. Recommend starting {report.capacity.recommended_start_count}. Recommendation only; operator approval required.</p></section>
          <section><small>Quoted GPU cost estimate</small><strong>{report.economics.instances.length ? "$" + (report.economics.estimated_cost_micro_usd / 1000000).toFixed(6) : "Not tracked"}</strong><p>Provider invoices recorded: {report.economics.provider_invoiced_micro_usd === null ? "None" : "$" + (report.economics.provider_invoiced_micro_usd / 1000000).toFixed(6)}</p></section>
          <section><small>Estimated attributable gross margin</small><strong>{percentage(report.economics.gross_margin)}</strong><p>{report.economics.unattributed_successful_requests} successful requests without tracked GPU cost attribution.</p></section>
        </div>
        <p>Start blocked by: {report.capacity.blocked_by.join(", ") || "No configured cap"}. Idle shutdown recommendations: {report.capacity.recommended_stop_instance_ids.join(", ") || "None"}.</p>
        <div className="scroll"><table><thead><tr><th>Worker</th><th>Mode</th><th>GPU utilization</th><th>Dispatch / hard cap</th></tr></thead><tbody>{report.workers.map(w => <tr key={w.id}><td>{w.id}</td><td>{w.mode}</td><td>{w.telemetry_fresh ? percentage(w.gpu_utilization) : "Stale / missing"}</td><td>{w.dispatch_limit} / {w.hard_limit}</td></tr>)}</tbody></table></div>
        <h3>Sampled active / idle time</h3><p>Heartbeat activity is a proxy, not GPU kernel timing. Missing coverage is reported as unknown.</p>
        {report.economics.instances.map(i => <p key={i.instance_id}>{i.instance_id}: active {seconds(i.observed_active_seconds)} · idle {seconds(i.observed_idle_seconds)} · unobserved {seconds(i.unobserved_seconds)}</p>)}
        <details><summary>Full cost, token and prediction report</summary><pre>{JSON.stringify(report, null, 2)}</pre></details>
      </>}
    </details>
  </section>;
}
