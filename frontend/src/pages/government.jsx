import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Badge, Button, Empty, ErrorNote, Field, Loading, Page, Stat, useLoad } from "../components/ui";
import { api, labelize } from "../services/api";
import { useToast } from "../context/AppState";

export function GovDashboard() {
  const dash = useLoad(() => api("/dashboard/"));
  const alerts = useLoad(() => api("/alerts/"));
  if (dash.loading) return <Loading />;
  const data = dash.data || {};
  return (
    <Page kicker="Government administrator" title="Cell dashboard" lede="Live figures from this demonstration workspace. The public landing keeps a separate illustrative snapshot." actions={<Button to="/government/problem-statements/create" variant="gold">New problem statement</Button>}>
      <ErrorNote error={dash.error} />
      <div className="card card-pad">
        <div className="kicker">Illustrative cell snapshot</div>
        <div className="grid-4" style={{ marginTop: 10 }}>
          <Stat value="8" label="Problem statements" />
          <Stat value="42" label="Applications" />
          <Stat value="5" label="Active pilots" />
          <Stat value="11" label="Pending evaluations" />
        </div>
        <p className="small">These are the illustrative programme figures. The cards below are live counts from this demonstration workspace, which also holds completed, cancelled and open files.</p>
      </div>
      <div className="grid-4">
        <Stat value={data.problem_statements ?? "—"} label="Workspace problem statements" />
        <Stat value={data.applications ?? "—"} label="Applications" />
        <Stat value={data.active_pilots ?? "—"} label="Active pilots" />
        <Stat value={data.pending_evaluations ?? "—"} label="Pending evaluations" />
      </div>
      <div className="grid-4">
        <Stat value={data.startups ?? "—"} label="Startups" />
        <Stat value={data.expiring_documents ?? "—"} label="Documents expiring soon" />
        <Stat value={data.open_complaints ?? "—"} label="Open complaints" />
        <Stat value={data.completed_pilots ?? "—"} label="Completed pilots" />
      </div>
      <div className="grid-2">
        <ChartCard title="Applications by stage" rows={data.applications_by_status} />
        <ChartCard title="Problem statements by status" rows={data.problems_by_status} />
      </div>
      <section className="card card-pad stack">
        <div className="card-title"><h3>Alerts</h3><Button to="/government/alerts" variant="ghost">Open alerts</Button></div>
        {(alerts.data || []).slice(0, 4).map((alert, index) => (
          <div key={index}>
            <b>{alert.title}</b>
            <div className="small">{alert.entity} — {alert.body}</div>
          </div>
        ))}
      </section>
    </Page>
  );
}

function ChartCard({ title, rows = [] }) {
  const data = rows.map((row) => ({ name: labelize(row.status), count: row.count }));
  return (
    <section className="card card-pad">
      <h3>{title}</h3>
      <div style={{ height: 240 }}>
        <ResponsiveContainer>
          <BarChart data={data}>
            <CartesianGrid stroke="#e6e1d6" />
            <XAxis dataKey="name" hide />
            <YAxis allowDecimals={false} />
            <Tooltip />
            <Bar dataKey="count" fill="#0b1f3a" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="small">{data.map((row) => `${row.name} ${row.count}`).join(" · ")}</div>
    </section>
  );
}

