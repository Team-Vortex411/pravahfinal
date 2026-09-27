import { Link, useParams } from "react-router-dom";
import PilotWorkspace from "../components/PilotWorkspace";
import { Badge, Loading, Page, Stat, useLoad } from "../components/ui";
import { api } from "../services/api";

export function FieldDashboard() {
  const state = useLoad(() => api("/pilots/"));
  const complaints = useLoad(() => api("/complaints/"));
  if (state.loading) return <Loading />;
  const pilots = state.data || [];
  const pending = pilots.filter((p) => p.status === "ACTIVE");
  return (
    <Page kicker="Field evaluator" title="Field desk" lede="Your personal name is not shown to the startup. The file shows only “Assigned Field Evaluator”.">
      <div className="grid-4">
        <Stat value={pilots.length} label="Assigned pilots" />
        <Stat value={pending.length} label="Active" />
        <Stat value={(complaints.data || []).length} label="Complaints you can see" />
        <Stat value={pilots.filter((p) => p.status === "COMPLETED").length} label="Final reports in history" />
      </div>
      <div className="card table-wrap">
        <table className="data">
          <thead><tr><th>Pilot</th><th>Startup</th><th>Location</th><th>Status</th></tr></thead>
          <tbody>
            {pilots.map((pilot) => (
              <tr key={pilot.id}>
                <td><Link to={`/field/pilots/${pilot.id}`}>{pilot.code}</Link></td>
                <td>{pilot.startup?.company_name}</td>
                <td>{pilot.location}</td>
                <td><Badge value={pilot.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Page>
  );
}

export function FieldPilots() {
  return <FieldDashboard />;
}

export function FieldPilotDetail() {
  const { id } = useParams();
  const state = useLoad(() => api(`/pilots/${id}/`), [id]);
  if (state.loading) return <Loading />;
  return <PilotWorkspace pilot={state.data} reload={state.reload} mode="field" />;
}

export function FieldReports() {
  return <FieldPilotDetail />;
}
export function FieldVerification() {
  return <FieldPilotDetail />;
}

export function FieldComplaints() {
  const state = useLoad(() => api("/complaints/"));
  if (state.loading) return <Loading />;
  return (
    <Page kicker="Field file" title="Complaints">
      {(state.data || []).map((item) => (
        <article key={item.id} className="card card-pad">
          <div className="card-title"><b>{item.category}</b><Badge value={item.status} /></div>
          <p>{item.description}</p>
          <div className="small">{item.startup} · {item.pilot_code}. The startup does not see your name.</div>
          <Link to={`/field/pilots/${item.pilot_id}`}>Open pilot</Link>
        </article>
      ))}
    </Page>
  );
}
