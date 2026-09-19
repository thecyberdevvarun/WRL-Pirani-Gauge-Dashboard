import { useEffect, useMemo, useState } from "react";
import { useDispatch } from "react-redux";
import {
  FiPlus,
  FiEdit2,
  FiTrash2,
  FiServer,
  FiSearch,
  FiWifi,
  FiWifiOff,
  FiHelpCircle,
  FiChevronDown,
  FiChevronUp,
  FiSlash,
  FiSliders,
  FiRotateCw,
  FiLoader,
  FiClock,
  FiTarget,
} from "react-icons/fi";
import { toast } from "react-hot-toast";
import LineConfigModal from "../components/LineConfigModal";
import ConfirmDialog from "../components/ConfirmDialog";
import {
  getLinesConfig,
  saveLine,
  deleteLine as deleteLineApi,
  getModbusDiagnostics,
  testConnection,
} from "../api/client";
import { fetchLines } from "../store/linesSlice";

const GAUGES_PREVIEW_COUNT = 10;
const DIAGNOSTICS_POLL_MS = 5000;

function hostKey(host, port) {
  return `${host}:${port}`;
}

/** "online" = at least one gauge on this gateway answered; "offline" = gateway
 * polled but nothing answered; "unknown" = no diagnostics yet (first load / no
 * enabled gauges on this host). */
function statusForHost(diagnostics, host, port) {
  const gw = diagnostics?.[hostKey(host, port)];
  if (!gw) return "unknown";
  if (gw.gauges_polled === 0) return "unknown";
  return gw.gauges_responding > 0 ? "online" : "offline";
}

const STATUS_STYLE = {
  online: { dot: "bg-signal-pass", text: "text-signal-pass", icon: FiWifi, label: "Online" },
  offline: { dot: "bg-signal-fail", text: "text-signal-fail", icon: FiWifiOff, label: "Unreachable" },
  unknown: { dot: "bg-slate-300", text: "text-slate-400", icon: FiHelpCircle, label: "Unknown" },
};

