import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import PilotWorkspace from "../components/PilotWorkspace";
import { AIBanner, Badge, Button, Disclaimer, Empty, Field, Loading, Page, Stat, useLoad } from "../components/ui";
import { api, inr } from "../services/api";
import { useToast } from "../context/AppState";

export function ProcDashboard() {
  const pilots = useLoad(() => api("/pilots/"));
  const apps = useLoad(() => api("/applications/?status=APPROVED_FOR_PILOT"));
  const complaints = useLoad(() => api("/complaints/"));
  if (pilots.loading) return <Loading />;
  const rows = pilots.data || [];
  return (
    <Page kicker="Procurement officer" title="Pilot desk" lede="Contracts, KPIs and recommendations are prepared here. Nothing on this desk is an automatic award.">
      <div className="grid-4">
        <Stat value={rows.filter((p) => p.status === "ACTIVE").length} label="Active pilots" />
        <Stat value={rows.filter((p) => p.status === "COMPLETED").length} label="Completed pilots" />
        <Stat value={rows.filter((p) => p.status === "CONTRACT_PENDING" || p.status === "DRAFT").length} label="Awaiting contract action" />
        <Stat value={(complaints.data || []).filter((c) => !["CLOSED", "ACCEPTED"].includes(c.status)).length} label="Open complaints" />
      </div>
      <section className="card card-pad stack">
        <h3>Approved, awaiting a pilot contract</h3>
        {(apps.data || []).length === 0 && <div className="small">No approved application is waiting.</div>}
        {(apps.data || []).map((app) => (
          <div key={app.id} className="card-title">
            <span>{app.startup?.company_name} · {app.problem?.title}</span>
            <CreatePilot application={app.id} />
          </div>
        ))}
      </section>
      <PilotTable rows={rows} />
    </Page>
  );
}

function CreatePilot({ application }) {
  const toast = useToast();
  const navigate = useNavigate();
  return (
    <Button variant="gold" onClick={async () => {
      try {
        const pilot = await api("/pilots/", { method: "POST", body: { application } });
        toast.push("Draft pilot created");
        navigate(`/procurement/pilots/${pilot.id}/contract`);
      } catch (error) { toast.push(error.message, "bad"); }
    }}>Create pilot</Button>
  );
}

