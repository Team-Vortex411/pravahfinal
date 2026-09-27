import { useState } from "react";
import { Link } from "react-router-dom";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AIBanner, AILabel, Badge, Button, Disclaimer, Field, Modal, Timeline } from "./ui";
import { api, downloadAuth, inr, when } from "../services/api";
import { useToast } from "../context/AppState";

const COLORS = ["#0b1f3a", "#c9a227", "#138808", "#ff9933", "#1d4e89"];

export default function PilotWorkspace({ pilot, reload, mode }) {
  const toast = useToast();
  const [modal, setModal] = useState(null);
  if (!pilot) return null;
  const series = pilot.kpi_series || [];
  const weeks = [...new Set(series.flatMap((item) => item.points.map((point) => point.week)))].sort((a, b) => a - b);
  const chart = weeks.map((week) => {
    const row = { week: `W${week}` };
    series.forEach((item) => {
      const point = item.points.find((entry) => entry.week === week);
      row[item.name] = point ? point.actual : null;
    });
    return row;
  });
  const latestAi = [...(pilot.weekly_reports || [])].reverse().find((report) => report.ai_progress?.result);

  async function act(path, body, ok) {
    try {
      await api(path, { method: "POST", body });
      toast.push(ok);
      setModal(null);
      reload();
    } catch (error) {
      toast.push(error.message, "bad");
    }
  }

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <div className="kicker">{pilot.code} · {pilot.problem?.department}</div>
          <h1 className="serif" style={{ fontSize: 34, margin: "4px 0" }}>{pilot.problem?.title}</h1>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <Badge value={pilot.status} />
            <span className="small">{pilot.startup?.company_name} · {pilot.location}</span>
          </div>
        </div>
        <div className="page-actions no-print">
          <Button variant="ghost" onClick={() => downloadAuth(`/api/pilots/${pilot.id}/contract-file/`, `${pilot.code}-contract.pdf`)}>Open contract</Button>
          {mode === "procurement" && <Button to={`/procurement/pilots/${pilot.id}/contract`} variant="gold">Contract & KPIs</Button>}
          {mode === "procurement" && pilot.status !== "CANCELLED" && pilot.status !== "COMPLETED" && (
            <Button variant="danger" onClick={() => setModal("cancel")}>Cancel pilot</Button>
          )}
        </div>
      </div>

      {pilot.status === "CANCELLED" && (
        <div className="demo-banner">Pilot cancelled{pilot.cancelled_at ? ` on ${when(pilot.cancelled_at)}` : ""}. {pilot.cancellation_reason}</div>
      )}

      <div className="card card-pad"><Timeline items={pilot.timeline} /></div>

      <div className="grid-2">
        <section className="card card-pad stack">
          <div className="card-title"><h3>Pilot contract</h3><Badge value={pilot.contract?.status} /></div>
          <div className="small">Contract {pilot.contract?.contract_no} · KPI method {pilot.contract?.kpi_method} · {pilot.kpi_locked ? "KPIs locked" : "KPIs editable"}</div>
          <div><b>Joining deadline</b> {when(pilot.joining_deadline)} · <b>Window</b> {when(pilot.start_date)} to {when(pilot.end_date)}</div>
          <p className="small">{pilot.responsibilities}</p>
          <p className="small">Government support: {pilot.government_support}</p>
          <p className="small">Payment: {pilot.payment_conditions}</p>
          {pilot.contract?.replacement_log?.length > 0 && (
            <div className="small">Contract file event: {pilot.contract.replacement_log.at(-1).event}</div>
          )}
          {mode === "startup" && pilot.contract?.status === "SENT" && (
            <Button onClick={() => setModal("sign")}>Accept and sign</Button>
          )}
          <div className="small">Field side: {pilot.field_evaluator?.display || pilot.field_evaluator?.name || "Not assigned"}</div>
        </section>
        <section className="card card-pad stack">
          <div className="card-title"><h3>Milestones</h3><span className="small">{pilot.reporting_frequency} reporting</span></div>
          {(pilot.milestones || []).map((item) => (
            <div key={item.id} style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
              <span>{item.status === "COMPLETE" ? "✓" : "○"} {item.name} <span className="small">week {item.due_week}</span></span>
              <span>{inr(item.amount)} <Badge value={item.status} /></span>
            </div>
          ))}
          {mode === "procurement" && <Button variant="ghost" to={`/procurement/pilots/${pilot.id}/contract`}>Update milestones</Button>}
        </section>
      </div>

      <section className="card card-pad stack">
        <div className="card-title"><h3>Required KPIs</h3><span className="small">Weights must total 100%. Official score uses verified actuals only.</span></div>
        <div className="table-wrap">
          <table className="data">
            <thead><tr><th>KPI</th><th>Target</th><th>Weight</th><th>Priority</th><th>Direction</th><th>Max</th></tr></thead>
            <tbody>
              {(pilot.kpis || []).map((kpi) => (
                <tr key={kpi.id}>
                  <td>{kpi.name}</td>
                  <td>{kpi.target} {kpi.unit}</td>
                  <td>{kpi.weight}%</td>
                  <td><Badge value={kpi.priority} /></td>
                  <td>{kpi.direction === "LOWER_IS_BETTER" ? "Lower is better" : "Higher is better"}</td>
                  <td>{kpi.max_score}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {pilot.contract?.kpi_method === "EXTRACT" && !pilot.contract?.kpis_finalized && mode === "procurement" && (
          <div className="demo-banner">Extracted KPIs are waiting for officer review. They are not official until confirmed.</div>
        )}
      </section>

      <section className="card card-pad stack">
        <div className="card-title">
          <h3>Verified weekly trend</h3>
          <span className="small">Chart is drawn from stored verified values, not from an image produced by the model.</span>
        </div>
        {chart.length === 0 ? <div className="small">No field-verified weekly points yet. Submitted claims stay pending until the field evaluator verifies them.</div> : (
          <div style={{ width: "100%", height: 280 }}>
            <ResponsiveContainer>
              <LineChart data={chart}>
                <CartesianGrid stroke="#e6e1d6" />
                <XAxis dataKey="week" />
                <YAxis />
                <Tooltip />
                <Legend />
                {series.map((item, index) => (
                  <Line key={item.name} type="monotone" dataKey={item.name} stroke={COLORS[index % COLORS.length]} strokeWidth={2} connectNulls dot />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
        {latestAi && (
          <AIBanner demo={latestAi.ai_progress.demo} notice={latestAi.ai_progress.notice}>
            <p>{latestAi.ai_progress.result.progress_summary}</p>
            <p><b>Improvement tip:</b> {latestAi.ai_progress.result.improvement_tip}</p>
          </AIBanner>
        )}
      </section>

      <section className="card card-pad stack">
        <div className="card-title">
          <h3>Weekly reports</h3>
          {mode === "startup" && pilot.status === "ACTIVE" && <Button onClick={() => setModal("report")}>Submit weekly report</Button>}
        </div>
        {(pilot.weekly_reports || []).map((report) => (
          <article key={report.id} className="card" style={{ padding: 12 }}>
            <div className="card-title">
              <strong>Week {report.week}</strong>
              <span style={{ display: "flex", gap: 6 }}><Badge value={report.status} /> {report.verification_status && <Badge value={report.verification_status} />}</span>
            </div>
            <div className="small">Due {when(report.due_date)} · Submitted {when(report.submitted_at)}</div>
            {report.narrative && <p>{report.narrative}</p>}
            {report.kpi_claims?.length > 0 && <div className="small">Startup claims (not official until verified): {report.kpi_claims.map((item) => `${item.name} ${item.actual}`).join(" · ")}</div>}
            {report.results?.length > 0 && <div className="small">Verified values: {report.results.map((item) => `${item.name} ${item.actual} ${item.unit}`).join(" · ")}</div>}
            {report.delay_reason && <div className="demo-banner">Delay explanation: {report.delay_reason} {report.delay_review ? `· review ${report.delay_review}` : ""}</div>}
            {report.observations && <div className="small">Observation: {report.observations}</div>}
            <div className="page-actions" style={{ marginTop: 8 }}>
              {mode === "startup" && (report.status === "LATE" || report.status === "PENDING") && (
                <Button variant="ghost" onClick={() => setModal({ type: "excuse", report })}>Explain delay</Button>
              )}
              {mode === "field" && report.delay_review === "PENDING" && (
                <>
                  <Button variant="good" onClick={() => act(`/pilots/${pilot.id}/delay-review/`, { report_id: report.id, action: "RELAXATION", note: "Relaxation granted for this week." }, "Relaxation recorded")}>Grant relaxation</Button>
                  <Button variant="ghost" onClick={() => act(`/pilots/${pilot.id}/delay-review/`, { report_id: report.id, action: "ACCEPT", note: "Explanation accepted." }, "Explanation accepted")}>Accept explanation</Button>
                  <Button variant="ghost" onClick={() => act(`/pilots/${pilot.id}/delay-review/`, { report_id: report.id, action: "CLARIFICATION", note: "Please add the field sheet." }, "Clarification requested")}>Request clarification</Button>
                  <Button variant="danger" onClick={() => act(`/pilots/${pilot.id}/delay-review/`, { report_id: report.id, action: "ESCALATE", note: "Repeated delay escalated to the procurement officer." }, "Escalated")}>Escalate</Button>
                </>
              )}
              {mode === "field" && report.submitted_at && report.verification_status !== "VERIFIED" && (
                <Button onClick={() => setModal({ type: "verify", report })}>Verify report</Button>
              )}
            </div>
          </article>
        ))}
        {mode === "startup" && <div className="small">If a weekly report is overdue you will see an alert. An excuse goes to the field evaluator, not to an automatic penalty.</div>}
      </section>

      <section className="card card-pad stack" id="final-report">
        <div className="card-title"><h3>Final report</h3>{pilot.final_report?.verification_status && <Badge value={pilot.final_report.verification_status} />}</div>
        {!pilot.final_report && <div className="small">No final report yet. Scoring does not run before field verification.</div>}
        {pilot.final_report && (
          <>
            <p>{pilot.final_report.narrative}</p>
            <div className="small">Claims: {(pilot.final_report.kpi_claims || []).map((item) => `${item.name} ${item.actual}`).join(" · ") || "—"}</div>
            <div className="small">Verified extraction: {(pilot.final_report.extracted_kpis || []).map((item) => `${item.name} ${item.actual}`).join(" · ") || "Waiting for verification"}</div>
            {pilot.final_report.observations && <div className="small">Field observation: {pilot.final_report.observations}</div>}
          </>
        )}
        {mode === "startup" && pilot.status === "ACTIVE" && <Button onClick={() => setModal("final")}>Submit final report</Button>}
        {mode === "field" && pilot.final_report && pilot.final_report.verification_status !== "VERIFIED" && (
          <Button onClick={() => setModal("verify-final")}>Verify final result</Button>
        )}
      </section>

      {pilot.score && (
        <section className="card card-pad stack">
          <div className="card-title">
            <h3>Official performance score {pilot.score.overall}</h3>
            <Badge value={pilot.score.label === "High Performer" ? "PILOT_COMPLETED" : "OPEN"} />
          </div>
          <div className="small">{pilot.score.label} · {pilot.score.disclaimer}</div>
          {pilot.score.must_have_failures?.length > 0 && (
            <div className="demo-banner">MUST HAVE attention: {pilot.score.must_have_failures.join(", ")}. Optional KPIs do not hide this gap.</div>
          )}
          <table className="data">
            <thead><tr><th>KPI</th><th>Target</th><th>Actual</th><th>Variance</th><th>Score</th><th>Weighted</th><th>Priority</th></tr></thead>
            <tbody>
              {pilot.score.kpis.map((row) => (
                <tr key={row.kpi_id}>
                  <td>{row.name}</td><td>{row.target}</td><td>{row.actual}</td><td>{row.variance}</td>
                  <td>{row.score}</td><td>{row.weighted_score}</td><td><Badge value={row.priority} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <section className="card card-pad stack">
        <div className="card-title">
          <h3>Complaints</h3>
          {mode === "field" && <Button variant="danger" onClick={() => setModal("complaint")}>Submit complaint</Button>}
        </div>
        {(pilot.complaints || []).length === 0 && <div className="small">No complaints on this pilot.</div>}
        {(pilot.complaints || []).map((item) => (
          <article key={item.id}>
            <div className="card-title"><strong>{item.category}</strong><Badge value={item.status} /></div>
            <p>{item.description}</p>
            <div className="small">Raised by {item.raised_by?.display || item.raised_by?.name}</div>
            {item.startup_response && <div className="small">Startup response: {item.startup_response}</div>}
            {item.officer_action && <div className="small">Officer action: {item.officer_action}</div>}
            {mode === "startup" && <Button variant="ghost" onClick={() => setModal({ type: "respond", item })}>Respond</Button>}
            {mode === "procurement" && (
              <div className="page-actions">
                <Button variant="ghost" onClick={() => act(`/complaints/${item.id}/respond/`, { action: "REQUEST_RESPONSE", note: "Please respond to the field observation." }, "Response requested")}>Request response</Button>
                <Button variant="good" onClick={() => act(`/complaints/${item.id}/respond/`, { action: "ACCEPT", note: "Explanation accepted." }, "Accepted")}>Accept explanation</Button>
                <Button variant="ghost" onClick={() => act(`/complaints/${item.id}/respond/`, { action: "ESCALATE", note: "Escalated for authority review." }, "Escalated")}>Escalate</Button>
                <Button variant="ghost" onClick={() => act(`/complaints/${item.id}/respond/`, { action: "CLOSE", note: "Closed on the file." }, "Closed")}>Close</Button>
              </div>
            )}
          </article>
        ))}
      </section>

      {pilot.recommendation && (
        <section className="card card-pad stack">
          <div className="card-title"><h3>Scale-up note</h3><AILabel /></div>
          <Badge value={pilot.recommendation.choice} />
          <p>{pilot.recommendation.narrative}</p>
          {pilot.recommendation.ai_demo && <div className="demo-banner">{pilot.recommendation.ai_notice}</div>}
          <Disclaimer />
        </section>
      )}
      <Disclaimer />

      {modal === "sign" && <SignModal pilot={pilot} onClose={() => setModal(null)} onDone={reload} />}
      {modal === "report" && <ReportModal pilot={pilot} onClose={() => setModal(null)} onDone={reload} />}
      {modal === "final" && <FinalModal pilot={pilot} onClose={() => setModal(null)} onDone={reload} />}
      {modal === "cancel" && <CancelModal pilot={pilot} onClose={() => setModal(null)} onDone={reload} />}
      {modal?.type === "excuse" && <ExcuseModal pilot={pilot} report={modal.report} onClose={() => setModal(null)} onDone={reload} />}
      {modal?.type === "verify" && <VerifyModal pilot={pilot} report={modal.report} onClose={() => setModal(null)} onDone={reload} />}
      {modal === "verify-final" && <VerifyFinalModal pilot={pilot} onClose={() => setModal(null)} onDone={reload} />}
      {modal === "complaint" && <ComplaintModal pilot={pilot} onClose={() => setModal(null)} onDone={reload} />}
      {modal?.type === "respond" && <RespondModal item={modal.item} onClose={() => setModal(null)} onDone={reload} />}
      {modal === "cancel" ? null : null}
    </div>
  );
}

function CancelModal({ pilot, onClose, onDone }) {
  const toast = useToast();
  const [reason, setReason] = useState("");
  return (
    <Modal title="Cancel pilot" onClose={onClose}>
      <Field label="Reason"><textarea value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
      <Button variant="danger" onClick={async () => {
        try {
          await api(`/pilots/${pilot.id}/cancel/`, { method: "POST", body: { reason } });
          toast.push("Pilot cancelled");
          onClose();
          onDone();
        } catch (error) { toast.push(error.message, "bad"); }
      }}>Confirm cancellation</Button>
    </Modal>
  );
}

function SignModal({ pilot, onClose, onDone }) {
  const toast = useToast();
  const [file, setFile] = useState(null);
  return (
    <Modal title="Accept and sign" onClose={onClose}>
      <p className="small">Download the unsigned contract, sign it, and upload the signed copy. The unsigned object is replaced. This is not a procurement award.</p>
      <Button variant="ghost" onClick={() => downloadAuth(`/api/pilots/${pilot.id}/contract-file/`, "unsigned-contract.pdf")}>Download unsigned contract</Button>
      <Field label="Signed contract"><input type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={(e) => setFile(e.target.files?.[0])} /></Field>
      <Button onClick={async () => {
        if (!file) return toast.push("Upload the signed file", "bad");
        const form = new FormData();
        form.append("file", file);
        try {
          await api(`/pilots/${pilot.id}/sign/`, { method: "POST", form });
          toast.push("Signed contract stored");
          onClose();
          onDone();
        } catch (error) { toast.push(error.message, "bad"); }
      }}>Accept and sign</Button>
    </Modal>
  );
}

function KpiFields({ kpis, values, setValues }) {
  return (kpis || []).map((kpi) => (
    <Field key={kpi.id} label={`${kpi.name} (${kpi.unit})`}>
      <input type="number" step="0.1" value={values[kpi.name] ?? ""} onChange={(e) => setValues({ ...values, [kpi.name]: e.target.value })} />
    </Field>
  ));
}

function ReportModal({ pilot, onClose, onDone }) {
  const toast = useToast();
  const [week, setWeek] = useState((pilot.weekly_reports?.length || 0) + 1);
  const [narrative, setNarrative] = useState("");
  const [values, setValues] = useState({});
  const [file, setFile] = useState(null);
  return (
    <Modal title="Weekly report" onClose={onClose}>
      <div className="stack">
        <Field label="Week"><input type="number" value={week} onChange={(e) => setWeek(e.target.value)} /></Field>
        <Field label="Report"><textarea value={narrative} onChange={(e) => setNarrative(e.target.value)} /></Field>
        <KpiFields kpis={pilot.kpis} values={values} setValues={setValues} />
        <Field label="Evidence"><input type="file" onChange={(e) => setFile(e.target.files?.[0])} /></Field>
        <Button onClick={async () => {
          const claims = (pilot.kpis || []).map((kpi) => ({ name: kpi.name, actual: Number(values[kpi.name]), unit: kpi.unit, evidence_ref: file?.name || "" })).filter((item) => !Number.isNaN(item.actual));
          try {
            if (file) {
              const form = new FormData();
              form.append("week", week);
              form.append("narrative", narrative);
              form.append("kpi_results", JSON.stringify(claims));
              form.append("file", file);
              await api(`/pilots/${pilot.id}/reports/`, { method: "POST", form });
            } else {
              await api(`/pilots/${pilot.id}/reports/`, { method: "POST", body: { week: Number(week), narrative, kpi_results: claims } });
            }
            toast.push("Weekly report submitted for field verification");
            onClose();
            onDone();
          } catch (error) { toast.push(error.message, "bad"); }
        }}>Submit report</Button>
      </div>
    </Modal>
  );
}

function FinalModal({ pilot, onClose, onDone }) {
  const toast = useToast();
  const [narrative, setNarrative] = useState("");
  const [values, setValues] = useState({});
  return (
    <Modal title="Final report" onClose={onClose}>
      <div className="stack">
        <Field label="Closing narrative"><textarea value={narrative} onChange={(e) => setNarrative(e.target.value)} /></Field>
        <KpiFields kpis={pilot.kpis} values={values} setValues={setValues} />
        <Button onClick={async () => {
          const claims = (pilot.kpis || []).map((kpi) => ({ name: kpi.name, actual: Number(values[kpi.name]), unit: kpi.unit })).filter((item) => !Number.isNaN(item.actual));
          try {
            await api(`/pilots/${pilot.id}/final-report/`, { method: "POST", body: { narrative, kpi_results: claims } });
            toast.push("Final report submitted. It will be scored only after field verification.");
            onClose();
            onDone();
          } catch (error) { toast.push(error.message, "bad"); }
        }}>Submit final report</Button>
      </div>
    </Modal>
  );
}

function ExcuseModal({ pilot, report, onClose, onDone }) {
  const toast = useToast();
  const [reason, setReason] = useState("");
  return (
    <Modal title={`Delay explanation · week ${report.week}`} onClose={onClose}>
      <Field label="Reason"><textarea value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
      <Button onClick={async () => {
        try {
          await api(`/pilots/${pilot.id}/delay-excuse/`, { method: "POST", body: { week: report.week, reason } });
          toast.push("Explanation sent to the field evaluator");
          onClose();
          onDone();
        } catch (error) { toast.push(error.message, "bad"); }
      }}>Send explanation</Button>
    </Modal>
  );
}

function VerifyModal({ pilot, report, onClose, onDone }) {
  const toast = useToast();
  const [status, setStatus] = useState("VERIFIED");
  const [observations, setObservations] = useState("");
  return (
    <Modal title={`Verify week ${report.week}`} onClose={onClose}>
      <div className="stack">
        <Field label="Verification">
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="VERIFIED">Verified</option>
            <option value="NEEDS_CLARIFICATION">Needs clarification</option>
            <option value="NOT_VERIFIED">Not verified</option>
          </select>
        </Field>
        <Field label="Observations"><textarea value={observations} onChange={(e) => setObservations(e.target.value)} /></Field>
        <Button onClick={async () => {
          try {
            await api(`/pilots/${pilot.id}/verify-report/`, { method: "POST", body: { report_id: report.id, status, observations, activity_verified: status === "VERIFIED" } });
            toast.push(status === "VERIFIED" ? "Verified. KPI values extracted and stored." : "Verification recorded. Claims were not scored.");
            onClose();
            onDone();
          } catch (error) { toast.push(error.message, "bad"); }
        }}>Save verification</Button>
      </div>
    </Modal>
  );
}

function VerifyFinalModal({ pilot, onClose, onDone }) {
  const toast = useToast();
  const [status, setStatus] = useState("VERIFIED");
  const [observations, setObservations] = useState("Field sample checked against source registers.");
  return (
    <Modal title="Verify final result" onClose={onClose}>
      <div className="stack">
        <Field label="Status">
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="VERIFIED">Verified</option>
            <option value="NEEDS_CLARIFICATION">Needs clarification</option>
            <option value="NOT_VERIFIED">Not verified</option>
          </select>
        </Field>
        <Field label="Observations"><textarea value={observations} onChange={(e) => setObservations(e.target.value)} /></Field>
        <Button onClick={async () => {
          try {
            await api(`/pilots/${pilot.id}/verify-result/`, { method: "POST", body: { status, observations } });
            toast.push("Final verification saved");
            onClose();
            onDone();
          } catch (error) { toast.push(error.message, "bad"); }
        }}>Save</Button>
      </div>
    </Modal>
  );
}

function ComplaintModal({ pilot, onClose, onDone }) {
  const toast = useToast();
  const [category, setCategory] = useState("Missed field deployment");
  const [description, setDescription] = useState("");
  return (
    <Modal title="Complaint to procurement officer" onClose={onClose}>
      <div className="stack">
        <Field label="Category">
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            {["False KPI information", "Missed field deployment", "Repeated report delay", "Policy violation", "Poor pilot performance", "Other"].map((item) => <option key={item}>{item}</option>)}
          </select>
        </Field>
        <Field label="Description"><textarea value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
        <div className="small">Your personal name, email and phone are not shown to the startup.</div>
        <Button variant="danger" onClick={async () => {
          try {
            await api("/complaints/", { method: "POST", body: { pilot: pilot.id, category, description } });
            toast.push("Complaint sent to the procurement officer");
            onClose();
            onDone();
          } catch (error) { toast.push(error.message, "bad"); }
        }}>Submit complaint</Button>
      </div>
    </Modal>
  );
}

function RespondModal({ item, onClose, onDone }) {
  const toast = useToast();
  const [note, setNote] = useState("");
  return (
    <Modal title="Respond to field observation" onClose={onClose}>
      <Field label="Response"><textarea value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      <Button onClick={async () => {
        try {
          await api(`/complaints/${item.id}/respond/`, { method: "POST", body: { note } });
          toast.push("Response recorded");
          onClose();
          onDone();
        } catch (error) { toast.push(error.message, "bad"); }
      }}>Send response</Button>
    </Modal>
  );
}

export function PilotLink({ pilot, base }) {
  return <Link to={`${base}/${pilot.id}`}>{pilot.code} · {pilot.problem?.title}</Link>;
}
