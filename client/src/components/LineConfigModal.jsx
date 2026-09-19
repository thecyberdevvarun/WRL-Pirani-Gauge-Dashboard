import { useEffect, useState } from "react";
import {
  FiPlus,
  FiTrash2,
  FiZap,
  FiX,
  FiServer,
  FiRotateCw,
  FiWifi,
  FiLoader,
  FiCheckCircle,
  FiAlertTriangle,
  FiClock,
  FiTarget,
} from "react-icons/fi";
import { toast } from "react-hot-toast";
import { testConnection } from "../api/client";

const EMPTY_GAUGE = () => ({ name: "", slave_id: "", enabled: true });
const EMPTY_HOST = () => ({ host: "", port: 502, gauges: [EMPTY_GAUGE()] });
const EMPTY_FORM = () => ({
  line_key: "",
  line_label: "",
  gap: "0",
  reading_delay_sec: "0",
  upper_limit: "0",
  poll_interval_sec: "60",
  min_duration_sec: "600",
  hosts: [EMPTY_HOST()],
});

function toFormHosts(hosts) {
  if (!hosts || !hosts.length) return [EMPTY_HOST()];
  return hosts.map((h) => ({
    host: h.host,
    port: h.port,
    gauges: h.gauges.map((g) => ({
      name: g.name,
      slave_id: String(g.slave_id),
      enabled: g.enabled,
    })),
  }));
}

/** Highest numeric slave_id anywhere in the form, for auto-suggesting the next one. */
function highestSlaveId(hosts) {
  let max = 0;
  for (const h of hosts) {
    for (const g of h.gauges) {
      const n = parseInt(g.slave_id, 10);
      if (Number.isInteger(n) && n > max) max = n;
    }
  }
  return max;
}

const inputCls = (hasError) =>
  `w-full px-3 py-2 border rounded outline-none text-sm ${
    hasError
      ? "border-rose-400 focus:border-rose-500 bg-rose-50/40"
      : "border-slate-300 focus:border-emerald-600"
  }`;

