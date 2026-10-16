// ---------------------------------------------------------------------------
// Thin wrapper around the existing Flask API. No backend routes are changed
// here — this file only calls the endpoints already exposed by app.py.
// In dev, Vite proxies /api, /start-test and /stop-test to localhost:5000
// (see vite.config.js). In production, build this app and serve the static
// bundle from the same Flask host, so these relative paths keep working.
// ---------------------------------------------------------------------------

// Fired when the server says the session is gone (expired, or the line was
// removed from .env). App.jsx listens and sends the user back to the login page.
export const UNAUTHORIZED_EVENT = "pirani:unauthorized";
// Fired when the server has no production line selected for this session.
export const SELECT_LINE_EVENT = "pirani:select-line";

async function request(url, options = {}) {
  const { skipAuthRedirect, ...fetchOptions } = options;
  const res = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(fetchOptions.headers || {}),
    },
    ...fetchOptions,
  });
  if (res.status === 401 && !skipAuthRedirect) {
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  }
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      message = body.error || body.message || message;
      if (res.status === 409 && body.code === "line_not_selected") {
        window.dispatchEvent(new Event(SELECT_LINE_EVENT));
      }
    } catch {
      /* response wasn't JSON */
    }
    throw new Error(message);
  }
  return res.json();
}

// ---- Auth (credentials are checked by the backend against .env) ----
export const login = (username, password) =>
  request("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
    skipAuthRedirect: true, // a wrong password is a form error, not a lost session
  });
export const logout = () =>
  request("/api/auth/logout", { method: "POST", skipAuthRedirect: true });
export const getMe = () => request("/api/auth/me");
export const selectLine = (line) =>
  request("/api/auth/select-line", {
    method: "POST",
    body: JSON.stringify({ line }),
  });

// ---- Health / stats ----
export const getHealth = () => request("/api/health");
export const getTodayStats = () => request("/api/stats/today");

// ---- Material lookup (external system, display-only) ----
export const getMaterialByCode = (modelCode) =>
  request(`/api/material/${encodeURIComponent(modelCode)}`);

// ---- Test control ----
export const startTest = (payload) =>
  request("/start-test", { method: "POST", body: JSON.stringify(payload) });
export const stopTest = (gaugeId) =>
  request(`/stop-test/${gaugeId}`, { method: "POST" });

// ---- Fixtures (live floor view) ----
export const getFixtures = () => request("/api/fixtures");
export const getLiveVacuum = (slaveId) =>
  request(`/api/fixture-live/${slaveId}`);
export const getFixtureDetail = (slaveId) => request(`/api/fixture/${slaveId}`);
export const getModbusDiagnostics = () => request("/api/modbus/diagnostics");

// ---- Line configuration (read-only; lives in the server's .env) ----
// Returns only the line you are logged into.
export const getLinesConfig = () => request("/api/settings/lines");
export const testConnection = (payload) =>
  request("/api/settings/test-connection", {
    method: "POST",
    body: JSON.stringify(payload),
  });

/** Opens the server-sent events stream of fixture state. Returns the EventSource. */
export function openFixturesStream(onMessage, onError) {
  const es = new EventSource("/api/fixtures/stream");
  es.onmessage = (e) => {
    try {
      onMessage(JSON.parse(e.data));
    } catch {
      /* ignore malformed payloads */
    }
  };
  if (onError) es.onerror = onError;
  return es;
}

// ---- Reports ----
export function buildReportsQuery(params) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") qs.set(k, v);
  });
  return qs.toString();
}
export const getReports = (params) =>
  request(`/api/reports?${buildReportsQuery(params)}`);
export const getReportTrend = (testId) =>
  request(`/api/report/${encodeURIComponent(testId)}/trend`);
export const exportReportsUrl = (params) =>
  `/api/reports?${buildReportsQuery({ ...params, export: "excel" })}`;
export const reportPdfUrl = (testId) =>
  `/api/report/${encodeURIComponent(testId)}/pdf`;
