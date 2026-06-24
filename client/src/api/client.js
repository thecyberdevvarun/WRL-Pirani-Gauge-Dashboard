// ---------------------------------------------------------------------------
// Thin wrapper around the existing Flask API. No backend routes are changed
// here — this file only calls the endpoints already exposed by app.py.
// In dev, Vite proxies /api, /start-test and /stop-test to localhost:5000
// (see vite.config.js). In production, build this app and serve the static
// bundle from the same Flask host, so these relative paths keep working.
// ---------------------------------------------------------------------------

async function request(url, options = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      message = body.error || body.message || message;
    } catch {
      /* response wasn't JSON */
    }
    throw new Error(message);
  }
  return res.json();
}

// ---- Health / stats ----
export const getHealth = () => request("/api/health");
export const getTodayStats = () => request("/api/stats/today");

// ---- Recipes ----
export const getRecipeByModel = (modelCode) => request(`/api/recipe/${encodeURIComponent(modelCode)}`);
export const listRecipes = () => request("/api/recipes");
export const saveRecipe = (payload) =>
  request("/api/recipes", { method: "POST", body: JSON.stringify(payload) });
export const deleteRecipe = (modelCode) =>
  request(`/api/recipes/${encodeURIComponent(modelCode)}`, { method: "DELETE" });

// ---- Test control ----
export const startTest = (payload) =>
  request("/start-test", { method: "POST", body: JSON.stringify(payload) });
export const stopTest = (gaugeId) =>
  request(`/stop-test/${gaugeId}`, { method: "POST" });
export const getActiveTests = () => request("/api/active-tests");

// ---- Fixtures (live floor view) ----
export const getFixtures = () => request("/api/fixtures");
export const getLiveVacuum = (slaveId) => request(`/api/fixture-live/${slaveId}`);
export const getFixtureDetail = (slaveId) => request(`/api/fixture/${slaveId}`);
export const getModbusDiagnostics = () => request("/api/modbus/diagnostics");

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
export const getReports = (params) => request(`/api/reports?${buildReportsQuery(params)}`);
export const getReportTrend = (testId) => request(`/api/report/${encodeURIComponent(testId)}/trend`);
export const exportReportsUrl = (params) => `/api/reports?${buildReportsQuery({ ...params, export: "excel" })}`;