function PilotTable({ rows }) {
  return (
    <div className="card table-wrap">
      <table className="data">
        <thead><tr><th>Pilot</th><th>Startup</th><th>Problem</th><th>Status</th><th>Score</th></tr></thead>
        <tbody>
          {rows.map((pilot) => (
            <tr key={pilot.id}>
              <td><Link to={`/procurement/pilots/${pilot.id}`}>{pilot.code}</Link></td>
              <td>{pilot.startup?.company_name}</td>
              <td>{pilot.problem?.title}</td>
              <td><Badge value={pilot.status} /></td>
              <td>{pilot.score?.overall ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ProcPilots() {
  const state = useLoad(() => api("/pilots/"));
  if (state.loading) return <Loading />;
  return <Page kicker="Register" title="Pilots"><PilotTable rows={state.data || []} /></Page>;
}

export function ProcPilotDetail() {
  const { id } = useParams();
  const state = useLoad(() => api(`/pilots/${id}/`), [id]);
  if (state.loading) return <Loading />;
  return <PilotWorkspace pilot={state.data} reload={state.reload} mode="procurement" />;
}

const BLANK_KPI = { name: "", target: "", unit: "percent", weight: "", priority: "MUST_HAVE", direction: "HIGHER_IS_BETTER", max_score: 120 };

export function ProcContract() {
  const { id } = useParams();
  const state = useLoad(() => api(`/pilots/${id}/`), [id]);
  const people = useLoad(() => api("/employees/"));
  const toast = useToast();
  const [form, setForm] = useState(null);
  const pilot = state.data;
  if (state.loading || people.loading) return <Loading />;
  if (!pilot) return <Empty>Pilot not found.</Empty>;
  const draft = form || {
    location: pilot.location || "",
    start_date: pilot.start_date || "",
    end_date: pilot.end_date || "",
    joining_deadline: pilot.joining_deadline || "",
    duration_weeks: pilot.duration_weeks || 8,
    responsibilities: pilot.responsibilities || "",
    government_support: pilot.government_support || "",
    payment_conditions: pilot.payment_conditions || "",
    security_requirements: pilot.security_requirements || "",
    reporting_frequency: pilot.reporting_frequency || "Weekly",
    field_evaluator: pilot.field_evaluator?.id || "",
    kpi_method: pilot.contract?.kpi_method || "MANUAL",
    kpis: pilot.kpis?.length ? pilot.kpis : [{ ...BLANK_KPI, name: "Accuracy", target: 90, weight: 40 }, { ...BLANK_KPI, name: "Response Time", target: 2, unit: "seconds", weight: 20, direction: "LOWER_IS_BETTER", priority: "BETTER_TO_HAVE" }, { ...BLANK_KPI, name: "Uptime", target: 99, weight: 25 }, { ...BLANK_KPI, name: "Adoption", target: 80, weight: 15, priority: "NICE_TO_HAVE" }],
    milestones: pilot.milestones?.length ? pilot.milestones : [
      { name: "Prototype Ready", amount: 150000, due_week: 2, status: "PENDING" },
      { name: "Integration Complete", amount: 150000, due_week: 4, status: "PENDING" },
      { name: "Pilot Complete", amount: 200000, due_week: 8, status: "PENDING" },
      { name: "Validation Complete", amount: 100000, due_week: 10, status: "PENDING" },
    ],
  };
  const set = (patch) => setForm({ ...draft, ...patch });
  const weight = draft.kpis.reduce((sum, kpi) => sum + Number(kpi.weight || 0), 0);

  async function save(send = false) {
    try {
      await api(`/pilots/${pilot.id}/`, { method: "PATCH", body: { ...draft, field_evaluator: draft.field_evaluator || null, milestones: draft.milestones } });
      if (draft.kpi_method === "MANUAL") {
        await api(`/pilots/${pilot.id}/kpis/`, { method: "POST", body: { kpis: draft.kpis, source: "MANUAL", finalize: true } });
      }
      if (send) await api(`/pilots/${pilot.id}/send-contract/`, { method: "POST", body: {} });
      toast.push(send ? "Contract sent to the startup" : "Contract draft saved");
      setForm(null);
      state.reload();
    } catch (error) { toast.push(error.message, "bad"); }
  }

  return (
    <Page kicker={pilot.code} title="Pilot contract and KPIs" lede="Manual KPI entry is the secure option: the contract is not mined for KPIs. Extraction, if chosen, runs only after signature and still needs your review." actions={<Button to={`/procurement/pilots/${pilot.id}`} variant="ghost">Back to pilot</Button>}>
      <div className="card card-pad grid-2">
        <Field label="Location"><input value={draft.location} onChange={(e) => set({ location: e.target.value })} /></Field>
        <Field label="Field evaluator">
          <select value={draft.field_evaluator} onChange={(e) => set({ field_evaluator: e.target.value })}>
            <option value="">Select</option>
            {(people.data || []).filter((p) => p.role === "FIELD_EVALUATOR").map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </Field>
        <Field label="Start"><input type="date" value={draft.start_date || ""} onChange={(e) => set({ start_date: e.target.value })} /></Field>
        <Field label="End"><input type="date" value={draft.end_date || ""} onChange={(e) => set({ end_date: e.target.value })} /></Field>
        <Field label="Joining deadline"><input type="date" value={draft.joining_deadline || ""} onChange={(e) => set({ joining_deadline: e.target.value })} /></Field>
        <Field label="Duration weeks"><input type="number" value={draft.duration_weeks} onChange={(e) => set({ duration_weeks: Number(e.target.value) })} /></Field>
        <Field label="Responsibilities"><textarea value={draft.responsibilities} onChange={(e) => set({ responsibilities: e.target.value })} /></Field>
        <Field label="Government support"><textarea value={draft.government_support} onChange={(e) => set({ government_support: e.target.value })} /></Field>
        <Field label="Payment conditions"><textarea value={draft.payment_conditions} onChange={(e) => set({ payment_conditions: e.target.value })} /></Field>
        <Field label="Security requirements"><textarea value={draft.security_requirements} onChange={(e) => set({ security_requirements: e.target.value })} /></Field>
      </div>
      <section className="card card-pad stack">
        <div className="card-title"><h3>Milestones</h3></div>
        {draft.milestones.map((item, index) => (
          <div key={index} className="grid-4">
            <input value={item.name} onChange={(e) => set({ milestones: draft.milestones.map((m, i) => i === index ? { ...m, name: e.target.value } : m) })} />
            <input type="number" value={item.amount} onChange={(e) => set({ milestones: draft.milestones.map((m, i) => i === index ? { ...m, amount: Number(e.target.value) } : m) })} />
            <input type="number" value={item.due_week} onChange={(e) => set({ milestones: draft.milestones.map((m, i) => i === index ? { ...m, due_week: Number(e.target.value) } : m) })} />
            <select value={item.status} onChange={(e) => set({ milestones: draft.milestones.map((m, i) => i === index ? { ...m, status: e.target.value } : m) })}>
              <option>PENDING</option><option>COMPLETE</option><option>DELAYED</option>
            </select>
          </div>
        ))}
        <div className="small">Amounts in INR. Example row total {inr(draft.milestones.reduce((s, m) => s + Number(m.amount || 0), 0))}.</div>
      </section>
      <section className="card card-pad stack" id="kpis">
        <div className="card-title">
          <h3>Required KPI</h3>
          <Badge value={weight === 100 ? "VERIFIED_VALID" : "EXPIRING_SOON"} />
        </div>
        <Field label="Configuration method">
          <select value={draft.kpi_method} onChange={(e) => set({ kpi_method: e.target.value })}>
            <option value="MANUAL">Manual KPI entry — do not read the contract for KPIs</option>
            <option value="EXTRACT">Extract KPIs from the signed contract, then review</option>
          </select>
        </Field>
        {draft.kpi_method === "MANUAL" && draft.kpis.map((kpi, index) => (
          <div key={index} className="grid-4">
            <input placeholder="Name" value={kpi.name} onChange={(e) => set({ kpis: draft.kpis.map((k, i) => i === index ? { ...k, name: e.target.value } : k) })} />
            <input placeholder="Target" type="number" value={kpi.target} onChange={(e) => set({ kpis: draft.kpis.map((k, i) => i === index ? { ...k, target: Number(e.target.value) } : k) })} />
            <input placeholder="Unit" value={kpi.unit} onChange={(e) => set({ kpis: draft.kpis.map((k, i) => i === index ? { ...k, unit: e.target.value } : k) })} />
            <input placeholder="Weight %" type="number" value={kpi.weight} onChange={(e) => set({ kpis: draft.kpis.map((k, i) => i === index ? { ...k, weight: Number(e.target.value) } : k) })} />
            <select value={kpi.priority} onChange={(e) => set({ kpis: draft.kpis.map((k, i) => i === index ? { ...k, priority: e.target.value } : k) })}>
              <option value="MUST_HAVE">MUST HAVE</option>
              <option value="BETTER_TO_HAVE">BETTER TO HAVE</option>
              <option value="NICE_TO_HAVE">NICE TO HAVE</option>
            </select>
            <select value={kpi.direction} onChange={(e) => set({ kpis: draft.kpis.map((k, i) => i === index ? { ...k, direction: e.target.value } : k) })}>
              <option value="HIGHER_IS_BETTER">Higher is better</option>
              <option value="LOWER_IS_BETTER">Lower is better</option>
            </select>
            <input type="number" value={kpi.max_score} onChange={(e) => set({ kpis: draft.kpis.map((k, i) => i === index ? { ...k, max_score: Number(e.target.value) } : k) })} />
            <Button variant="ghost" onClick={() => set({ kpis: draft.kpis.filter((_, i) => i !== index) })}>Remove</Button>
          </div>
        ))}
        {draft.kpi_method === "MANUAL" && <Button variant="ghost" onClick={() => set({ kpis: [...draft.kpis, { ...BLANK_KPI }] })}>Add KPI</Button>}
        <div className={weight === 100 ? "small" : "demo-banner"}>Weight total {weight}%. Weights must total 100% before a manual contract is sent.</div>
        {pilot.contract?.extracted_kpis?.length > 0 && (
          <div className="demo-banner">Extracted, not yet official: {JSON.stringify(pilot.contract.extracted_kpis)}</div>
        )}
      </section>
      <div className="page-actions">
        <Button variant="ghost" onClick={() => save(false)}>Save draft</Button>
        <Button variant="gold" onClick={() => save(true)}>Send contract to startup</Button>
        {pilot.contract?.kpi_method === "EXTRACT" && (
          <Button onClick={async () => {
            try {
              await api(`/pilots/${pilot.id}/confirm-extracted-kpis/`, { method: "POST", body: { kpis: draft.kpis, start: true } });
              toast.push("Extracted KPIs confirmed and pilot started");
              state.reload();
            } catch (error) { toast.push(error.message, "bad"); }
          }}>Confirm extracted KPIs and start</Button>
        )}
      </div>
    </Page>
  );
}

export function ProcKpis() {
  return <ProcContract />;
}

export function ProcComplaints() {
  const { id } = useParams();
  const state = useLoad(() => api(id ? `/pilots/${id}/` : "/complaints/"), [id]);
  if (state.loading) return <Loading />;
  if (id) return <PilotWorkspace pilot={state.data} reload={state.reload} mode="procurement" />;
  return (
    <Page kicker="Complaints" title="Pilot complaints">
      {(state.data || []).map((item) => (
        <article key={item.id} className="card card-pad">
          <div className="card-title"><b>{item.category}</b><Badge value={item.status} /></div>
          <div>{item.startup} · {item.problem}</div>
          <p>{item.description}</p>
          <Link to={`/procurement/pilots/${item.pilot_id}/complaints`}>Open pilot</Link>
        </article>
      ))}
    </Page>
  );
}

const CHOICES = [
  ["CONSIDER_PROCUREMENT", "Consider Procurement"],
  ["CONSIDER_SCALEUP", "Consider Scale-up"],
  ["ADDITIONAL_PILOT", "Request Additional Pilot"],
  ["CLARIFICATION", "Request Clarification"],
  ["DO_NOT_RECOMMEND", "Do Not Recommend"],
];

export function ProcRecommendations() {
  const board = useLoad(() => api("/leaderboard/"));
  const recs = useLoad(() => api("/recommendations/"));
  const pilots = useLoad(() => api("/pilots/?status=COMPLETED"));
  const toast = useToast();
  const [pilotId, setPilotId] = useState("");
  const [choice, setChoice] = useState("CONSIDER_SCALEUP");
  const [note, setNote] = useState("");
  const [report, setReport] = useState(null);

  return (
    <Page kicker="Decision support" title="Leaderboard and recommendations" lede="Position on the leaderboard does not award procurement.">
      <AIBanner>
        <span> Final award rests with the competent government authority.</span>
      </AIBanner>
      {board.loading ? <Loading /> : (
        <div className="card table-wrap">
          <table className="data">
            <thead><tr><th>Rank</th><th>Startup</th><th>Problem</th><th>Score</th><th>Status</th></tr></thead>
            <tbody>
              {(board.data || []).map((row) => (
                <tr key={row.pilot_id}>
                  <td>{row.rank}</td>
                  <td><Link to={`/procurement/pilots/${row.pilot_id}`}>{row.startup}</Link></td>
                  <td>{row.problem}</td>
                  <td>{row.score}</td>
                  <td>{row.label}{row.must_have_failures?.length ? ` · MUST HAVE: ${row.must_have_failures.join(", ")}` : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <section className="card card-pad stack">
        <h3>Record a recommendation</h3>
        <Field label="Completed pilot">
          <select value={pilotId} onChange={(e) => setPilotId(e.target.value)}>
            <option value="">Select</option>
            {(pilots.data || []).map((pilot) => <option key={pilot.id} value={pilot.id}>{pilot.startup?.company_name} · {pilot.problem?.title}</option>)}
          </select>
        </Field>
        <Field label="Choice for authority review">
          <select value={choice} onChange={(e) => setChoice(e.target.value)}>
            {CHOICES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </Field>
        <Field label="Officer note"><textarea value={note} onChange={(e) => setNote(e.target.value)} /></Field>
        <div className="page-actions">
          <Button onClick={async () => {
            if (!pilotId) return toast.push("Select a pilot", "bad");
            try {
              const saved = await api(`/pilots/${pilotId}/recommendation/`, { method: "POST", body: { choice, officer_note: note, regenerate: true, include_report: true } });
              setReport(saved);
              toast.push("Recommendation recorded for government review");
              recs.reload();
            } catch (error) { toast.push(error.message, "bad"); }
          }}>Generate insights and record</Button>
        </div>
        {report && (
          <article className="stack">
            <AIBanner demo={report.ai_demo} notice={report.ai_notice}>
              <div><b>{report.choice_label}</b></div>
              <ul>{(report.scaleup_tips?.recommended_focus || []).map((item) => <li key={item}>{item}</li>)}</ul>
              <ul>{(report.scaleup_tips?.scaleup_considerations || []).map((item) => <li key={item}>{item}</li>)}</ul>
            </AIBanner>
            {report.evidence_report && (
              <div className="card card-pad">
                <h3>Evidence-based report</h3>
                <pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit" }}>{report.evidence_report}</pre>
                <div className="small">Evidence links: {(report.evidence_links || []).map((link) => `${link.claim} → ${link.source}`).join(" · ")}</div>
              </div>
            )}
          </article>
        )}
        <Disclaimer />
      </section>
      <section className="stack">
        {(recs.data || []).map((rec) => (
          <article key={rec.id} className="card card-pad">
            <div className="card-title"><b>{rec.startup}</b><Badge value={rec.choice} /></div>
            <div className="small">{rec.problem} · score {rec.score?.overall ?? "—"} {rec.score?.label || ""}</div>
            <p>{rec.officer_note || rec.narrative}</p>
            <Link to={`/procurement/pilots/${rec.pilot_id}`}>Open pilot file</Link>
          </article>
        ))}
      </section>
    </Page>
  );
}
