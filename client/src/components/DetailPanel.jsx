import { useEffect, useRef, useState } from "react";
import { FiSquare } from "react-icons/fi";
import { getFixtureDetail, getLiveVacuum, stopTest as stopTestApi } from "../api/client";
import { toast } from "react-hot-toast";
import LiveVacuumChart from "./LiveVacuumChart";

const STATUS_TEXT_COLOR = {
  PASS: "text-signal-pass",
  FAIL: "text-signal-fail",
  RUNNING: "text-amber-600",
  ERROR: "text-signal-err",
  IDLE: "text-slate-400",
};

const MAX_POINTS = 80;

function formatRemaining(sec) {
  if (sec === null || sec === undefined) return null;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}m ${String(s).padStart(2, "0")}s`;
}

export default function DetailPanel({ gaugeId, fixture, onStopped }) {
  // using react-hot-toast
  const [detail, setDetail] = useState(null);
  const [liveValue, setLiveValue] = useState(null);
  const [chartData, setChartData] = useState([]);
  const [remaining, setRemaining] = useState(null);
  const tickRef = useRef(0);

  // Load detail whenever a different gauge is selected
  useEffect(() => {
    if (!gaugeId) return;
    setDetail(null);
    setChartData([]);
    tickRef.current = 0;
    getFixtureDetail(gaugeId)
      .then(setDetail)
      .catch(() => toast.error("Unable to load fixture details"));
  }, [gaugeId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Seed countdown from the fixture's reported remaining time
  useEffect(() => {
    if (fixture?.status === "RUNNING" && fixture.remaining != null) {
      setRemaining(fixture.remaining);
    } else {
      setRemaining(null);
    }
  }, [gaugeId, fixture?.status, fixture?.remaining]);

  // Countdown ticker
  useEffect(() => {
    if (remaining === null) return;
    if (remaining <= 0) return;
    const t = setInterval(() => setRemaining((r) => (r !== null && r > 0 ? r - 1 : r)), 1000);
    return () => clearInterval(t);
  }, [remaining !== null]); // eslint-disable-line react-hooks/exhaustive-deps

  // Live vacuum polling
  useEffect(() => {
    if (!gaugeId) return;
    const poll = () => {
      getLiveVacuum(gaugeId)
        .then((d) => {
          const v = Number(d.vacuum);
          if (!Number.isFinite(v)) {
            setLiveValue(null);
            return;
          }
          setLiveValue(v);
          tickRef.current += 1.5;
          setChartData((prev) => {
            const next = [...prev, { t: tickRef.current.toFixed(1), v }];
            return next.length > MAX_POINTS ? next.slice(next.length - MAX_POINTS) : next;
          });
        })
        .catch(() => setLiveValue(null));
    };
    poll();
    const t = setInterval(poll, 1500);
    return () => clearInterval(t);
  }, [gaugeId]);

  const handleStop = async () => {
    if (!confirm(`Stop the running test on Gauge ${gaugeId}?`)) return;
    try {
      const res = await stopTestApi(gaugeId);
        if (res.status === "STOPPED") {
        toast(`Test on Gauge ${gaugeId} stopped`, { icon: "⚠️" });
        onStopped?.();
      } else {
        toast(res.message || "No active test found", { icon: "ℹ️" });
      }
    } catch {
      toast.error("Network error — could not stop test");
    }
  };

  if (!gaugeId) return null;
  const status = fixture?.status || "IDLE";
  const sClass = STATUS_TEXT_COLOR[status] || "text-slate-400";

  return (
    <aside className="bg-white border rounded-xl shadow p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-lg font-bold text-slate-700 font-display">Gauge {gaugeId}</h3>
        <span className={`text-sm font-semibold ${sClass}`}>{status}</span>
      </div>

      {!detail ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : (
        <>
          <div className="text-xs space-y-1 mb-3 text-slate-500">
            <div>
              Serial: <b className="text-slate-800">{detail.serial_no || "—"}</b>
            </div>
            <div>
              Model: <b className="text-slate-800">{detail.model_code || "—"}</b> — {detail.model_name || "—"}
            </div>
            <div>
              Line: <b className="text-slate-800">{detail.line_name || "—"}</b>
            </div>
            {status === "RUNNING" && (
              <>
                <div className="text-amber-600 font-semibold pt-1">
                  ⏱ Remaining: {formatRemaining(remaining) || "—"}
                </div>
                <button
                  type="button"
                  onClick={handleStop}
                  className="w-full mt-2 py-2 rounded bg-rose-600 hover:bg-rose-700 text-white font-bold text-sm transition flex items-center justify-center gap-1.5"
                >
                  <FiSquare /> Stop Test
                </button>
              </>
            )}
          </div>

          <div className="text-sm mb-2">
            Vacuum:{" "}
            <b className="text-emerald-700 text-base tabular">
              {liveValue !== null ? liveValue.toFixed(3) : "—"}
            </b>{" "}
            <span className="text-xs text-slate-400">mbar</span>
          </div>

          <LiveVacuumChart data={chartData} ll={detail.ll} ul={detail.ul} />

          <div className="text-xs mt-2 text-slate-500 tabular">
            LL: <b>{detail.ll ?? "—"}</b> mbar &nbsp;|&nbsp; UL: <b>{detail.ul ?? "—"}</b> mbar
            {detail.start_time && (
              <>
                <br />
                Started: {new Date(detail.start_time).toLocaleString()}
              </>
            )}
          </div>
        </>
      )}
    </aside>
  );
}
