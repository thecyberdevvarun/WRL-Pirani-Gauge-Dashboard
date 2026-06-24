import { useEffect, useState } from "react";
import { getTodayStats } from "../api/client";

export default function TodayStatsBar() {
  const [stats, setStats] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);

  useEffect(() => {
    const load = () =>
      getTodayStats()
        .then((d) => {
          setStats(d);
          setLastUpdated(new Date());
        })
        .catch(() => {});
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="flex flex-wrap items-center gap-5 px-5 py-2 bg-ink-800 text-white text-xs tabular">
      <span className="font-semibold text-slate-400 uppercase tracking-wider font-display">
        Today
      </span>
      <span>
        Total: <b className="text-white">{stats?.total ?? "—"}</b>
      </span>
      <span className="text-signal-pass">
        PASS: <b>{stats?.pass ?? "—"}</b>
      </span>
      <span className="text-signal-fail">
        FAIL: <b>{stats?.fail ?? "—"}</b>
      </span>
      <span className="text-signal-run">
        RUNNING: <b>{stats?.running ?? "—"}</b>
      </span>
      <span className="text-slate-300">
        Pass Rate: <b>{stats ? `${stats.pass_rate}%` : "—"}</b>
      </span>
      <span className="ml-auto text-slate-500">
        Last updated: {lastUpdated ? lastUpdated.toLocaleTimeString() : "—"}
      </span>
    </div>
  );
}
