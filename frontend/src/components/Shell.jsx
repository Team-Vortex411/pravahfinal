import { useEffect, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import {
  Bell, ClipboardCheck, FileStack, FolderOpen, LayoutDashboard, LogOut, MapPinned,
  Menu, Scale, ScrollText, TriangleAlert, Users, X,
} from "lucide-react";
import { Logo } from "./ui";
import { useAuth } from "../context/AppState";
import { api } from "../services/api";

const NAV = {
  GOVERNMENT_ADMIN: [
    ["/government/dashboard", "Dashboard", LayoutDashboard],
    ["/government/problem-statements", "Problem statements", ScrollText],
    ["/government/applications", "Applications", FileStack],
    ["/government/startups", "Startups", Users],
    ["/government/alerts", "Alerts", TriangleAlert],
    ["/government/employees", "Employees", ClipboardCheck],
  ],
  TECHNICAL_EVALUATOR: [
    ["/evaluator/dashboard", "Dashboard", LayoutDashboard],
    ["/evaluator/applications", "Applications", FileStack],
    ["/evaluator/documents", "Documents", FolderOpen],
    ["/evaluator/evaluations", "Evaluations", Scale],
  ],
  PROCUREMENT_OFFICER: [
    ["/procurement/dashboard", "Dashboard", LayoutDashboard],
    ["/procurement/pilots", "Pilots", MapPinned],
    ["/procurement/recommendations", "Recommendations", Scale],
  ],
  FIELD_EVALUATOR: [
    ["/field/dashboard", "Dashboard", LayoutDashboard],
    ["/field/pilots", "Assigned pilots", MapPinned],
    ["/field/complaints", "Complaints", TriangleAlert],
  ],
  STARTUP: [
    ["/startup/dashboard", "Dashboard", LayoutDashboard],
    ["/startup/profile", "Profile", Users],
    ["/startup/documents", "Documents", FolderOpen],
    ["/startup/problem-statements", "Problem statements", ScrollText],
    ["/startup/applications", "Applications", FileStack],
    ["/startup/pilots", "Pilots", MapPinned],
  ],
};

export default function Shell({ children }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [notes, setNotes] = useState([]);
  const [showNotes, setShowNotes] = useState(false);
  const items = NAV[user?.role] || [];

  async function loadNotes() {
    try { setNotes(await api("/notifications/")); } catch { setNotes([]); }
  }
  useEffect(() => { loadNotes(); }, [user?.id]);

  return (
    <div>
      <div className="tricolor"><i /><i /><i /></div>
      <div className="shell">
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <Logo light />
        <div className="small" style={{ color: "#b7c6d8", padding: "0 8px" }}>{user?.role_label}</div>
        <nav>
          {items.map(([to, label, Icon]) => (
            <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "active" : "")} onClick={() => setOpen(false)}>
              <Icon size={16} /> {label}
            </NavLink>
          ))}
        </nav>
        <div style={{ marginTop: "auto" }} className="card-pad">
          <div style={{ fontWeight: 650 }}>{user?.name}</div>
          <div className="small" style={{ color: "#b7c6d8" }}>{user?.email}</div>
          <button className="btn btn-ghost btn-sm" style={{ marginTop: 10, color: "white", borderColor: "#34506e" }} onClick={async () => { await logout(); navigate("/login"); }}>
            <LogOut size={14} /> Sign out
          </button>
        </div>
      </aside>
      <div className="main-col">
        <header className="topbar">
          <button className="btn btn-ghost btn-sm" onClick={() => setOpen((v) => !v)} aria-label="Menu">
            {open ? <X size={16} /> : <Menu size={16} />} Menu
          </button>
          <div className="small">AI assists → Rules check → Humans verify → Government decides</div>
          <button className="btn btn-ghost btn-sm" onClick={() => { setShowNotes((v) => !v); loadNotes(); }}>
            <Bell size={15} /> {notes.filter((n) => !n.is_read).length || ""}
          </button>
        </header>
        {showNotes && (
          <div className="card" style={{ margin: "8px 22px 0", position: "relative", zIndex: 15 }}>
            <div className="card-pad stack">
              <strong>Notifications</strong>
              {notes.length === 0 && <div className="small">No notifications.</div>}
              {notes.slice(0, 8).map((note) => (
                <button key={note.id} className="btn btn-ghost" style={{ justifyContent: "space-between" }} onClick={async () => {
                  await api(`/notifications/${note.id}/read/`, { method: "POST" });
                  if (note.link) navigate(note.link);
                  setShowNotes(false);
                  loadNotes();
                }}>
                  <span style={{ textAlign: "left" }}>
                    <b>{note.title}</b>
                    <div className="small">{note.body}</div>
                  </span>
                  {!note.is_read && <BadgeDot />}
                </button>
              ))}
            </div>
          </div>
        )}
        <main className="content">{children}</main>
      </div>
    </div>
    </div>
  );
}

function BadgeDot() {
  return <span style={{ width: 8, height: 8, borderRadius: 99, background: "#c9a227", display: "inline-block" }} />;
}

export function Guard({ roles, children }) {
  const { user, ready } = useAuth();
  const navigate = useNavigate();
  useEffect(() => {
    if (!ready) return;
    if (!user) navigate("/login");
    else if (roles && !roles.includes(user.role)) navigate("/");
  }, [ready, user]);
  if (!ready || !user) return <div className="content">Checking session…</div>;
  if (roles && !roles.includes(user.role)) return null;
  return <Shell>{children}</Shell>;
}