export default function LineConfigModal({ open, mode, initial, onClose, onSave }) {
  const [form, setForm] = useState(EMPTY_FORM());
  const [globalError, setGlobalError] = useState("");
  const [fieldErrors, setFieldErrors] = useState(null); // set only after a failed Save attempt
  const [quickAddOpen, setQuickAddOpen] = useState(null); // host index, or null
  const [testResults, setTestResults] = useState({}); // host index -> { status, reachable, error, gauges }

  useEffect(() => {
    if (!open) return;
    if (initial) {
      setForm({
        line_key: initial.line_key,
        line_label: initial.line_label,
        gap: String(initial.gap ?? 0),
        reading_delay_sec: String(initial.reading_delay_sec ?? 0),
        upper_limit: String(initial.upper_limit ?? 0),
        poll_interval_sec: String(initial.poll_interval_sec ?? 60),
        min_duration_sec: String(initial.min_duration_sec ?? 600),
        hosts: toFormHosts(initial.hosts),
      });
    } else {
      setForm(EMPTY_FORM());
    }
    setGlobalError("");
    setFieldErrors(null);
    setQuickAddOpen(null);
    setTestResults({});
  }, [open, initial]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const updateHost = (hIdx, patch) => {
    setForm((f) => ({
      ...f,
      hosts: f.hosts.map((h, i) => (i === hIdx ? { ...h, ...patch } : h)),
    }));
    // A stale reachable/unreachable result for the old host:port would be misleading.
    if ("host" in patch || "port" in patch) {
      setTestResults((r) => {
        if (!(hIdx in r)) return r;
        const next = { ...r };
        delete next[hIdx];
        return next;
      });
    }
  };

  const updateGauge = (hIdx, gIdx, patch) =>
    setForm((f) => ({
      ...f,
      hosts: f.hosts.map((h, i) =>
        i !== hIdx
          ? h
          : { ...h, gauges: h.gauges.map((g, j) => (j === gIdx ? { ...g, ...patch } : g)) }
      ),
    }));

  const addHost = () => {
    setForm((f) => ({ ...f, hosts: [...f.hosts, EMPTY_HOST()] }));
  };
  const removeHost = (hIdx) => {
    setForm((f) => ({ ...f, hosts: f.hosts.filter((_, i) => i !== hIdx) }));
    // Indices shift after removal — drop all cached results rather than risk
    // showing a stale result against the wrong host.
    setTestResults({});
  };

  const addGauge = (hIdx) => {
    const suggested = highestSlaveId(form.hosts) + 1;
    setForm((f) => ({
      ...f,
      hosts: f.hosts.map((h, i) =>
        i === hIdx
          ? { ...h, gauges: [...h.gauges, { name: "", slave_id: String(suggested), enabled: true }] }
          : h
      ),
    }));
  };
  const removeGauge = (hIdx, gIdx) =>
    setForm((f) => ({
      ...f,
      hosts: f.hosts.map((h, i) =>
        i === hIdx ? { ...h, gauges: h.gauges.filter((_, j) => j !== gIdx) } : h
      ),
    }));

  const runQuickAdd = (hIdx, { count, start, prefix }) => {
    const n = parseInt(count, 10);
    const startId = parseInt(start, 10);
    if (!Number.isInteger(n) || n < 1 || n > 100 || !Number.isInteger(startId) || startId < 1) {
      return;
    }
    const generated = Array.from({ length: n }, (_, i) => ({
      name: `${prefix}${startId + i}`,
      slave_id: String(startId + i),
      enabled: true,
    }));
    setForm((f) => ({
      ...f,
      hosts: f.hosts.map((h, i) => {
        if (i !== hIdx) return h;
        // Drop untouched blank placeholder rows before appending generated ones.
        const kept = h.gauges.filter((g) => g.name.trim() || g.slave_id.trim());
        return { ...h, gauges: [...kept, ...generated] };
      }),
    }));
    setQuickAddOpen(null);
  };

  const handleTestHost = async (hIdx) => {
    const h = form.hosts[hIdx];
    const port = Number(h.port);
    if (!h.host.trim() || !Number.isInteger(port) || port < 1 || port > 65535) {
      return toast.error("Enter a valid host and port before testing");
    }
    const slaveIds = h.gauges
      .map((g) => Number(g.slave_id))
      .filter((n) => Number.isInteger(n) && n >= 1 && n <= 247);

    setTestResults((r) => ({ ...r, [hIdx]: { status: "testing" } }));
    try {
      const res = await testConnection({ host: h.host.trim(), port, slave_ids: slaveIds });
      setTestResults((r) => ({ ...r, [hIdx]: { status: "done", ...res } }));
    } catch (err) {
      setTestResults((r) => ({
        ...r,
        [hIdx]: { status: "done", reachable: false, error: err.message, gauges: [] },
      }));
    }
  };

  const validate = () => {
    const lineKey = form.line_key.trim();
    const lineLabel = form.line_label.trim();
    const gapNum = Number(form.gap);
    const readingDelayNum = Number(form.reading_delay_sec);
    const upperLimitNum = Number(form.upper_limit);
    const pollIntervalNum = Number(form.poll_interval_sec);
    const minDurationNum = Number(form.min_duration_sec);
    const errors = {
      line_key: !/^[A-Za-z0-9_-]{1,50}$/.test(lineKey)
        ? "1-50 characters: letters, digits, _ or -"
        : null,
      line_label: !lineLabel ? "Required" : null,
      gap:
        !Number.isInteger(gapNum) || gapNum < 0 || gapNum > 500 ? "0-500" : null,
      reading_delay_sec:
        !Number.isInteger(readingDelayNum) || readingDelayNum < 0 || readingDelayNum > 3600
          ? "0-3600"
          : null,
      upper_limit:
        !Number.isFinite(upperLimitNum) || upperLimitNum < 0 ? "Must be 0 or greater" : null,
      poll_interval_sec:
        !Number.isInteger(pollIntervalNum) || pollIntervalNum < 60 || pollIntervalNum > 3600
          ? "60-3600"
          : null,
      min_duration_sec:
        !Number.isInteger(minDurationNum) || minDurationNum < 0 || minDurationNum > 3600
          ? "0-3600"
          : null,
      hosts: form.hosts.map((h) => {
        const port = Number(h.port);
        return {
          host: !h.host.trim() ? "Required" : null,
          port: !Number.isInteger(port) || port < 1 || port > 65535 ? "1-65535" : null,
          gauges: h.gauges.map((g) => {
            const sid = Number(g.slave_id);
            return {
              name: !g.name.trim() ? "Required" : null,
              slave_id:
                !Number.isInteger(sid) || sid < 1 || sid > 247 ? "1-247" : null,
            };
          }),
        };
      }),
    };

    let global = "";
    if (!form.hosts.length) {
      global = "Add at least one host";
    } else if (form.hosts.some((h) => !h.gauges.length)) {
      global = "Every host needs at least one gauge";
    } else {
      const allSlaveIds = form.hosts.flatMap((h) => h.gauges.map((g) => Number(g.slave_id)));
      const validIds = allSlaveIds.filter((n) => Number.isInteger(n) && n >= 1 && n <= 247);
      if (new Set(validIds).size !== validIds.length) {
        global = "Duplicate slave ID within this line — slave IDs must be unique";
      }
    }

    const hasFieldError =
      errors.line_key ||
      errors.line_label ||
      errors.gap ||
      errors.reading_delay_sec ||
      errors.upper_limit ||
      errors.poll_interval_sec ||
      errors.min_duration_sec ||
      errors.hosts.some((h) => h.host || h.port || h.gauges.some((g) => g.name || g.slave_id));

    return { errors, global, valid: !hasFieldError && !global };
  };

  const handleSave = () => {
    const { errors, global, valid } = validate();
    setFieldErrors(errors);
    setGlobalError(global);
    if (!valid) return;

    onSave({
      line_key: form.line_key.trim(),
      line_label: form.line_label.trim(),
      gap: Number(form.gap) || 0,
      reading_delay_sec: Number(form.reading_delay_sec) || 0,
      upper_limit: Number(form.upper_limit) || 0,
      poll_interval_sec: Number(form.poll_interval_sec) || 60,
      min_duration_sec: Number(form.min_duration_sec) || 0,
      hosts: form.hosts.map((h) => ({
        host: h.host.trim(),
        port: Number(h.port),
        gauges: h.gauges.map((g) => ({
          name: g.name.trim(),
          slave_id: Number(g.slave_id),
          enabled: !!g.enabled,
        })),
      })),
    });
  };

  const titles = { add: "Add Line", edit: "Edit Line" };
  const totalGauges = form.hosts.reduce((n, h) => n + h.gauges.length, 0);

  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
      role="dialog"
      aria-modal="true"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b shrink-0">
          <div>
            <h3 className="text-lg font-semibold text-emerald-700 font-display">
              {titles[mode]}
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              {form.hosts.length} host{form.hosts.length === 1 ? "" : "s"} · {totalGauges} gauge
              {totalGauges === 1 ? "" : "s"}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 p-1"
            title="Close"
          >
            <FiX className="text-lg" />
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-4 overflow-y-auto scroll-thin flex-1">
          <div className="grid grid-cols-2 gap-3 mb-5 text-sm">
            <div>
              <label className="block mb-1 font-medium">
                Line Key <span className="text-rose-500">*</span>
              </label>
              <input
                value={form.line_key}
                onChange={(e) => setForm((f) => ({ ...f, line_key: e.target.value }))}
                disabled={mode === "edit"}
                placeholder="e.g. VISI_COOLER"
                className={`${inputCls(fieldErrors?.line_key)} disabled:opacity-60 disabled:bg-slate-50`}
              />
              {fieldErrors?.line_key && (
                <p className="text-[11px] text-rose-500 mt-1">{fieldErrors.line_key}</p>
              )}
            </div>
            <div>
              <label className="block mb-1 font-medium">
                Line Label <span className="text-rose-500">*</span>
              </label>
              <input
                value={form.line_label}
                onChange={(e) => setForm((f) => ({ ...f, line_label: e.target.value }))}
                placeholder="e.g. Visi Cooler"
                className={inputCls(fieldErrors?.line_label)}
              />
              {fieldErrors?.line_label && (
                <p className="text-[11px] text-rose-500 mt-1">{fieldErrors.line_label}</p>
              )}
            </div>
          </div>

          <div className="mb-5 p-3 rounded-lg bg-emerald-50 border border-emerald-200">
            <label className="flex items-center gap-1.5 font-medium text-sm mb-1">
              <FiTarget className="text-emerald-600" /> Pass/Fail Limit
            </label>
            <p className="text-xs text-slate-500 mb-2">
              The single common Upper Limit every test on this line is judged against — a reading
              above this fails, at or below it passes (no lower limit). Leave at 0 until you set a
              real value; every test will fail until you do, rather than silently passing everything.
            </p>
            <div className="flex items-end gap-4 flex-wrap">
              <div>
                <label className="block mb-1 text-[11px] text-slate-500">Upper Limit (mbar)</label>
                <input
                  type="number"
                  step="0.001"
                  min="0"
                  value={form.upper_limit}
                  onChange={(e) => setForm((f) => ({ ...f, upper_limit: e.target.value }))}
                  className={inputCls(fieldErrors?.upper_limit) + " w-36"}
                />
                {fieldErrors?.upper_limit && (
                  <p className="text-[11px] text-rose-500 mt-1">{fieldErrors.upper_limit}</p>
                )}
              </div>
              <div>
                <label className="block mb-1 text-[11px] text-slate-500">
                  Poll Interval (sec)
                </label>
                <input
                  type="number"
                  min="60"
                  max="3600"
                  value={form.poll_interval_sec}
                  onChange={(e) => setForm((f) => ({ ...f, poll_interval_sec: e.target.value }))}
                  className={inputCls(fieldErrors?.poll_interval_sec) + " w-32"}
                />
                {fieldErrors?.poll_interval_sec && (
                  <p className="text-[11px] text-rose-500 mt-1">{fieldErrors.poll_interval_sec}</p>
                )}
              </div>
            </div>
          </div>

          <div className="mb-5 p-3 rounded-lg bg-amber-50 border border-amber-200">
            <label className="flex items-center gap-1.5 font-medium text-sm mb-1">
              <FiRotateCw className="text-amber-600" /> IN/OUT Auto-Stop Gap
            </label>
            <p className="text-xs text-slate-500 mb-2">
              On a rotating/cyclic line, scanning a gauge IN also automatically stops any running
              test found in the gauges spanning this many positions <strong>ahead</strong> of it in
              the sequence (e.g. gap 5 on gauge 15 sweeps gauges 16-20, wraps around). Set to 0 to
              disable — tests will then only stop on their own timer or a manual Stop.
            </p>
            <input
              type="number"
              min="0"
              max="500"
              value={form.gap}
              onChange={(e) => setForm((f) => ({ ...f, gap: e.target.value }))}
              className={inputCls(fieldErrors?.gap) + " w-32"}
            />
            {fieldErrors?.gap && <p className="text-[11px] text-rose-500 mt-1">{fieldErrors.gap}</p>}
          </div>

          <div className="mb-5 p-3 rounded-lg bg-indigo-50 border border-indigo-200">
            <label className="flex items-center gap-1.5 font-medium text-sm mb-1">
              <FiClock className="text-indigo-600" /> Minimum Test Duration
            </label>
            <p className="text-xs text-slate-500 mb-2">
              A test on this line always runs for at least this long, even if the IN/OUT
              auto-stop above tries to end it sooner — its naturally accumulated PASS/FAIL still
              stands once it does stop. Does <strong>not</strong> apply to a manual Stop, which
              always takes effect immediately. Set to 0 to disable.
            </p>
            <div className="flex items-center gap-2">
              <input
                type="number"
                min="0"
                max="3600"
                value={form.min_duration_sec}
                onChange={(e) => setForm((f) => ({ ...f, min_duration_sec: e.target.value }))}
                className={inputCls(fieldErrors?.min_duration_sec) + " w-32"}
              />
              <span className="text-xs text-slate-400">seconds</span>
            </div>
            {fieldErrors?.min_duration_sec && (
              <p className="text-[11px] text-rose-500 mt-1">{fieldErrors.min_duration_sec}</p>
            )}
          </div>

          <div className="mb-5 p-3 rounded-lg bg-sky-50 border border-sky-200">
            <label className="flex items-center gap-1.5 font-medium text-sm mb-1">
              <FiClock className="text-sky-600" /> Reading Startup Delay
            </label>
            <p className="text-xs text-slate-500 mb-2">
              After a test starts, wait this many seconds before readings start counting toward
              PASS/FAIL — lets the vacuum settle right after start instead of judging on an early,
              still-ramping reading. Comes out of the overall test time rather than extending it.
              Set to 0 to disable.
            </p>
            <div className="flex items-center gap-2">
              <input
                type="number"
                min="0"
                max="3600"
                value={form.reading_delay_sec}
                onChange={(e) => setForm((f) => ({ ...f, reading_delay_sec: e.target.value }))}
                className={inputCls(fieldErrors?.reading_delay_sec) + " w-32"}
              />
              <span className="text-xs text-slate-400">seconds</span>
            </div>
            {fieldErrors?.reading_delay_sec && (
              <p className="text-[11px] text-rose-500 mt-1">{fieldErrors.reading_delay_sec}</p>
            )}
          </div>

          <div className="space-y-4">
            {form.hosts.map((h, hIdx) => {
              const hErr = fieldErrors?.hosts?.[hIdx];
              return (
                <div key={hIdx} className="border rounded-lg p-4 bg-slate-50/60">
                  <div className="flex items-center justify-between mb-3">
                    <span className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">
                      <FiServer /> Host {hIdx + 1}
                    </span>
                    <button
                      type="button"
                      onClick={() => removeHost(hIdx)}
                      disabled={form.hosts.length === 1}
                      title="Remove host"
                      className="p-1.5 text-slate-400 hover:text-rose-500 disabled:opacity-30 disabled:hover:text-slate-400"
                    >
                      <FiTrash2 />
                    </button>
                  </div>

                  <div className="flex items-start gap-3 mb-2">
                    <div className="flex-1">
                      <input
                        value={h.host}
                        onChange={(e) => updateHost(hIdx, { host: e.target.value })}
                        placeholder="Host / IP, e.g. 192.168.0.3"
                        className={inputCls(hErr?.host)}
                      />
                      {hErr?.host && <p className="text-[11px] text-rose-500 mt-1">{hErr.host}</p>}
                    </div>
                    <div className="w-28">
                      <input
                        type="number"
                        value={h.port}
                        onChange={(e) => updateHost(hIdx, { port: e.target.value })}
                        placeholder="Port"
                        className={inputCls(hErr?.port)}
                      />
                      {hErr?.port && <p className="text-[11px] text-rose-500 mt-1">{hErr.port}</p>}
                    </div>
                    <button
                      type="button"
                      onClick={() => handleTestHost(hIdx)}
                      disabled={testResults[hIdx]?.status === "testing"}
                      className="flex items-center gap-1.5 px-3 py-2 rounded border border-slate-300 bg-white hover:bg-slate-50 text-xs font-semibold text-slate-600 disabled:opacity-60 whitespace-nowrap"
                    >
                      {testResults[hIdx]?.status === "testing" ? (
                        <FiLoader className="animate-spin" />
                      ) : (
                        <FiWifi />
                      )}
                      Test
                    </button>
                  </div>

                  <TestResultSummary result={testResults[hIdx]} />

                  <div className="space-y-1.5">
                    {h.gauges.map((g, gIdx) => {
                      const gErr = hErr?.gauges?.[gIdx];
                      return (
                        <div key={gIdx} className="flex items-start gap-2">
                          <div className="flex-1">
                            <input
                              value={g.name}
                              onChange={(e) => updateGauge(hIdx, gIdx, { name: e.target.value })}
                              placeholder="Gauge name, e.g. Pirani_1"
                              className={inputCls(gErr?.name) + " py-1.5"}
                            />
                          </div>
                          <div className="w-24">
                            <input
                              type="number"
                              value={g.slave_id}
                              onChange={(e) =>
                                updateGauge(hIdx, gIdx, { slave_id: e.target.value })
                              }
                              placeholder="Slave ID"
                              className={inputCls(gErr?.slave_id) + " py-1.5"}
                            />
                          </div>
                          <label className="flex items-center gap-1 text-xs text-slate-500 w-20 pt-2">
                            <input
                              type="checkbox"
                              checked={g.enabled}
                              onChange={(e) =>
                                updateGauge(hIdx, gIdx, { enabled: e.target.checked })
                              }
                            />
                            Enabled
                          </label>
                          <button
                            type="button"
                            onClick={() => removeGauge(hIdx, gIdx)}
                            disabled={h.gauges.length === 1}
                            title="Remove gauge"
                            className="p-1.5 mt-0.5 text-slate-400 hover:text-rose-500 disabled:opacity-30 disabled:hover:text-slate-400"
                          >
                            <FiTrash2 className="text-sm" />
                          </button>
                        </div>
                      );
                    })}
                  </div>

                  {quickAddOpen === hIdx ? (
                    <QuickAddForm
                      defaultStart={highestSlaveId(form.hosts) + 1}
                      onGenerate={(opts) => runQuickAdd(hIdx, opts)}
                      onCancel={() => setQuickAddOpen(null)}
                    />
                  ) : (
                    <div className="flex items-center gap-4 mt-2.5">
                      <button
                        type="button"
                        onClick={() => addGauge(hIdx)}
                        className="flex items-center gap-1 text-xs font-medium text-emerald-700 hover:text-emerald-800"
                      >
                        <FiPlus /> Add Gauge
                      </button>
                      <button
                        type="button"
                        onClick={() => setQuickAddOpen(hIdx)}
                        className="flex items-center gap-1 text-xs font-medium text-sky-700 hover:text-sky-800"
                      >
                        <FiZap /> Quick Add Sequential…
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <button
            type="button"
            onClick={addHost}
            className="mt-3 flex items-center gap-1.5 text-sm font-medium text-emerald-700 hover:text-emerald-800"
          >
            <FiPlus /> Add Host
          </button>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t shrink-0">
          {globalError && <p className="text-xs text-rose-500 font-medium mb-3">{globalError}</p>}
          <div className="flex justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded bg-slate-200 hover:bg-slate-300 text-sm"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              className="px-4 py-2 rounded bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-sm"
            >
              Save Line
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function TestResultSummary({ result }) {
  if (!result || result.status === "testing") return null;

  if (!result.reachable) {
    return (
      <p className="flex items-center gap-1.5 text-xs text-rose-600 mb-3 -mt-1">
        <FiAlertTriangle /> Unreachable{result.error ? `: ${result.error}` : ""}
      </p>
    );
  }

  const gauges = result.gauges || [];
  const responding = gauges.filter((g) => g.responding).length;

  return (
    <div className="mb-3 -mt-1">
      <p className="flex items-center gap-1.5 text-xs text-emerald-700 font-medium">
        <FiCheckCircle />
        Reachable
        {gauges.length > 0 && ` — ${responding}/${gauges.length} gauges responding`}
      </p>
      {gauges.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-1.5">
          {gauges.map((g) => (
            <span
              key={g.slave_id}
              title={g.responding ? `Reading: ${g.value ?? "—"}` : "No response"}
              className={`text-[11px] font-mono px-1.5 py-0.5 rounded ${
                g.responding
                  ? "bg-emerald-100 text-emerald-700"
                  : "bg-rose-100 text-rose-600"
              }`}
            >
              #{g.slave_id}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function QuickAddForm({ defaultStart, onGenerate, onCancel }) {
  const [count, setCount] = useState("5");
  const [start, setStart] = useState(String(defaultStart));
  const [prefix, setPrefix] = useState("Pirani_");

  return (
    <div className="mt-3 p-3 rounded-lg bg-sky-50 border border-sky-200">
      <p className="text-[11px] font-semibold text-sky-800 uppercase tracking-wide mb-2 flex items-center gap-1">
        <FiZap /> Generate sequential gauges
      </p>
      <div className="flex items-end gap-2 flex-wrap">
        <div>
          <label className="block text-[11px] text-slate-500 mb-1">Count</label>
          <input
            type="number"
            min="1"
            max="100"
            value={count}
            onChange={(e) => setCount(e.target.value)}
            className="w-20 px-2 py-1.5 border rounded text-sm focus:border-sky-500 outline-none"
          />
        </div>
        <div>
          <label className="block text-[11px] text-slate-500 mb-1">Start Slave ID</label>
          <input
            type="number"
            min="1"
            max="247"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            className="w-24 px-2 py-1.5 border rounded text-sm focus:border-sky-500 outline-none"
          />
        </div>
        <div>
          <label className="block text-[11px] text-slate-500 mb-1">Name Prefix</label>
          <input
            value={prefix}
            onChange={(e) => setPrefix(e.target.value)}
            className="w-28 px-2 py-1.5 border rounded text-sm focus:border-sky-500 outline-none"
          />
        </div>
        <button
          type="button"
          onClick={() => onGenerate({ count, start, prefix })}
          className="px-3 py-1.5 rounded bg-sky-600 hover:bg-sky-700 text-white text-xs font-semibold"
        >
          Generate
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="px-3 py-1.5 rounded bg-white border text-xs text-slate-500 hover:bg-slate-50"
        >
          Cancel
        </button>
      </div>
      <p className="text-[11px] text-sky-700 mt-2">
        Creates "{prefix}
        {start || "?"}" … "{prefix}
        {start && count ? Number(start) + Number(count) - 1 : "?"}" and replaces any empty rows on
        this host.
      </p>
    </div>
  );
}