export default function SettingsPage() {
  const dispatch = useDispatch();
  const [lines, setLines] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [diagnostics, setDiagnostics] = useState({});
  const [expandedHosts, setExpandedHosts] = useState(() => new Set());
  const [modal, setModal] = useState({ open: false, mode: "add", initial: null });
  const [confirmTarget, setConfirmTarget] = useState(null); // line_key pending delete
  const [manualTests, setManualTests] = useState({}); // hostKey -> { status, reachable, error, gauges }

  const loadLines = () =>
    getLinesConfig()
      .then((data) => setLines(data))
      .catch(() => toast.error("Failed to load line settings"))
      .finally(() => setLoading(false));

  useEffect(() => {
    loadLines();
  }, []);

  // Live gateway reachability, polled while this page is open.
  useEffect(() => {
    let mounted = true;
    const poll = () =>
      getModbusDiagnostics()
        .then((data) => {
          if (!mounted) return;
          const map = {};
          for (const gw of data.gateways) map[hostKey(gw.host, gw.port)] = gw;
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

  // Matching by line name/key shows the whole line; matching by a specific
  // host IP or gauge narrows the card down to just that host, so searching
  // for one gateway actually finds it instead of just confirming its line.
  const filteredLines = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return lines;
    return lines
      .map((l) => {
        if (l.line_label.toLowerCase().includes(q) || l.line_key.toLowerCase().includes(q)) {
          return l;
        }
        const matchingHosts = l.hosts.filter(
          (h) =>
            h.host.toLowerCase().includes(q) ||
            h.gauges.some((g) => g.name.toLowerCase().includes(q) || String(g.slave_id) === q)
        );
        return matchingHosts.length ? { ...l, hosts: matchingHosts } : null;
      })
      .filter(Boolean);
  }, [lines, search]);

  const openAdd = () => setModal({ open: true, mode: "add", initial: null });
  const openEdit = (line) => setModal({ open: true, mode: "edit", initial: line });
  const closeModal = () => setModal({ open: false, mode: "add", initial: null });

  const toggleHostExpanded = (key) =>
    setExpandedHosts((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const handleTestHost = async (host, port, gauges) => {
    const key = hostKey(host, port);
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

  const handleSave = async (payload) => {
    try {
      await saveLine(payload);
      closeModal();
      loadLines();
      dispatch(fetchLines());
      toast.success(modal.mode === "edit" ? "Line updated" : "Line created");
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleDeleteConfirmed = async () => {
    const lineKey = confirmTarget;
    setConfirmTarget(null);
    try {
      await deleteLineApi(lineKey);
      loadLines();
      dispatch(fetchLines());
      toast.success("Line deleted");
    } catch (err) {
      toast.error(err.message);
    }
  };

  const confirmingLine = lines.find((l) => l.line_key === confirmTarget);

  return (
    <main className="p-6 max-w-[1900px] mx-auto">
      <div className="flex flex-wrap justify-between items-center gap-3 mb-5">
        <div>
          <h2 className="text-2xl font-semibold font-display">Line Settings</h2>
          <p className="text-sm text-slate-400 mt-0.5">
            Configure the Modbus gateways and gauges for each production line.
          </p>
        </div>
        <button
          type="button"
          onClick={openAdd}
          className="flex items-center gap-1.5 px-4 py-2 rounded bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-sm shadow-sm"
        >
          <FiPlus /> Add Line
        </button>
      </div>

      {!loading && lines.length > 0 && (
        <div className="relative w-80 mb-5">
          <FiSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search lines, hosts, or gauges…"
            aria-label="Search line settings"
            className="w-full pl-9 pr-3 py-2 border rounded focus:border-emerald-600 outline-none text-sm bg-white"
          />
        </div>
      )}

      {loading && (
        <div className="bg-white rounded-xl shadow p-8 text-center text-slate-400 text-sm">
          Loading line settings…
        </div>
      )}

      {!loading && lines.length === 0 && (
        <div className="bg-white rounded-xl shadow p-10 text-center">
          <FiSliders className="mx-auto text-4xl text-slate-300 mb-3" />
          <p className="text-slate-500 font-medium">No lines configured yet</p>
          <p className="text-sm text-slate-400 mt-1 mb-4">
            Add your first production line to start polling its Modbus gateways.
          </p>
          <button
            type="button"
            onClick={openAdd}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-sm"
          >
            <FiPlus /> Add Line
          </button>
        </div>
      )}

      {!loading && lines.length > 0 && filteredLines.length === 0 && (
        <div className="bg-white rounded-xl shadow p-8 text-center text-slate-400 text-sm">
          No lines, hosts, or gauges match "{search}".
        </div>
      )}

      <div className="space-y-4">
        {filteredLines.map((line) => {
          const gaugeCount = line.hosts.reduce((n, h) => n + h.gauges.length, 0);
          const enabledCount = line.hosts.reduce(
            (n, h) => n + h.gauges.filter((g) => g.enabled).length,
            0
          );
          const offlineHosts = line.hosts.filter(
            (h) => statusForHost(diagnostics, h.host, h.port) === "offline"
          ).length;

          return (
            <div key={line.line_key} className="bg-white rounded-xl shadow overflow-hidden">
              <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 border-b bg-slate-50/60">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-slate-800 text-base">{line.line_label}</h3>
                    <span className="text-[11px] font-mono text-slate-400 bg-slate-200/70 px-1.5 py-0.5 rounded">
                      {line.line_key}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1.5 text-xs text-slate-500">
                    <span className="flex items-center gap-1">
                      <FiServer className="text-slate-400" />
                      {line.hosts.length} host{line.hosts.length === 1 ? "" : "s"}
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
                    {line.gap > 0 ? (
                      <span className="flex items-center gap-1 text-amber-600 font-medium">
                        <FiRotateCw /> IN/OUT gap {line.gap}
                      </span>
                    ) : (
                      <span className="text-slate-400">IN/OUT auto-stop off</span>
                    )}
                    {line.reading_delay_sec > 0 && (
                      <span className="flex items-center gap-1 text-sky-600 font-medium">
                        <FiClock /> {line.reading_delay_sec}s startup delay
                      </span>
                    )}
                    {line.min_duration_sec > 0 && (
                      <span className="flex items-center gap-1 text-indigo-600 font-medium">
                        <FiClock /> min {line.min_duration_sec}s runtime
                      </span>
                    )}
                    {offlineHosts > 0 && (
                      <span className="flex items-center gap-1 text-signal-fail font-medium">
                        <FiWifiOff /> {offlineHosts} host{offlineHosts === 1 ? "" : "s"} unreachable
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex gap-1.5">
                  <button
                    type="button"
                    onClick={() => openEdit(line)}
                    title="Edit line"
                    className="flex items-center gap-1 px-2.5 py-1.5 bg-ink-900 hover:bg-ink-800 text-white rounded-md text-xs font-medium transition-colors"
                  >
                    <FiEdit2 className="text-[11px]" /> Edit
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirmTarget(line.line_key)}
                    title="Delete line"
                    className="flex items-center gap-1 px-2.5 py-1.5 bg-signal-fail/10 hover:bg-signal-fail text-signal-fail hover:text-white ring-1 ring-inset ring-signal-fail/30 rounded-md text-xs font-medium transition-colors"
                  >
                    <FiTrash2 className="text-[11px]" /> Delete
                  </button>
                </div>
              </div>

              <div className="p-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                {line.hosts.map((h) => {
                  const key = `${line.line_key}:${hostKey(h.host, h.port)}`;
                  const status = statusForHost(diagnostics, h.host, h.port);
                  const style = STATUS_STYLE[status];
                  const StatusIcon = style.icon;
                  const isExpanded = expandedHosts.has(key);
                  const visibleGauges =
                    isExpanded || h.gauges.length <= GAUGES_PREVIEW_COUNT
                      ? h.gauges
                      : h.gauges.slice(0, GAUGES_PREVIEW_COUNT);
                  const hiddenCount = h.gauges.length - visibleGauges.length;
                  const enabledInHost = h.gauges.filter((g) => g.enabled).length;
                  const manualTest = manualTests[key];
                  const manualByGauge = new Map(
                    (manualTest?.gauges || []).map((g) => [g.slave_id, g])
                  );

                  return (
                    <div key={key} className="border rounded-lg overflow-hidden">
                      <div className="flex items-center justify-between px-3 py-2 bg-slate-50 border-b gap-2">
                        <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-700 font-mono truncate">
                          <FiServer className="text-slate-400 shrink-0" />
                          {h.host}:{h.port}
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <span
                            title={style.label}
                            className={`flex items-center gap-1 text-[11px] font-medium ${style.text}`}
                          >
                            <span className={`w-1.5 h-1.5 rounded-full ${style.dot}`} />
                            <StatusIcon className="text-xs" />
                          </span>
                          <button
                            type="button"
                            onClick={() => handleTestHost(h.host, h.port, h.gauges)}
                            disabled={manualTest?.status === "testing"}
                            title="Test connection now"
                            className="flex items-center gap-1 px-1.5 py-0.5 rounded border border-slate-300 bg-white hover:bg-slate-100 text-[11px] font-medium text-slate-500 disabled:opacity-60"
                          >
                            {manualTest?.status === "testing" ? (
                              <FiLoader className="animate-spin" />
                            ) : (
                              "Test"
                            )}
                          </button>
                        </div>
                      </div>

                      {manualTest?.status === "done" && !manualTest.reachable && (
                        <p className="px-2.5 pt-2 text-[11px] text-rose-600">
                          Unreachable{manualTest.error ? `: ${manualTest.error}` : ""}
                        </p>
                      )}

                      <ul className="p-2.5 space-y-1">
                        {visibleGauges.map((g) => {
                          const tested = manualByGauge.get(g.slave_id);
                          return (
                            <li
                              key={g.slave_id}
                              className="flex items-center justify-between gap-2 text-xs"
                            >
                              <span
                                className={`flex items-center gap-1.5 truncate ${
                                  g.enabled ? "text-slate-700" : "text-slate-400"
                                }`}
                              >
                                {!g.enabled && <FiSlash className="text-slate-300 shrink-0" />}
                                <span className={g.enabled ? "" : "line-through"}>{g.name}</span>
                              </span>
                              <span
                                title={tested ? (tested.responding ? `Reading: ${tested.value ?? "—"}` : "No response") : undefined}
                                className={`font-mono shrink-0 px-1 rounded ${
                                  tested
                                    ? tested.responding
                                      ? "bg-emerald-100 text-emerald-700"
                                      : "bg-rose-100 text-rose-600"
                                    : "text-slate-400"
                                }`}
                              >
                                #{g.slave_id}
                              </span>
                            </li>
                          );
                        })}
                      </ul>

                      <div className="flex items-center justify-between px-2.5 pb-2 text-[11px] text-slate-400">
                        <span>
                          {enabledInHost}/{h.gauges.length} enabled
                        </span>
                        {h.gauges.length > GAUGES_PREVIEW_COUNT && (
                          <button
                            type="button"
                            onClick={() => toggleHostExpanded(key)}
                            className="flex items-center gap-0.5 text-emerald-700 hover:text-emerald-800 font-medium"
                          >
                            {isExpanded ? (
                              <>
                                Show less <FiChevronUp />
                              </>
                            ) : (
                              <>
                                +{hiddenCount} more <FiChevronDown />
                              </>
                            )}
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      <LineConfigModal
        open={modal.open}
        mode={modal.mode}
        initial={modal.initial}
        onClose={closeModal}
        onSave={handleSave}
      />

      <ConfirmDialog
        open={!!confirmTarget}
        title={`Delete "${confirmingLine?.line_label || confirmTarget}"?`}
        message="This removes all of its hosts and gauges. This cannot be undone."
        confirmLabel="Delete Line"
        danger
        onConfirm={handleDeleteConfirmed}
        onCancel={() => setConfirmTarget(null)}
      />
    </main>
  );
}
