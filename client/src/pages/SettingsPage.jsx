import { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import {
  FiServer,
  FiSlash,
  FiRotateCw,
  FiLoader,
  FiClock,
  FiTarget,
  FiInfo,
  FiGlobe,
  FiAlertTriangle,
} from "react-icons/fi";
import { toast } from "react-hot-toast";
import { getLinesConfig, getModbusDiagnostics, testConnection } from "../api/client";
import StatusBadge from "../components/StatusBadge";
import { formatTime } from "../utils/time";

const DIAGNOSTICS_POLL_MS = 5000;

function usrKey(host, port) {
  return `${host}:${port}`;
}

const MODE_TEXT = {
  line_specific: "line-specific (each line has its own PC)",
  centralized: "centralized (this PC polls several lines)",
};

function Field({ label, children }) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="text-sm font-mono text-slate-800">{children || "—"}</dd>
    </div>
  );
}

/** Read-only view of the logged-in line's configuration and live health. The
 * values come from the server's .env file — to change anything, edit .env and
 * restart the app. */
export default function SettingsPage() {
  const isAdmin = useSelector((s) => s.auth.role === "Admin");
  const [line, setLine] = useState(null);
  const [loading, setLoading] = useState(true);
  const [diagnostics, setDiagnostics] = useState({});
  const [manualTests, setManualTests] = useState({}); // usrKey -> { status, reachable, error, gauges }

  useEffect(() => {
    // The server returns only the line you are logged into.
    getLinesConfig()
      .then((data) => setLine(data[0] || null))
      .catch(() => toast.error("Failed to load line configuration"))
      .finally(() => setLoading(false));
  }, []);

  // Live USR / gauge health, refreshed while this page is open.
  useEffect(() => {
    let mounted = true;
    const poll = () =>
      getModbusDiagnostics()
        .then((data) => {
          if (!mounted) return;
          const map = {};
          for (const u of data.gateways) map[usrKey(u.host, u.port)] = u;
          setDiagnostics(map);
        })
        .catch(() => {});
    poll();
    const t = setInterval(poll, DIAGNOSTICS_POLL_MS);
    return () => {
      mounted = false;
      clearInterval(t);
    };
  }, []);

  const handleTestHost = async (host, port, gauges) => {
    const key = usrKey(host, port);
    const slaveIds = gauges.filter((g) => g.enabled).map((g) => g.slave_id);
    setManualTests((m) => ({ ...m, [key]: { status: "testing" } }));
    try {
      const res = await testConnection({ host, port, slave_ids: slaveIds });
      setManualTests((m) => ({ ...m, [key]: { status: "done", ...res } }));
      if (!res.reachable) {
        toast.error(`${host}:${port} unreachable`);
      } else {
        const responding = (res.gauges || []).filter((g) => g.responding).length;
        toast.success(`${host}:${port} reachable — ${responding}/${res.gauges.length} responding`);
      }
    } catch (err) {
      setManualTests((m) => ({
        ...m,
        [key]: { status: "done", reachable: false, error: err.message, gauges: [] },
      }));
      toast.error(err.message);
    }
  };

  const usrs = line?.hosts || [];
  const gaugeCount = usrs.reduce((n, h) => n + h.gauges.length, 0);
  const enabledCount = usrs.reduce((n, h) => n + h.gauges.filter((g) => g.enabled).length, 0);
  const down = usrs.filter(
    (h) => h.enabled && diagnostics[usrKey(h.host, h.port)]?.connection_status === "disconnected"
  ).length;

  return (
    <main className="p-6 max-w-[1900px] mx-auto">
      <div className="mb-5">
        <h2 className="text-2xl font-semibold font-display">Line Configuration</h2>
        <p className="text-sm text-slate-400 mt-0.5">
          USR devices, gauges and live communication health for your production line.
        </p>
      </div>

      <div className="flex items-start gap-2 mb-5 px-4 py-3 rounded-lg bg-sky-50 border border-sky-200 text-sm text-sky-800">
        <FiInfo className="mt-0.5 shrink-0" />
        <span>
          This page is read-only. Gauge counts, USR addresses, limits and logins are set in the{" "}
          <code className="bg-sky-100 px-1 rounded">.env</code> file on the server — edit it and
          restart the app to apply changes.
        </span>
      </div>

      {line && line.polled_here === false && (
        <div className="flex items-start gap-2 mb-5 px-4 py-3 rounded-lg bg-amber-50 border border-amber-200 text-sm text-amber-800">
          <FiAlertTriangle className="mt-0.5 shrink-0" />
          <span>
            This PC does not poll <b>{line.line_label}</b> (polling mode:{" "}
            {MODE_TEXT[line.polling_mode] || line.polling_mode}). Live readings, tests and
            connection checks for this line are only available on the {line.line_label} line PC.
          </span>
        </div>
      )}

      {loading && (
        <div className="bg-white rounded-xl shadow p-8 text-center text-slate-400 text-sm">
          Loading line configuration…
        </div>
      )}

      {!loading && !line && (
        <div className="bg-white rounded-xl shadow p-10 text-center text-slate-500">
          Line configuration is unavailable.
        </div>
      )}

      {line && (
        <>
          <div className="bg-white rounded-xl shadow p-5 mb-4">
            <div className="flex items-center gap-2 mb-3">
              <FiGlobe className="text-slate-400" />
              <h3 className="font-semibold text-slate-800">Line network</h3>
              <span className="text-[11px] text-slate-400">
                polling: {MODE_TEXT[line.polling_mode] || line.polling_mode}
              </span>
            </div>
            <dl className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <Field label="Line subnet">{line.network.subnet}</Field>
              <Field label="PC (line side)">{line.network.pc_ip}</Field>
              <Field label="Router">{line.network.router_ip}</Field>
              <Field label="PC (company network)">{line.network.company_pc_ip}</Field>
              <Field label="Register map">{line.register_map}</Field>
            </dl>
          </div>

          <div className="bg-white rounded-xl shadow overflow-hidden">
            <div className="px-5 py-4 border-b bg-slate-50/60">
              <div className="flex items-center gap-2">
                <h3 className="font-semibold text-slate-800 text-base">{line.line_label}</h3>
                <span className="text-[11px] font-mono text-slate-400 bg-slate-200/70 px-1.5 py-0.5 rounded">
                  {line.line_key}
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1.5 text-xs text-slate-500">
                <span className="flex items-center gap-1">
                  <FiServer className="text-slate-400" />
                  {usrs.length} USR device{usrs.length === 1 ? "" : "s"}
                </span>
                <span>
                  {enabledCount}/{gaugeCount} gauges enabled
                </span>
                {line.upper_limit > 0 ? (
                  <span className="flex items-center gap-1 text-emerald-700 font-medium">
                    <FiTarget /> UL {line.upper_limit} mbar
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-rose-600 font-semibold">
                    <FiTarget /> Upper Limit not set — all tests will FAIL
                  </span>
                )}
                <span className="flex items-center gap-1">
                  <FiClock /> reading every {line.poll_interval_sec}s
                </span>
                {line.gap > 0 ? (
                  <span className="flex items-center gap-1 text-amber-600 font-medium">
                    <FiRotateCw /> IN/OUT gap {line.gap}
                  </span>
                ) : (
                  <span className="text-slate-400">IN/OUT auto-stop off</span>
                )}
                {line.reading_delay_sec > 0 && (
                  <span className="text-sky-600 font-medium">
                    {line.reading_delay_sec}s startup delay
                  </span>
                )}
                {line.min_duration_sec > 0 && (
                  <span className="text-indigo-600 font-medium">
                    min {line.min_duration_sec}s runtime
                  </span>
                )}
                {down > 0 && (
                  <span className="text-signal-fail font-medium">
                    {down} USR{down === 1 ? "" : "s"} disconnected
                  </span>
                )}
              </div>
            </div>

            <div className="p-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
              {usrs.map((h) => {
                const key = usrKey(h.host, h.port);
                const diag = diagnostics[key];
                const manualTest = manualTests[key];
                const manualByGauge = new Map(
                  (manualTest?.gauges || []).map((g) => [g.slave_id, g])
                );
                const canTest = isAdmin && h.enabled && line.polled_here;

                return (
                  <div
                    key={key}
                    className={`border rounded-lg overflow-hidden ${h.enabled ? "" : "opacity-60"}`}
                  >
                    <div className="flex items-center justify-between px-3 py-2 bg-slate-50 border-b gap-2">
                      <div className="min-w-0">
                        <div className="text-xs font-semibold text-slate-700 font-mono truncate flex items-center gap-1.5">
                          <FiServer className="text-slate-400 shrink-0" />
                          {h.usr_id}
                        </div>
                        <div className="text-[11px] text-slate-400 font-mono">
                          {h.host}:{h.port}
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        {h.enabled ? (
                          <>
                            <StatusBadge kind="connection" value={diag?.connection_status || "unknown"} />
                            <StatusBadge kind="polling" value={diag?.polling_status || "stopped"} />
                          </>
                        ) : (
                          <span className="text-[11px] font-semibold px-1.5 py-0.5 rounded bg-slate-200 text-slate-500">
                            Disabled
                          </span>
                        )}
                        {canTest && (
                          <button
                            type="button"
                            onClick={() => handleTestHost(h.host, h.port, h.gauges)}
                            disabled={manualTest?.status === "testing"}
                            title="Test connection now (admin)"
                            className="flex items-center gap-1 px-1.5 py-0.5 rounded border border-slate-300 bg-white hover:bg-slate-100 text-[11px] font-medium text-slate-500 disabled:opacity-60"
                          >
                            {manualTest?.status === "testing" ? (
                              <FiLoader className="animate-spin" />
                            ) : (
                              "Test"
                            )}
                          </button>
                        )}
                      </div>
                    </div>

                    {manualTest?.status === "done" && !manualTest.reachable && (
                      <p className="px-2.5 pt-2 text-[11px] text-rose-600">
                        Unreachable{manualTest.error ? `: ${manualTest.error}` : ""}
                      </p>
                    )}

                    {diag?.last_error && h.enabled && (
                      <p className="px-2.5 pt-2 text-[11px] text-rose-600">
                        Last error: {diag.last_error}{" "}
                        <span className="text-rose-400">({formatTime(diag.last_error_time)})</span>
                      </p>
                    )}

                    <div className="px-2.5 pt-2 text-[11px] text-slate-400">
                      Gauges {h.first_gauge}–{h.last_gauge} (slave ID = gauge number)
                      {diag?.last_cycle_at && <> · last poll {formatTime(diag.last_cycle_at)}</>}
                    </div>

                    <ul className="p-2.5 grid grid-cols-6 gap-1.5">
                      {h.gauges.map((g) => {
                        const tested = manualByGauge.get(g.slave_id);
                        const gs = diag?.gauges?.[g.slave_id];
                        let cls = "bg-slate-100 text-slate-400";
                        let title = `Gauge ${g.slave_id}`;
                        if (!g.enabled || !h.enabled) {
                          cls = "bg-slate-50 text-slate-300 line-through";
                          title += " — disabled";
                        } else if (tested) {
                          cls = tested.responding
                            ? "bg-emerald-100 text-emerald-700"
                            : "bg-rose-100 text-rose-600";
                          title += tested.responding
                            ? ` — reading ${tested.value ?? "—"}`
                            : ` — ${tested.communication_status || "no response"}`;
                        } else if (gs?.freshness === "valid") {
                          cls = "bg-emerald-50 text-emerald-700";
                          title += ` — reading ${gs.value}`;
                        } else if (gs?.freshness === "stale") {
                          cls = "bg-amber-50 text-amber-700";
                          title += ` — stale (${gs.communication_status || "no recent reading"})`;
                        } else if (gs?.communication_status) {
                          cls = "bg-rose-50 text-rose-500";
                          title += ` — ${gs.communication_status}`;
                        }
                        return (
                          <li
                            key={g.slave_id}
                            title={title}
                            className={`flex items-center justify-center gap-0.5 h-7 rounded text-xs font-mono ${cls}`}
                          >
                            {(!g.enabled || !h.enabled) && <FiSlash className="text-[9px]" />}
                            {g.slave_id}
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}
    </main>
  );
}
