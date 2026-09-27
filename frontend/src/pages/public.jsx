import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Logo, Badge, Button, Loading, Page } from "../components/ui";
import { api, HOME } from "../services/api";
import { useAuth, useToast } from "../context/AppState";

function PublicFrame({ children }) {
  return (
    <div>
      <div className="tricolor"><i /><i /><i /></div>
      <header className="public-header">
        <Link to="/" style={{ textDecoration: "none" }}><Logo /></Link>
        <nav className="public-nav">
          <Link to="/problem-statements">Problem statements</Link>
          <Link to="/login">Sign in</Link>
          <Button to="/login" variant="gold">Enter demo workspace</Button>
        </nav>
      </header>
      {children}
      <footer className="content small">
        PRAVAH is a decision-support prototype for innovation procurement. It does not award contracts.
        Final award rests with the competent government authority. The lion capital is not used; the seal is an original flow mark.
      </footer>
    </div>
  );
}

const STEPS = [
  ["01", "Problem statement", "A department records the public problem, eligibility, documents and the pilot joining deadline."],
  ["02", "Startup discovery", "Embeddings match a startup profile to the problem. The score is a recommendation, not a selection."],
  ["03", "Verification", "Documents are checked, dated, and allowed to expire. An expired file cannot support a new application."],
  ["04", "Technical evaluation", "A person scores feasibility and decides. The model may summarise. It may not approve."],
  ["05", "Pilot and field check", "Weekly evidence is verified in the field. The evaluator's personal identity is not shown to the startup."],
  ["06", "Score and recommendation", "Verified KPIs are scored by formula. Government reviews the file and decides."],
];

export function Home() {
  const [problems, setProblems] = useState([]);
  useEffect(() => { api("/problem-statements/").then((rows) => setProblems(rows.slice(0, 4))).catch(() => {}); }, []);
  return (
    <PublicFrame>
      <section className="hero">
        <div className="hero-inner">
          <div className="kicker">Government of India · Innovation Procurement Cell</div>
          <h1>From public problem to proven solution.</h1>
          <div className="gold-rule" />
          <p className="lede">PRAVAH connects a government problem to a measured pilot. AI assists. Rules check. Humans verify. Government decides. Demonstration password: demo123.</p>
          <div className="page-actions" style={{ marginTop: 22 }}>
            <Button to="/login" variant="gold">Enter demo workspace</Button>
            <Button to="/problem-statements" variant="ghost" style={{ color: "white", borderColor: "rgba(255,255,255,0.3)" }}>Browse problem statements</Button>
          </div>
        </div>
      </section>
      <div className="content" style={{ marginTop: -36 }}>
        <div className="grid-4">
          <Snap n="8" l="Problem statements" />
          <Snap n="42" l="Applications" />
          <Snap n="5" l="Active pilots" />
          <Snap n="11" l="Pending evaluations" />
        </div>
        <p className="small" style={{ marginTop: 8 }}>Illustrative programme snapshot for the public landing. The demonstration workspace uses a fully worked dataset and shows its own live counts after sign-in.</p>
        <section style={{ marginTop: 28 }}>
          <div className="kicker">Lifecycle</div>
          <h2 className="serif" style={{ fontSize: 32, margin: "6px 0 14px" }}>Six steps, one file.</h2>
          <div className="steps">
            {STEPS.map(([n, title, text]) => (
              <article key={n} className="card step">
                <em>{n}</em>
                <h3 style={{ margin: "8px 0" }}>{title}</h3>
                <p className="small">{text}</p>
              </article>
            ))}
          </div>
        </section>
        <section className="card card-pad" style={{ marginTop: 22 }}>
          <div className="kicker">Operating principle</div>
          <div className="principle" style={{ marginTop: 10 }}>
            <span>AI assists</span> → <span>Rules check</span> → <span>Humans verify</span> → <span>Verified data is scored</span> → <span>Government decides</span>
          </div>
        </section>
        <section style={{ marginTop: 22 }}>
          <div className="card-title"><h2 className="serif">Open problems</h2><Link to="/problem-statements">View all</Link></div>
          <div className="grid-2">
            {problems.map((ps) => <ProblemCard key={ps.id} ps={ps} />)}
          </div>
        </section>
      </div>
    </PublicFrame>
  );
}

function Snap({ n, l }) {
  return <div className="card stat"><b>{n}</b><span>{l}</span></div>;
}

export function ProblemCard({ ps }) {
  return (
    <Link to={`/problem-statements/${ps.id}`} className="card card-pad" style={{ textDecoration: "none" }}>
      <div className="card-title">
        <span className="kicker">{ps.code}</span>
        <Badge value={ps.status} />
      </div>
      <h3>{ps.title}</h3>
      <p className="small">{ps.department?.name} · {ps.location} · {ps.technology_domain}</p>
      <p>{ps.description}</p>
      <div className="small">Apply by {ps.application_deadline} · Pilot join by {ps.pilot_joining_deadline}</div>
    </Link>
  );
}

