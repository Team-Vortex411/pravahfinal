import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import ApplicationReview from "../components/ApplicationReview";
import PilotWorkspace from "../components/PilotWorkspace";
import { AIBanner, AILabel, Badge, Button, Disclaimer, Empty, ErrorNote, Field, GreenRing, Loading, Page, Stat, useLoad } from "../components/ui";
import { api, downloadAuth, when } from "../services/api";
import { useAuth, useToast } from "../context/AppState";

export function StartupDashboard() {
  const { user } = useAuth();
  const dash = useLoad(() => api("/dashboard/"));
  const matches = useLoad(() => api("/match/problem-statements/"));
  const docs = useLoad(() => api("/documents/"));
  const notes = useLoad(() => api("/notifications/"));
  if (dash.loading) return <Loading />;
  return (
    <Page kicker={`Startup · ${user?.startup?.company_name || ""}`} title="Your desk" lede="Recommendations come from embedding similarity and declared domain rules. They are not a selection.">
      <div className="grid-4">
        <Stat value={`${dash.data?.profile_completion ?? 0}%`} label="Profile completion" />
        <Stat value={dash.data?.valid_documents ?? 0} label="Valid documents" />
        <Stat value={dash.data?.applications ?? 0} label="Applications" />
        <Stat value={dash.data?.active_pilots ?? 0} label="Active pilots" />
      </div>
      <section className="stack">
        <div className="card-title"><h2 className="serif">Recommended problem statements</h2><AILabel /></div>
        <AIBanner />
        <div className="grid-3">
          {(matches.data || []).map((ps) => (
            <Link key={ps.id} to={`/startup/problem-statements/${ps.id}`} className="card card-pad" style={{ textDecoration: "none" }}>
              <div className="ring-label">
                <GreenRing value={ps.match?.score} />
                <div>
                  <AILabel />
                  <div className="small">AI match</div>
                </div>
              </div>
              <h3 style={{ marginTop: 10 }}>{ps.title}</h3>
              <div className="small">{ps.department?.name} · {ps.location}</div>
              <div className="small">Apply by {when(ps.application_deadline)}</div>
              <div className="small">{ps.match?.reasons?.[0]}</div>
            </Link>
          ))}
        </div>
        {(matches.data || []).length === 0 && <Empty>No fresh recommendations. Applied problems are hidden.</Empty>}
      </section>
      <section className="card card-pad">
        <h3>Documents needing attention</h3>
        {(docs.data || []).filter((d) => ["EXPIRING_SOON", "EXPIRED", "PENDING_VERIFICATION", "REJECTED"].includes(d.verification_status)).map((doc) => (
          <div key={doc.id} className="card-title"><span>{doc.name}</span><Badge value={doc.verification_status} /></div>
        ))}
      </section>
      <section className="card card-pad">
        <h3>Notifications</h3>
        {(notes.data || []).slice(0, 4).map((note) => <div key={note.id} className="small"><b>{note.title}.</b> {note.body}</div>)}
      </section>
      <Disclaimer />
    </Page>
  );
}

export function StartupProfile() {
  const { user, setUser } = useAuth();
  const toast = useToast();
  const startup = user?.startup || {};
  const [form, setForm] = useState({
    company_name: startup.company_name || "",
    domain: startup.domain || "",
    technologies: startup.technologies || "",
    dpiit_number: startup.dpiit_number || "",
    city: startup.city || "",
    state: startup.state || "",
    experience_years: startup.experience_years || 0,
    team_size: startup.team_size || 1,
    description: startup.description || "",
    gstin: startup.gstin || "",
    capabilities: startup.capabilities || "",
    relevant_experience: startup.relevant_experience || "",
    contact_person: startup.contact_person || user?.name || "",
  });
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });
  return (
    <Page kicker="Profile" title="Startup profile" lede="These are the fields used for the embedding. GSTIN is stored separately from the public profile set.">
      <form className="card card-pad grid-2" onSubmit={async (e) => {
        e.preventDefault();
        try {
          const saved = await api("/startups/", { method: "PATCH", body: form });
          setUser({ ...user, startup: saved, name: form.contact_person });
          toast.push("Profile saved and embedding refreshed");
        } catch (error) { toast.push(error.message, "bad"); }
      }}>
        {[["company_name", "Company name"], ["domain", "Domain"], ["technologies", "Technologies"], ["dpiit_number", "DPIIT number"], ["city", "City"], ["state", "State"], ["experience_years", "Experience years"], ["team_size", "Team size"], ["contact_person", "Contact person"], ["gstin", "GSTIN"]].map(([key, label]) => (
          <Field key={key} label={label}><input value={form[key]} onChange={set(key)} /></Field>
        ))}
        <Field label="Description"><textarea value={form.description} onChange={set("description")} /></Field>
        <Field label="Relevant experience"><textarea value={form.relevant_experience} onChange={set("relevant_experience")} /></Field>
        <Button type="submit">Save profile</Button>
      </form>
    </Page>
  );
}