export function GovProblems() {
  const state = useLoad(() => api("/problem-statements/"));
  if (state.loading) return <Loading />;
  return (
    <Page kicker="Register" title="Problem statements" actions={<Button to="/government/problem-statements/create" variant="gold">Create</Button>}>
      <div className="card table-wrap">
        <table className="data">
          <thead><tr><th>Code</th><th>Title</th><th>Department</th><th>Status</th><th>Applications</th><th>Deadline</th></tr></thead>
          <tbody>
            {(state.data || []).map((ps) => (
              <tr key={ps.id}>
                <td><Link to={`/government/problem-statements/${ps.id}`}>{ps.code}</Link></td>
                <td>{ps.title}</td>
                <td>{ps.department?.name}</td>
                <td><Badge value={ps.status} /></td>
                <td>{ps.application_count}</td>
                <td>{ps.application_deadline}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Page>
  );
}

export function GovProblemCreate() {
  const toast = useToast();
  const navigate = useNavigate();
  const meta = useLoad(() => api("/meta/"));
  const people = useLoad(() => api("/employees/"));
  const [form, setForm] = useState({
    title: "", description: "", department_id: "", location: "", technology_domain: "", expected_outcome: "",
    technical_requirements: "", eligibility_criteria: "DPIIT-recognised startup\nValid GST registration",
    required_documents: "DPIIT\nGST\nPAN\nINCORPORATION\nTECHNICAL_PROPOSAL",
    application_deadline: "2026-11-15", pilot_joining_deadline: "2026-12-01", pilot_location: "", pilot_duration_weeks: 8,
    technical_evaluator: "", procurement_officer: "",
  });
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });
  if (meta.loading || people.loading) return <Loading />;
  return (
    <Page kicker="New file" title="Create a problem statement" lede="Saving generates a 384-dimensional embedding for startup matching.">
      <form className="card card-pad grid-2" onSubmit={async (e) => {
        e.preventDefault();
        try {
          const created = await api("/problem-statements/", { method: "POST", body: { ...form, department_id: Number(form.department_id), technical_evaluator: form.technical_evaluator || null, procurement_officer: form.procurement_officer || null } });
          toast.push("Problem statement published and embedded");
          navigate(`/government/problem-statements/${created.id}`);
        } catch (error) { toast.push(error.message, "bad"); }
      }}>
        <Field label="Title"><input value={form.title} onChange={set("title")} required /></Field>
        <Field label="Department">
          <select value={form.department_id} onChange={set("department_id")} required>
            <option value="">Select</option>
            {(meta.data?.departments || []).map((dep) => <option key={dep.id} value={dep.id}>{dep.name}</option>)}
          </select>
        </Field>
        <Field label="Location"><input value={form.location} onChange={set("location")} required /></Field>
        <Field label="Technology domain"><input value={form.technology_domain} onChange={set("technology_domain")} required /></Field>
        <Field label="Description"><textarea value={form.description} onChange={set("description")} required /></Field>
        <Field label="Expected outcome"><textarea value={form.expected_outcome} onChange={set("expected_outcome")} required /></Field>
        <Field label="Technical requirements" hint="One item per line"><textarea value={form.technical_requirements} onChange={set("technical_requirements")} /></Field>
        <Field label="Eligibility criteria" hint="One item per line"><textarea value={form.eligibility_criteria} onChange={set("eligibility_criteria")} /></Field>
        <Field label="Required documents" hint="One type per line"><textarea value={form.required_documents} onChange={set("required_documents")} /></Field>
        <Field label="Pilot location"><input value={form.pilot_location} onChange={set("pilot_location")} required /></Field>
        <Field label="Application deadline"><input type="date" value={form.application_deadline} onChange={set("application_deadline")} required /></Field>
        <Field label="Pilot joining deadline"><input type="date" value={form.pilot_joining_deadline} onChange={set("pilot_joining_deadline")} required /></Field>
        <Field label="Pilot duration (weeks)"><input type="number" value={form.pilot_duration_weeks} onChange={set("pilot_duration_weeks")} /></Field>
        <Field label="Technical evaluator">
          <select value={form.technical_evaluator} onChange={set("technical_evaluator")}>
            <option value="">Assign later</option>
            {(people.data || []).filter((p) => p.role === "TECHNICAL_EVALUATOR").map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </Field>
        <Field label="Procurement officer">
          <select value={form.procurement_officer} onChange={set("procurement_officer")}>
            <option value="">Assign later</option>
            {(people.data || []).filter((p) => p.role === "PROCUREMENT_OFFICER").map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </Field>
        <Button type="submit" variant="gold">Publish problem statement</Button>
      </form>
    </Page>
  );
}

export function GovProblemDetail() {
  const { id } = useParams();
  const state = useLoad(() => api(`/problem-statements/${id}/`), [id]);
  const people = useLoad(() => api("/employees/"));
  const toast = useToast();
  if (state.loading) return <Loading />;
  if (state.error) return <ErrorNote error={state.error} />;
  const ps = state.data;
  return (
    <Page kicker={ps.code} title={ps.title} lede={ps.description} actions={<Badge value={ps.status} />}>
      <div className="grid-2">
        <article className="card card-pad stack">
          <div>{ps.department?.name} · {ps.location} · {ps.technology_domain}</div>
          <p>{ps.expected_outcome}</p>
          <div className="small">Deadline {ps.application_deadline} · Join by {ps.pilot_joining_deadline} · {ps.pilot_location}</div>
          <h3>Requirements</h3>
          <ul>{ps.technical_requirements.map((item) => <li key={item}>{item}</li>)}</ul>
        </article>
        <article className="card card-pad stack">
          <h3>Assignments</h3>
          <div className="small">Evaluator: {ps.technical_evaluator?.name || "Unassigned"}</div>
          <div className="small">Procurement: {ps.procurement_officer?.name || "Unassigned"}</div>
          <Field label="Reassign evaluator">
            <select defaultValue={ps.technical_evaluator?.id || ""} onChange={async (e) => {
              await api(`/problem-statements/${ps.id}/assign/`, { method: "POST", body: { technical_evaluator: e.target.value || null } });
              toast.push("Evaluator assigned");
              state.reload();
            }}>
              <option value="">Unassigned</option>
              {(people.data || []).filter((p) => p.role === "TECHNICAL_EVALUATOR").map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </Field>
          <h3>Similar startups</h3>
          {(ps.similar_startups || []).map((row) => (
            <div key={row.startup.id} className="small">{row.startup.company_name} · match {row.match.score}% · {row.match.reasons?.[0]}</div>
          ))}
        </article>
      </div>
      <div className="card table-wrap">
        <table className="data">
          <thead><tr><th>Application</th><th>Startup</th><th>Status</th></tr></thead>
          <tbody>
            {(ps.applications || []).map((app) => (
              <tr key={app.id}><td>{app.code}</td><td>{app.startup?.company_name}</td><td><Badge value={app.status} /></td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </Page>
  );
}

export function GovApplications() {
  const [status, setStatus] = useState("");
  const state = useLoad(() => api(`/applications/${status ? `?status=${status}` : ""}`), [status]);
  return (
    <Page kicker="Intake" title="Applications" actions={
      <select className="search" value={status} onChange={(e) => setStatus(e.target.value)}>
        <option value="">All statuses</option>
        {["SUBMITTED", "ELIGIBILITY_CHECK", "UNDER_TECHNICAL_EVALUATION", "CLARIFICATION_REQUIRED", "APPROVED_FOR_PILOT", "REJECTED", "REJECTED_DEADLINE", "CONTRACT_PENDING", "PILOT_ACTIVE", "PILOT_COMPLETED", "PILOT_CANCELLED"].map((item) => <option key={item}>{item}</option>)}
      </select>
    }>
      {state.loading ? <Loading /> : (
        <div className="card table-wrap">
          <table className="data">
            <thead><tr><th>Code</th><th>Startup</th><th>Problem</th><th>Status</th><th>Readiness</th></tr></thead>
            <tbody>
              {(state.data || []).map((app) => (
                <tr key={app.id}>
                  <td>{app.code}</td>
                  <td>{app.startup?.company_name}</td>
                  <td>{app.problem?.title}</td>
                  <td><Badge value={app.status} /></td>
                  <td>{app.pilot_readiness || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Page>
  );
}

export function GovStartups() {
  const [q, setQ] = useState("");
  const state = useLoad(() => api(`/startups/${q ? `?q=${encodeURIComponent(q)}` : ""}`), [q]);
  return (
    <Page kicker="Participation" title="Startups" actions={<input className="search" value={q} placeholder="Search" onChange={(e) => setQ(e.target.value)} />}>
      {state.loading ? <Loading /> : (
        <div className="card table-wrap">
          <table className="data">
            <thead><tr><th>Company</th><th>Domain</th><th>Place</th><th>DPIIT</th><th>Experience</th></tr></thead>
            <tbody>
              {(state.data || []).map((s) => (
                <tr key={s.id}><td><Link to={`/government/startups?focus=${s.id}`}>{s.company_name}</Link></td><td>{s.domain}</td><td>{s.city}, {s.state}</td><td>{s.dpiit_number}</td><td>{s.experience_years} yrs</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Page>
  );
}

export function GovAlerts() {
  const alerts = useLoad(() => api("/alerts/"));
  const logs = useLoad(() => api("/audit-logs/"));
  const toast = useToast();
  return (
    <Page kicker="Watchlist" title="Alerts" lede="No-selection, expiry and overdue-report alerts are computed from the register." actions={
      <Button variant="ghost" onClick={async () => { await api("/documents/expiry-scan/", { method: "POST" }); toast.push("Expiry scan completed"); alerts.reload(); }}>Run expiry check</Button>
    }>
      {alerts.loading ? <Loading /> : (alerts.data || []).length === 0 ? <Empty>No alerts.</Empty> : (
        <div className="stack">
          {alerts.data.map((alert, index) => (
            <article key={index} className="card card-pad">
              <div className="card-title"><strong>{alert.title}</strong><Badge value={alert.severity === "danger" ? "EXPIRED" : "EXPIRING_SOON"} /></div>
              <div>{alert.body}</div>
              <div className="small">{alert.entity}</div>
              {alert.link && <Link to={alert.link}>Open record</Link>}
            </article>
          ))}
        </div>
      )}
      <section className="card card-pad">
        <h3>Recent audit</h3>
        <table className="data">
          <tbody>
            {(logs.data || []).slice(0, 12).map((row) => (
              <tr key={row.id}><td>{row.created_at.slice(0, 16).replace("T", " ")}</td><td>{row.actor}</td><td>{row.action}</td><td>{row.detail}</td></tr>
            ))}
          </tbody>
        </table>
      </section>
    </Page>
  );
}

export function GovEmployees() {
  const state = useLoad(() => api("/employees/"));
  const meta = useLoad(() => api("/meta/"));
  const toast = useToast();
  const [form, setForm] = useState({ name: "", email: "", role: "TECHNICAL_EVALUATOR", designation: "", employee_id: "", department_id: "" });
  return (
    <Page kicker="Establishment" title="Employees">
      <form className="card card-pad grid-2" onSubmit={async (e) => {
        e.preventDefault();
        try {
          await api("/employees/", { method: "POST", body: { ...form, department_id: form.department_id || null, password: "demo123" } });
          toast.push("Employee added. Password is demo123.");
          state.reload();
        } catch (error) { toast.push(error.message, "bad"); }
      }}>
        <Field label="Name"><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></Field>
        <Field label="Email"><input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required /></Field>
        <Field label="Role">
          <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            {(meta.data?.roles || []).filter((r) => r.value !== "STARTUP").map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
        </Field>
        <Field label="Designation"><input value={form.designation} onChange={(e) => setForm({ ...form, designation: e.target.value })} /></Field>
        <Field label="Employee ID"><input value={form.employee_id} onChange={(e) => setForm({ ...form, employee_id: e.target.value })} /></Field>
        <Field label="Department">
          <select value={form.department_id} onChange={(e) => setForm({ ...form, department_id: e.target.value })}>
            <option value="">—</option>
            {(meta.data?.departments || []).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </Field>
        <Button type="submit">Add employee</Button>
      </form>
      {state.loading ? <Loading /> : (
        <div className="card table-wrap">
          <table className="data">
            <thead><tr><th>Name</th><th>Role</th><th>Email</th><th>Employee ID</th><th>Department</th></tr></thead>
            <tbody>
              {(state.data || []).map((person) => (
                <tr key={person.id}><td>{person.name}</td><td>{person.role_label}</td><td>{person.email}</td><td>{person.employee_id || "—"}</td><td>{person.department || "—"}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Page>
  );
}
