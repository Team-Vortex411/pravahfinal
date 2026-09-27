import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import ApplicationReview from "../components/ApplicationReview";
import { Badge, Button, Empty, Field, Loading, Modal, Page, Stat, useLoad } from "../components/ui";
import { api, downloadAuth } from "../services/api";
import { useToast } from "../context/AppState";

export function EvalDashboard() {
  const apps = useLoad(() => api("/applications/"));
  const docs = useLoad(() => api("/documents/?status=PENDING_VERIFICATION"));
  if (apps.loading) return <Loading />;
  const rows = apps.data || [];
  return (
    <Page kicker="Technical evaluator" title="Assigned work" lede="You see applications assigned to you. A decision here is a human decision.">
      <div className="grid-4">
        <Stat value={rows.length} label="Assigned applications" />
        <Stat value={rows.filter((a) => a.status === "UNDER_TECHNICAL_EVALUATION").length} label="Technical reviews" />
        <Stat value={(docs.data || []).length} label="Pending documents" />
        <Stat value={rows.filter((a) => a.status === "CLARIFICATION_REQUIRED").length} label="Clarifications" />
      </div>
      <Queue rows={rows.slice(0, 8)} />
    </Page>
  );
}

function Queue({ rows }) {
  return (
    <div className="card table-wrap">
      <table className="data">
        <thead><tr><th>Application</th><th>Startup</th><th>Problem</th><th>Status</th></tr></thead>
        <tbody>
          {rows.map((app) => (
            <tr key={app.id}>
              <td><Link to={`/evaluator/applications/${app.id}`}>{app.code}</Link></td>
              <td>{app.startup?.company_name}</td>
              <td>{app.problem?.title}</td>
              <td><Badge value={app.status} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function EvalApplications() {
  const [status, setStatus] = useState("");
  const state = useLoad(() => api(`/applications/${status ? `?status=${status}` : ""}`), [status]);
  return (
    <Page kicker="Queue" title="Applications" actions={
      <select className="search" value={status} onChange={(e) => setStatus(e.target.value)}>
        <option value="">All</option>
        <option>UNDER_TECHNICAL_EVALUATION</option>
        <option>CLARIFICATION_REQUIRED</option>
        <option>APPROVED_FOR_PILOT</option>
        <option>REJECTED</option>
      </select>
    }>
      {state.loading ? <Loading /> : <Queue rows={state.data || []} />}
    </Page>
  );
}

export function EvalApplicationDetail() {
  const { id } = useParams();
  const state = useLoad(() => api(`/applications/${id}/`), [id]);
  if (state.loading) return <Loading />;
  if (!state.data) return <Empty>Application not available.</Empty>;
  return <ApplicationReview application={state.data} reload={state.reload} mode="evaluator" />;
}

export function EvalDocuments() {
  const [status, setStatus] = useState("");
  const state = useLoad(() => api(`/documents/${status ? `?status=${status}` : ""}`), [status]);
  return (
    <Page kicker="Document register" title="Documents" lede="Verification, rejection, clarification and expiry are recorded against the file. History is kept when a startup uploads a renewal." actions={
      <select className="search" value={status} onChange={(e) => setStatus(e.target.value)}>
        <option value="">All</option>
        <option>PENDING_VERIFICATION</option>
        <option>VERIFIED_VALID</option>
        <option>EXPIRING_SOON</option>
        <option>EXPIRED</option>
        <option>REJECTED</option>
      </select>
    }>
      {state.loading ? <Loading /> : (
        <div className="card table-wrap">
          <table className="data">
            <thead><tr><th>Document</th><th>Startup</th><th>Type</th><th>Status</th><th>Expiry</th><th></th></tr></thead>
            <tbody>
              {(state.data || []).map((doc) => (
                <tr key={doc.id}>
                  <td><Link to={`/evaluator/documents/${doc.id}`}>{doc.name}</Link></td>
                  <td>{doc.startup_name}</td>
                  <td>{doc.document_type_label}</td>
                  <td><Badge value={doc.verification_status} /></td>
                  <td>{doc.no_expiry ? "No expiry" : doc.expiry_date || "—"}</td>
                  <td><Button variant="ghost" onClick={() => downloadAuth(doc.download_url, doc.file_name)}>Open</Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Page>
  );
}

export function EvalDocumentDetail() {
  const { id } = useParams();
  const state = useLoad(() => api(`/documents/${id}/`), [id]);
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ action: "VERIFY", expiry_date: "", no_expiry: false, notes: "" });
  if (state.loading) return <Loading />;
  const doc = state.data;
  if (!doc) return <Empty>Document not found.</Empty>;
  return (
    <Page kicker={doc.document_type_label} title={doc.name} actions={<Badge value={doc.verification_status} />}>
      <div className="card card-pad stack">
        <div>Startup: {doc.startup_name}</div>
        <div className="small">Verified by {doc.verified_by?.name || "—"} on {doc.verified_date || "—"} · Currently valid: {doc.currently_valid ? "yes" : "no"} · Version {doc.version}</div>
        {doc.notes && <div className="demo-banner">{doc.notes}</div>}
        <div className="page-actions">
          <Button variant="ghost" onClick={() => downloadAuth(doc.download_url, doc.file_name)}>Open file</Button>
          <Button onClick={() => setOpen(true)}>Record verification</Button>
        </div>
      </div>
      {open && (
        <Modal title="Document decision" onClose={() => setOpen(false)}>
          <div className="stack">
            <Field label="Action">
              <select value={form.action} onChange={(e) => setForm({ ...form, action: e.target.value })}>
                <option value="VERIFY">Verify</option>
                <option value="REJECT">Reject</option>
                <option value="CLARIFICATION">Request clarification</option>
              </select>
            </Field>
            <label className="small"><input type="checkbox" checked={form.no_expiry} onChange={(e) => setForm({ ...form, no_expiry: e.target.checked })} /> No expiry</label>
            {!form.no_expiry && <Field label="Expiry date"><input type="date" value={form.expiry_date} onChange={(e) => setForm({ ...form, expiry_date: e.target.value })} /></Field>}
            <Field label="Note"><textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></Field>
            <Button onClick={async () => {
              try {
                await api(`/documents/${doc.id}/verify/`, { method: "PATCH", body: form });
                toast.push("Document updated");
                setOpen(false);
                state.reload();
              } catch (error) { toast.push(error.message, "bad"); }
            }}>Save</Button>
          </div>
        </Modal>
      )}
    </Page>
  );
}

export function EvalEvaluations() {
  const state = useLoad(() => api("/evaluations/"));
  if (state.loading) return <Loading />;
  return (
    <Page kicker="Record" title="Technical evaluations">
      <div className="card table-wrap">
        <table className="data">
          <thead><tr><th>Application</th><th>Startup</th><th>Problem</th><th>Decision</th><th>Score</th></tr></thead>
          <tbody>
            {(state.data || []).map((row) => (
              <tr key={row.id}>
                <td><Link to={`/evaluator/applications/${row.application_id}`}>{row.application_code}</Link></td>
                <td>{row.startup}</td>
                <td>{row.problem}</td>
                <td><Badge value={row.decision} /></td>
                <td>{row.technical_score ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Page>
  );
}
