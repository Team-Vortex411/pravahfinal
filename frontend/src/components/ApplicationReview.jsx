import { useState } from "react";
import { AIBanner, AILabel, Badge, Button, Disclaimer, Field, GreenRing, Timeline } from "./ui";
import { api, downloadAuth } from "../services/api";
import { useToast } from "../context/AppState";

const SCORE_FIELDS = [
  ["technical_feasibility", "Technical Feasibility"],
  ["innovation", "Innovation"],
  ["problem_relevance", "Problem Relevance"],
  ["scalability", "Scalability"],
  ["technical_capability", "Technical Capability"],
  ["relevant_experience", "Relevant Experience"],
];

export default function ApplicationReview({ application, reload, mode }) {
  const toast = useToast();
  const ai = application.ai_analysis || {};
  const result = ai.result || {};
  const [scores, setScores] = useState(application.evaluation?.scores || {});
  const [comments, setComments] = useState(application.evaluation?.comments || "");
  const [response, setResponse] = useState("");

  async function save(decision) {
    try {
      await api(application.evaluation ? `/evaluations/${application.evaluation.id}/` : "/evaluations/", {
        method: application.evaluation ? "PATCH" : "POST",
        body: { application: application.id, scores, comments, decision },
      });
      toast.push(decision ? "Decision recorded. AI did not make this decision." : "Scores saved");
      reload();
    } catch (error) {
      toast.push(error.message, "bad");
    }
  }

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <div className="kicker">{application.code}</div>
          <h1 className="serif" style={{ fontSize: 32, margin: "4px 0" }}>{application.problem?.title}</h1>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <Badge value={application.status} />
            <span className="small">{application.startup?.company_name}</span>
          </div>
        </div>
      </div>
      <div className="card card-pad"><Timeline items={application.timeline} /></div>
      {application.status === "REJECTED_DEADLINE" && (
        <div className="demo-banner">REJECTED — CANNOT MEET PILOT DEADLINE. This application cannot continue.</div>
      )}
      <div className="grid-2">
        <section className="card card-pad stack">
          <h3>Startup profile</h3>
          <Profile startup={application.startup_profile || application.startup} />
        </section>
        <section className="card card-pad stack">
          <h3>Documents</h3>
          {(application.documents || []).length === 0 && <div className="small">No documents linked.</div>}
          {(application.documents || []).map((doc) => (
            <div key={doc.id} className="card-title">
              <div>
                <b>{doc.name}</b>
                <div className="small">{doc.document_type_label} · expiry {doc.no_expiry ? "no expiry" : doc.expiry_date || "—"}</div>
              </div>
              <span style={{ display: "flex", gap: 6 }}>
                <Badge value={doc.verification_status} />
                <Button variant="ghost" onClick={() => downloadAuth(doc.download_url, doc.file_name)}>Open</Button>
              </span>
            </div>
          ))}
        </section>
      </div>

      {mode !== "startup" && (
        <section className="card card-pad stack">
          <div className="card-title">
            <h3>Proposal analysis</h3>
            <span className="ring-label"><GreenRing value={result.ai_score || 0} /><AILabel /></span>
          </div>
          <AIBanner demo={ai.demo} notice={ai.notice}>
            <p><b>Solution summary.</b> {result.solution_summary}</p>
            <p><b>Technical approach.</b> {result.technical_approach}</p>
            <p><b>Problem understanding.</b> {result.problem_understanding}</p>
          </AIBanner>
          <div className="grid-2">
            <div>
              <b>Requirement matches</b>
              <ul>{(result.matched_requirements || []).map((item) => <li key={item}>{item}</li>)}</ul>
            </div>
            <div>
              <b>Missing or unclear</b>
              <ul>{(result.missing_requirements || []).map((item) => <li key={item}>{item}</li>)}</ul>
              <b>Concerns</b>
              <ul>{(result.concerns || []).map((item) => <li key={item}>{item}</li>)}</ul>
            </div>
          </div>
          <div className="small">{result.experience_observations}</div>
          <div className="small">{result.document_observations}</div>
          <Button variant="ghost" onClick={async () => {
            try {
              await api("/ai/analyze-proposal/", { method: "POST", body: { application_id: application.id } });
              toast.push("Analysis refreshed");
              reload();
            } catch (error) { toast.push(error.message, "bad"); }
          }}>Refresh AI analysis</Button>
        </section>
      )}

      <section className="card card-pad stack">
        <h3>Proposal text</h3>
        <p style={{ whiteSpace: "pre-wrap" }}>{application.proposal_text || "No proposal text stored."}</p>
        {application.clarification_request && <div className="demo-banner">Clarification requested: {application.clarification_request}</div>}
        {application.clarification_response && <div className="small">Startup response: {application.clarification_response}</div>}
        {application.rejection_reason && <div className="small">Reason: {application.rejection_reason}</div>}
        {mode === "startup" && application.status === "CLARIFICATION_REQUIRED" && (
          <>
            <Field label="Your clarification"><textarea value={response} onChange={(e) => setResponse(e.target.value)} /></Field>
            <Button onClick={async () => {
              try {
                await api(`/applications/${application.id}/clarification-response/`, { method: "POST", body: { response } });
                toast.push("Clarification sent");
                reload();
              } catch (error) { toast.push(error.message, "bad"); }
            }}>Send response</Button>
          </>
        )}
      </section>

      {mode === "evaluator" && (
        <section className="card card-pad stack">
          <h3>Technical evaluation</h3>
          <div className="small">Score each category from 0 to 10. The decision buttons are yours. The model cannot approve, reject, or request clarification.</div>
          <div className="grid-2">
            {SCORE_FIELDS.map(([key, label]) => (
              <Field key={key} label={label}>
                <input type="number" min="0" max="10" step="1" value={scores[key] ?? ""} onChange={(e) => setScores({ ...scores, [key]: Number(e.target.value) })} />
              </Field>
            ))}
          </div>
          <Field label="Comments"><textarea value={comments} onChange={(e) => setComments(e.target.value)} /></Field>
          <div className="page-actions">
            <Button variant="ghost" onClick={() => save(null)}>Save scores</Button>
            <Button variant="good" onClick={() => save("APPROVE_FOR_PILOT")}>Approve for pilot</Button>
            <Button variant="ghost" onClick={() => save("REQUEST_CLARIFICATION")}>Request clarification</Button>
            <Button variant="danger" onClick={() => save("REJECT")}>Reject</Button>
          </div>
          {application.evaluation?.technical_score != null && <div className="small">Composite technical score: {application.evaluation.technical_score} / 100</div>}
        </section>
      )}
      <Disclaimer />
    </div>
  );
}

function Profile({ startup }) {
  if (!startup) return null;
  return (
    <div className="small">
      <div><b>{startup.company_name}</b> · {startup.domain}</div>
      <div>{startup.city}, {startup.state} · {startup.experience_years} years · team {startup.team_size}</div>
      <div>DPIIT {startup.dpiit_number || "—"} · GSTIN {startup.gstin || "—"}</div>
      <div>{startup.technologies}</div>
      <p>{startup.description}</p>
      {startup.relevant_experience && <p>{startup.relevant_experience}</p>}
    </div>
  );
}
