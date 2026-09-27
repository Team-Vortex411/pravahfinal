import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { api, getToken, setToken } from "../services/api";

const AuthContext = createContext(null);
const ToastContext = createContext(null);

export function AppState({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  const [toasts, setToasts] = useState([]);

  useEffect(() => {
    if (!getToken()) {
      setReady(true);
      return;
    }
    api("/auth/me/")
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setReady(true));
  }, []);

  const auth = useMemo(
    () => ({
      user,
      ready,
      async login(email, password) {
        const data = await api("/auth/login/", { method: "POST", body: { email, password } });
        setToken(data.token);
        setUser(data.user);
        return data.user;
      },
      async logout() {
        try { await api("/auth/logout/", { method: "POST" }); } catch { /* token may already be gone */ }
        setToken(null);
        setUser(null);
      },
      setUser,
    }),
    [user, ready]
  );

  const toast = useMemo(
    () => ({
      push(message, tone = "ok") {
        const id = `${Date.now()}-${Math.random()}`;
        setToasts((items) => [...items, { id, message, tone }]);
        setTimeout(() => setToasts((items) => items.filter((item) => item.id !== id)), 4600);
      },
    }),
    []
  );

  return (
    <AuthContext.Provider value={auth}>
      <ToastContext.Provider value={toast}>
        {children}
        <div className="toasts">
          {toasts.map((item) => (
            <div key={item.id} className={`toast ${item.tone === "bad" ? "bad" : ""}`}>{item.message}</div>
          ))}
        </div>
      </ToastContext.Provider>
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
export function useToast() {
  return useContext(ToastContext);
}
