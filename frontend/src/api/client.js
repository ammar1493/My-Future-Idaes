// Thin API client. Token is kept in localStorage and attached to every call.
// In local dev API_BASE is "" and Vite proxies /api -> :8000. In production
// (e.g. Vercel) set VITE_API_BASE to the backend's URL.
const API_BASE = import.meta.env.VITE_API_BASE || "";
const TOKEN_KEY = "livetrain_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(t) {
  if (t) localStorage.setItem(TOKEN_KEY, t);
  else localStorage.removeItem(TOKEN_KEY);
}

async function request(path, { method = "GET", body, form } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let payload;
  if (form) {
    payload = new URLSearchParams(form).toString();
    headers["Content-Type"] = "application/x-www-form-urlencoded";
  } else if (body !== undefined) {
    payload = JSON.stringify(body);
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(`${API_BASE}/api${path}`, { method, headers, body: payload });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `Request failed (${res.status})`);
  }
  return res.status === 204 ? null : res.json();
}

export const api = {
  config: () => request("/config"),
  login: (email, password) =>
    request("/auth/login", { method: "POST", form: { username: email, password } }),
  register: (data) => request("/auth/register", { method: "POST", body: data }),
  me: () => request("/auth/me"),

  joinToken: (roomId) => request(`/rooms/${roomId}/join-token`, { method: "POST" }),

  courses: () => request("/courses"),
  createCourse: (data) => request("/courses", { method: "POST", body: data }),
  courseStudents: (id) => request(`/courses/${id}/students`),

  sessions: (params = "") => request(`/sessions${params}`),
  createSession: (data) => request("/sessions", { method: "POST", body: data }),
  startSession: (id) => request(`/sessions/${id}/start`, { method: "POST" }),
  endSession: (id) => request(`/sessions/${id}/end`, { method: "POST" }),
  sessionAttendance: (id, recompute = false) =>
    request(`/sessions/${id}/attendance${recompute ? "?recompute=true" : ""}`),

  dashboardSummary: () => request("/dashboard/summary"),
};