export function StartupDocuments() {
  const state = useLoad(() => api("/documents/"));
  const meta = useLoad(() => api("/meta/"));
  const toast = useToast();
  const [file, setFile] = useState(null);
  const [docType, setDocType] = useState("DPIIT");
  const [replaces, setReplaces] = useState("");
  if (state.loading) return <Loading />;
  return (
    <Page kicker="Evidence" title="Documents" lede="An expired document is kept for history and is not valid for a new application. Upload a renewal; the evaluator verifies it again.">
      <form className="card card-pad grid-2" onSubmit={async (e) => {
        e.preventDefault();
        if (!file) return toast.push("Choose a file", "bad");
        const form = new FormData();
        form.append("file", file);
        form.append("document_type", docType);
        form.append("name", file.name);
        if (replaces) form.append("replaces", replaces);
        try {
          await api("/documents/", { method: "POST", form });
          toast.push("Uploaded. Status is pending verification.");
          state.reload();
        } catch (error) { toast.push(error.message, "bad"); }
      }}>
        <Field label="Type">
          <select value={docType} onChange={(e) => setDocType(e.target.value)}>
            {(meta.data?.document_types || []).map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </Field>
        <Field label="Renewal of">
          <select value={replaces} onChange={(e) => setReplaces(e.target.value)}>
            <option value="">New document</option>
            {(state.data || []).map((doc) => <option key={doc.id} value={doc.id}>{doc.name}</option>)}
          </select>
        </Field>
        <Field label="File" hint="PDF, PPT, PPTX, DOC, DOCX, JPG, PNG. Max 15 MB."><input type="file" onChange={(e) => setFile(e.target.files?.[0])} /></Field>
        <Button type="submit">Upload</Button>
      </form>
      <div className="card table-wrap">
        <table className="data">
          <thead><tr><th>Name</th><th>Type</th><th>Status</th><th>Expiry</th><th>Valid now</th><th></th></tr></thead>
          <tbody>
            {(state.data || []).map((doc) => (
              <tr key={doc.id}>
                <td>{doc.name} {doc.version > 1 ? `v${doc.version}` : ""}</td>
                <td>{doc.document_type_label}</td>
                <td><Badge value={doc.verification_status} /></td>
                <td>{doc.no_expiry ? "No expiry" : doc.expiry_date || "—"}</td>
                <td>{doc.currently_valid ? "Yes" : "No"}</td>
                <td><Button variant="ghost" onClick={() => downloadAuth(doc.download_url, doc.file_name)}>Open</Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Page>
  );
}

export function StartupProblems() {
  const state = useLoad(() => api("/problem-statements/"));
  if (state.loading) return <Loading />;
  return (
    <Page kicker="Discovery" title="Problem statements" lede="Match scores appear only for problems you have not already applied to.">
      <div className="grid-2">
        {(state.data || []).map((ps) => (
          <Link key={ps.id} to={`/startup/problem-statements/${ps.id}`} className="card card-pad" style={{ textDecoration: "none" }}>
            <div className="card-title"><span className="kicker">{ps.code}</span>{ps.match ? <span className="ring-label"><GreenRing value={ps.match.score} size={54} /><AILabel /></span> : <Badge value={ps.status} />}</div>
            <h3>{ps.title}</h3>
            <div className="small">{ps.department?.name} · {ps.location} · deadline {ps.application_deadline}</div>
            {ps.match && <div className="small">{ps.match.reasons?.[0]}</div>}
          </Link>
        ))}
      </div>
    </Page>
  );
}

export function StartupProblemDetail() {
  const { id } = useParams();
  const state = useLoad(() => api(`/problem-statements/${id}/`), [id]);
  const docs = useLoad(() => api("/documents/"));
  const toast = useToast();
  const [checks, setChecks] = useState({});
  const [readiness, setReadiness] = useState("");
  const [proposal, setProposal] = useState("");
  const [selected, setSelected] = useState([]);
  const [file, setFile] = useState(null);
  if (state.loading) return <Loading />;
  const ps = state.data;
  if (!ps) return <Empty>Not found.</Empty>;
  return (
    <Page kicker={ps.code} title={ps.title} lede={ps.description} actions={ps.match && <span className="ring-label"><GreenRing value={ps.match.score} /><AILabel /></span>}>
      {ps.match && <AIBanner><div>{ps.match.reasons?.join(" ")} Semantic component {ps.match.semantic}. Method: {ps.match.method}.</div></AIBanner>}
      <div className="card card-pad small">Join by {ps.pilot_joining_deadline}. Required: {ps.required_documents.join(", ")}. Pilot at {ps.pilot_location}.</div>
      <form className="card card-pad stack" onSubmit={async (e) => {
        e.preventDefault();
        try {
          let documentIds = [...selected];
          if (file) {
            const form = new FormData();
            form.append("file", file);
            form.append("document_type", "TECHNICAL_PROPOSAL");
            form.append("name", file.name);
            const uploaded = await api("/documents/", { method: "POST", form });
            documentIds.push(uploaded.id);
          }
          const app = await api("/applications/", { method: "POST", body: {
            problem_statement: ps.id,
            eligibility_confirmed: true,
            eligibility_checks: checks,
            pilot_readiness: readiness,
            proposal_text: proposal,
            document_ids: documentIds,
          } });
          toast.push(app.status === "REJECTED_DEADLINE" ? "Application closed: cannot meet pilot deadline" : "Application submitted");
          window.location.assign(`/startup/applications/${app.id}`);
        } catch (error) { toast.push(error.message, "bad"); }
      }}>
        <h3>Eligibility</h3>
        {ps.eligibility_criteria.map((item) => (
          <label key={item} className="small"><input type="checkbox" checked={!!checks[item]} onChange={(e) => setChecks({ ...checks, [item]: e.target.checked })} /> {item}</label>
        ))}
        <h3>Can you prepare your product and make it ready for deployment by the defined pilot joining deadline?</h3>
        <label><input type="radio" name="ready" checked={readiness === "YES"} onChange={() => setReadiness("YES")} /> YES</label>
        <label><input type="radio" name="ready" checked={readiness === "NO"} onChange={() => setReadiness("NO")} /> NO</label>
        {readiness === "NO" && <div className="demo-banner">Choosing NO closes the application as REJECTED — CANNOT MEET PILOT DEADLINE. You cannot continue with this application.</div>}
        <Field label="Attach valid documents">
          <div className="stack">
            {(docs.data || []).filter((d) => d.currently_valid).map((doc) => (
              <label key={doc.id} className="small"><input type="checkbox" checked={selected.includes(doc.id)} onChange={(e) => setSelected(e.target.checked ? [...selected, doc.id] : selected.filter((x) => x !== doc.id))} /> {doc.document_type_label} · {doc.name}</label>
            ))}
          </div>
        </Field>
        <Field label="Technical proposal / PPT"><input type="file" accept=".pdf,.ppt,.pptx,.doc,.docx" onChange={(e) => setFile(e.target.files?.[0])} /></Field>
        <Field label="Solution summary"><textarea value={proposal} onChange={(e) => setProposal(e.target.value)} required /></Field>
        <Button type="submit" disabled={!readiness}>Submit application</Button>
      </form>
    </Page>
  );
}

export function StartupApplications() {
  const state = useLoad(() => api("/applications/"));
  if (state.loading) return <Loading />;
  return (
    <Page kicker="Your file" title="Applications">
      <div className="card table-wrap">
        <table className="data">
          <thead><tr><th>Code</th><th>Problem</th><th>Status</th><th>Submitted</th></tr></thead>
          <tbody>
            {(state.data || []).map((app) => (
              <tr key={app.id}>
                <td><Link to={`/startup/applications/${app.id}`}>{app.code}</Link></td>
                <td>{app.problem?.title}</td>
                <td><Badge value={app.status} /></td>
                <td>{when(app.submitted_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Page>
  );
}

export function StartupApplicationDetail() {
  const { id } = useParams();
  const state = useLoad(() => api(`/applications/${id}/`), [id]);
  if (state.loading) return <Loading />;
  if (!state.data) return <ErrorNote error={state.error || "Not found"} />;
  return <ApplicationReview application={state.data} reload={state.reload} mode="startup" />;
}

export function StartupPilots() {
  const state = useLoad(() => api("/pilots/"));
  if (state.loading) return <Loading />;
  return (
    <Page kicker="Pilots" title="Your pilots">
      <div className="stack">
        {(state.data || []).map((pilot) => (
          <Link key={pilot.id} to={`/startup/pilots/${pilot.id}`} className="card card-pad" style={{ textDecoration: "none" }}>
            <div className="card-title"><b>{pilot.problem?.title}</b><Badge value={pilot.status} /></div>
            <div className="small">{pilot.code} · {pilot.location} · field side shown only as {pilot.field_evaluator?.display || "Assigned Field Evaluator"}</div>
            {pilot.score && <div>Official score {pilot.score.overall} · {pilot.score.label}</div>}
          </Link>
        ))}
        {(state.data || []).length === 0 && <Empty>No pilot yet.</Empty>}
      </div>
    </Page>
  );
}

export function StartupPilotDetail() {
  const { id } = useParams();
  const state = useLoad(() => api(`/pilots/${id}/`), [id]);
  if (state.loading) return <Loading />;
  return <PilotWorkspace pilot={state.data} reload={state.reload} mode="startup" />;
}

export function StartupReports() {
  return <StartupPilotDetail />;
}
export function StartupFinalReport() {
  return <StartupPilotDetail />;
}
