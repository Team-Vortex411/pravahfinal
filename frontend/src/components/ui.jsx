import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { TONE, labelize } from "../services/api";

export function Logo({ light = false, compact = false }) {
  const ink = light ? "#f4e7c1" : "#0b1f3a";
  const gold = "#c9a227";
  return (
    <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
      <svg width="42" height="42" viewBox="0 0 64 64" aria-hidden="true">
        <circle cx="32" cy="32" r="30" fill={light ? "#0b1f3a" : "#06101c"} stroke={gold} strokeWidth="2.5" />
        <circle cx="32" cy="32" r="24" fill="none" stroke={gold} strokeOpacity="0.55" />
        <path d="M14 34c6-8 8-8 12 0s6 8 12 0 6-8 12 0" fill="none" stroke={gold} strokeWidth="2.4" strokeLinecap="round" />
        <path d="M16 40c6-6 8-6 10 0s6 6 10 0 6-6 12 0" fill="none" stroke="#ff9933" strokeWidth="1.6" strokeLinecap="round" />
        <path d="M18 28c5-5 7-5 9 0s5 5 9 0 5-5 10 0" fill="none" stroke="#138808" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
      {!compact && (
        <div>
          <div className="serif" style={{ fontWeight: 700, letterSpacing: "0.14em", color: ink, fontSize: 18 }}>PRAVAH</div>
          <div style={{ fontSize: 11, color: light ? "#d7e2ef" : "#5c6b7a" }}>प्रवाह · Innovation Procurement</div>
        </div>
      )}
    </div>
  );
}

export function Badge({ value }) {
  if (!value) return null;
  const tone = TONE[value] || "navy";
  return <span className={`badge tone-${tone}`}><i />{labelize(value)}</span>;
}

export function AILabel() {
  return <span className="ai-pill">AI assisted</span>;
}

export function AIBanner({ demo, notice, children }) {
  return (
    <div className="stack">
      {demo && <div className="demo-banner">Demo AI Analysis. {notice || "AI service unavailable. Showing demo analysis so the prototype remains functional."}</div>}
      <div className="ai-banner">
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: 6 }}>
          <strong>Decision support only</strong>
          <AILabel />
        </div>
        <div>This is an AI-assisted recommendation and not an automatic selection decision.</div>
        {children}
      </div>
    </div>
  );
}

export function GreenRing({ value = 0, size = 74 }) {
  const pct = Math.max(0, Math.min(100, Number(value) || 0));
  const r = 28;
  const c = 2 * Math.PI * r;
  return (
    <svg width={size} height={size} viewBox="0 0 72 72" aria-label={`AI match ${pct}%`}>
      <circle cx="36" cy="36" r={r} stroke="#e6e1d6" strokeWidth="6" fill="none" />
      <circle
        cx="36"
        cy="36"
        r={r}
        stroke="#138808"
        strokeWidth="6"
        fill="none"
        strokeDasharray={`${(c * pct) / 100} ${c}`}
        strokeLinecap="round"
        transform="rotate(-90 36 36)"
      />
      <text x="36" y="40" textAnchor="middle" fontSize="13" fontWeight="700" fill="#0b1f3a">{Math.round(pct)}%</text>
    </svg>
  );
}

export function Page({ kicker, title, lede, actions, children }) {
  return (
    <div className="page">
      <header className="page-head">
        <div>
          {kicker && <div className="kicker">{kicker}</div>}
          <h1>{title}</h1>
          {lede && <p>{lede}</p>}
        </div>
        {actions && <div className="page-actions">{actions}</div>}
      </header>
      {children}
    </div>
  );
}

export function Button({ to, variant = "primary", children, className = "", ...props }) {
  const classes = `btn btn-${variant} ${className}`.trim();
  if (to) return <Link to={to} className={classes} {...props}>{children}</Link>;
  return <button className={classes} {...props}>{children}</button>;
}

export function Field({ label, hint, children }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}

export function Modal({ title, children, onClose }) {
  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal" onClick={(event) => event.stopPropagation()}>
        <div className="card-title">
          <h3>{title}</h3>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>Close</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function useLoad(loader, deps = []) {
  const [state, setState] = useState({ loading: true, data: null, error: "" });
  const reload = () => {
    setState((prev) => ({ ...prev, loading: !prev.data, error: "" }));
    return Promise.resolve()
      .then(loader)
      .then((data) => setState({ loading: false, data, error: "" }))
      .catch((error) => setState({ loading: false, data: null, error: error.message }));
  };
  useEffect(() => { reload(); }, deps);
  return { ...state, reload, setData: (data) => setState({ loading: false, data, error: "" }) };
}

export function Loading({ label = "Loading the register…" }) {
  return <div className="card card-pad muted">{label}</div>;
}
export function ErrorNote({ error }) {
  if (!error) return null;
  return <div className="demo-banner">{error}</div>;
}

export function Empty({ children }) {
  return <div className="card card-pad muted">{children}</div>;
}

export function Stat({ value, label }) {
  return <div className="card stat"><b>{value}</b><span>{label}</span></div>;
}

export function Timeline({ items = [] }) {
  return (
    <div className="timeline">
      {items.map((item) => (
        <div key={item.key || item.label} className={`t-step ${item.state || ""}`}>
          <div className="bar" />
          <strong>{item.label}</strong>
          {item.at && <div className="small">{String(item.at).slice(0, 10)}</div>}
          {item.detail && <div className="small">{item.detail}</div>}
        </div>
      ))}
    </div>
  );
}

export function Disclaimer() {
  return <div className="small">Final award rests with the competent government authority. Scores and AI notes are decision-support only.</div>;
}
