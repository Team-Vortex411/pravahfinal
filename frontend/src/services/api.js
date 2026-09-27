const TOKEN_KEY = "pravah_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export async function api(path, { method = "GET", body, form } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Token ${token}`;
  let payload;
  if (form) payload = form;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const response = await fetch(`/api${path}`, { method, headers, body: payload });
  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text || "Unexpected response" };
  }
  if (!response.ok) {
    const error = new Error(data?.detail || "The request could not be completed.");
    error.status = response.status;
    error.data = data;
    throw error;
  }
  return data;
}

export async function downloadAuth(path, filename) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Token ${token}`;
  const response = await fetch(path, { headers });
  if (!response.ok) throw new Error("The file could not be downloaded.");
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename || "pravah-document.pdf";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export const HOME = {
  GOVERNMENT_ADMIN: "/government/dashboard",
  TECHNICAL_EVALUATOR: "/evaluator/dashboard",
  PROCUREMENT_OFFICER: "/procurement/dashboard",
  FIELD_EVALUATOR: "/field/dashboard",
  STARTUP: "/startup/dashboard",
};

export function inr(value) {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(value || 0);
}

export function when(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 10);
  return date.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

export const TONE = {
  OPEN: "info",
  SUBMITTED: "navy",
  ELIGIBILITY_CHECK: "info",
  UNDER_TECHNICAL_EVALUATION: "info",
  CLARIFICATION_REQUIRED: "warn",
  APPROVED_FOR_PILOT: "good",
  REJECTED: "danger",
  REJECTED_DEADLINE: "danger",
  CONTRACT_PENDING: "gold",
  CONTRACT_ACCEPTED: "good",
  PILOT_ACTIVE: "good",
  ACTIVE: "good",
  PILOT_COMPLETED: "navy",
  COMPLETED: "navy",
  PILOT_CANCELLED: "danger",
  CANCELLED: "danger",
  DRAFT: "navy",
  SENT: "gold",
  VERIFIED_VALID: "good",
  EXPIRING_SOON: "warn",
  EXPIRED: "danger",
  PENDING_VERIFICATION: "navy",
  VERIFIED: "good",
  NEEDS_CLARIFICATION: "warn",
  NOT_VERIFIED: "danger",
  LATE: "warn",
  PENDING: "navy",
  OPEN_COMPLAINT: "warn",
  MUST_HAVE: "danger",
  BETTER_TO_HAVE: "warn",
  NICE_TO_HAVE: "info",
};

export function labelize(value) {
  return String(value || "—").replaceAll("_", " ");
}