export function ProblemList() {
  const [rows, setRows] = useState(null);
  const [q, setQ] = useState("");
  useEffect(() => { api("/problem-statements/").then(setRows).catch(() => setRows([])); }, []);
  const filtered = (rows || []).filter((ps) => `${ps.title} ${ps.location} ${ps.technology_domain}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <PublicFrame>
      <div className="content">
        <Page kicker="Public register" title="Problem statements" lede="Published problems from the innovation procurement cell. Signing in as a startup adds an AI-assisted match score." actions={<input className="search" placeholder="Search title, place, domain" value={q} onChange={(e) => setQ(e.target.value)} />} />
        {!rows && <Loading />}
        <div className="grid-2">{filtered.map((ps) => <ProblemCard key={ps.id} ps={ps} />)}</div>
      </div>
    </PublicFrame>
  );
}

export function ProblemDetail() {
  const { id } = useParams();
  const [ps, setPs] = useState(null);
  useEffect(() => { api(`/problem-statements/${id}/`).then(setPs).catch(() => setPs(false)); }, [id]);
  if (ps === false) return <PublicFrame><div className="content">Problem statement not found.</div></PublicFrame>;
  if (!ps) return <PublicFrame><div className="content"><Loading /></div></PublicFrame>;
  return (
    <PublicFrame>
      <div className="content stack">
        <Page kicker={ps.code} title={ps.title} lede={ps.description} actions={<Button to="/login">Sign in to apply</Button>} />
        <div style={{ display: "flex", gap: 8 }}><Badge value={ps.status} /><span className="small">{ps.department?.name} · {ps.location}</span></div>
        <div className="grid-2">
          <article className="card card-pad stack">
            <h3>Expected outcome</h3>
            <p>{ps.expected_outcome}</p>
            <h3>Technical requirements</h3>
            <ul>{ps.technical_requirements.map((item) => <li key={item}>{item}</li>)}</ul>
          </article>
          <article className="card card-pad stack">
            <h3>Eligibility and documents</h3>
            <ul>{ps.eligibility_criteria.map((item) => <li key={item}>{item}</li>)}</ul>
            <div className="small">Required documents: {ps.required_documents.join(", ")}</div>
            <div className="small">Application deadline {ps.application_deadline}. Pilot joining deadline {ps.pilot_joining_deadline}. Location: {ps.pilot_location}. Duration {ps.pilot_duration_weeks} weeks.</div>
          </article>
        </div>
      </div>
    </PublicFrame>
  );
}

export function Login() {
  const { login } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [accounts, setAccounts] = useState(null);
  const [email, setEmail] = useState("admin@gov.in");
  const [password, setPassword] = useState("demo123");
  useEffect(() => { api("/demo-accounts/").then(setAccounts).catch(() => setAccounts({ featured: [] })); }, []);

  async function submit(event, nextEmail, nextPassword) {
    event?.preventDefault();
    try {
      const user = await login(nextEmail || email, nextPassword || password);
      navigate(HOME[user.role] || "/");
    } catch (error) {
      toast.push(error.message, "bad");
    }
  }

  return (
    <PublicFrame>
      <div className="content" style={{ maxWidth: 980, margin: "0 auto" }}>
        <Page kicker="Demonstration access" title="Enter the workspace" lede="Password for every demonstration account is demo123. These are not production credentials." />
        <div className="grid-2">
          <form className="card card-pad stack" onSubmit={submit}>
            <label className="field">Email<input value={email} onChange={(e) => setEmail(e.target.value)} /></label>
            <label className="field">Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
            <Button type="submit">Sign in</Button>
            <Link to="/register">Register a startup</Link>
          </form>
          <div className="stack">
            {(accounts?.featured || []).map((account) => (
              <button key={account.email} className="card card-pad" style={{ textAlign: "left", cursor: "pointer" }} onClick={(e) => submit(e, account.email, account.password)}>
                <div className="kicker">{account.role_label}</div>
                <strong>{account.name}</strong>
                <div className="small">{account.email} · {account.blurb}</div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </PublicFrame>
  );
}

export function Register() {
  const { setUser } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    company_name: "", domain: "", technologies: "", city: "", state: "", contact_person: "", email: "", password: "demo123",
    dpiit_number: "", experience_years: 1, team_size: 5, description: "",
  });
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });
  return (
    <PublicFrame>
      <div className="content" style={{ maxWidth: 820, margin: "0 auto" }}>
        <Page kicker="Startup registration" title="Create a startup profile" lede="Registration stores the profile and a 384-dimensional embedding for problem matching." />
        <form className="card card-pad grid-2" onSubmit={async (e) => {
          e.preventDefault();
          try {
            const data = await api("/auth/register/", { method: "POST", body: form });
            localStorage.setItem("pravah_token", data.token);
            setUser(data.user);
            toast.push("Profile created. Embedding stored.");
            navigate("/startup/dashboard");
          } catch (error) { toast.push(error.message, "bad"); }
        }}>
          {[
            ["company_name", "Company name"], ["contact_person", "Contact person"], ["email", "Email"], ["password", "Password"],
            ["domain", "Domain"], ["technologies", "Technologies"], ["city", "City"], ["state", "State"],
            ["dpiit_number", "DPIIT number"], ["experience_years", "Experience years"], ["team_size", "Team size"],
          ].map(([key, label]) => (
            <label key={key} className="field">{label}<input value={form[key]} onChange={set(key)} required={!["dpiit_number"].includes(key)} /></label>
          ))}
          <label className="field" style={{ gridColumn: "1 / -1" }}>Description<textarea value={form.description} onChange={set("description")} /></label>
          <Button type="submit">Register</Button>
        </form>
      </div>
    </PublicFrame>
  );
}
