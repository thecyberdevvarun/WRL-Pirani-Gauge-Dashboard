import { useEffect, useState } from "react";
import { FiX, FiLoader } from "react-icons/fi";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, Legend } from "recharts";
import { getReportTrend, getRecipeByModel } from "../api/client";

function fmtDateTime(dt) {
  if (!dt || dt === "None" || dt === "NaT") return "—";
  return new Date(dt).toLocaleString();
}

export default function TrendModal({ row, onClose }) {
  const [state, setState] = useState({ loading: true, error: null, points: [], ll: null, ul: null });

  useEffect(() => {
    if (!row) return;
    setState({ loading: true, error: null, points: [], ll: null, ul: null });

    Promise.all([getReportTrend(row.test_id), getRecipeByModel(row.model_code)])
      .then(([trendData, recipe]) => {
        const ll = recipe.ll ?? null;
        const ul = recipe.ul ?? null;
        const points = trendData.map((d) => {
          const t = new Date(d.time);
          return {
            label: `${String(t.getHours()).padStart(2, "0")}:${String(t.getMinutes()).padStart(2, "0")}:${String(
              t.getSeconds()
            ).padStart(2, "0")}`,
            v: d.vacuum,
          };
        });
        setState({ loading: false, error: null, points, ll, ul });
      })
      .catch((err) => setState({ loading: false, error: err.message, points: [], ll: null, ul: null }));
  }, [row]);

  if (!row) return null;

  const { loading, error, points, ll, ul } = state;
  const vals = points.map((p) => p.v).filter((v) => v !== null && v !== undefined);
  const stats = vals.length
    ? {
        min: Math.min(...vals).toFixed(3),
        max: Math.max(...vals).toFixed(3),
        avg: (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(3),
        count: vals.length,
      }
    : null;

  const allY = [...vals, ...(ll != null ? [ll] : []), ...(ul != null ? [ul] : [])];
  const yPad = allY.length ? (Math.max(...allY) - Math.min(...allY)) * 0.15 || 0.05 : 0.5;
  const yMin = allY.length ? Math.min(...allY) - yPad : undefined;
  const yMax = allY.length ? Math.max(...allY) + yPad : undefined;

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-white rounded-xl p-6 w-full max-w-3xl shadow-2xl">
        <div className="flex justify-between items-start mb-4">
          <div>
            <h3 className="font-bold text-slate-700 text-base font-display">
              Gauge {row.gauge_id} — {row.model_code || ""} — {row.serial_no || ""}
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              {fmtDateTime(row.start_time)} → {fmtDateTime(row.end_time)} | {row.line_name || "—"}
            </p>
          </div>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-700 text-xl leading-none">
            <FiX />
          </button>
        </div>

        {stats && (
          <div className="grid grid-cols-4 gap-2 mb-4 text-xs text-center">
            <div className="bg-slate-50 rounded p-2">
              <div className="font-bold text-slate-700 tabular">{stats.min}</div>
              <div className="text-slate-400">Min (mbar)</div>
            </div>
            <div className="bg-slate-50 rounded p-2">
              <div className="font-bold text-slate-700 tabular">{stats.max}</div>
              <div className="text-slate-400">Max (mbar)</div>
            </div>
            <div className="bg-slate-50 rounded p-2">
              <div className="font-bold text-slate-700 tabular">{stats.avg}</div>
              <div className="text-slate-400">Avg (mbar)</div>
            </div>
            <div className="bg-slate-50 rounded p-2">
              <div className="font-bold text-slate-700 tabular">{stats.count}</div>
              <div className="text-slate-400">Readings</div>
            </div>
          </div>
        )}

        {loading && (
          <div className="text-center py-10 text-slate-400 text-sm flex items-center justify-center gap-2">
            <FiLoader className="animate-spin text-emerald-600" /> Loading trend data…
          </div>
        )}

        {!loading && (error || points.length === 0) && (
          <div className="text-center py-10 text-slate-400 text-sm">
            {error ? `Error loading trend: ${error}` : "No vacuum readings recorded for this test."}
          </div>
        )}

        {!loading && !error && points.length > 0 && (
          <div className="h-75">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={points} margin={{ top: 8, right: 16, bottom: 8, left: -8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="label" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                <YAxis domain={[yMin, yMax]} tick={{ fontSize: 10 }} tickFormatter={(v) => Number(v).toFixed(3)} width={56} />
                <Tooltip formatter={(v) => [v != null ? `${Number(v).toFixed(3)} mbar` : "No reading", "Vacuum"]} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                {ll != null && (
                  <ReferenceLine y={ll} stroke="#f97316" strokeDasharray="7 5" label={{ value: `LL (${ll})`, fontSize: 10, fill: "#f97316" }} />
                )}
                {ul != null && (
                  <ReferenceLine y={ul} stroke="#dc2626" strokeDasharray="7 5" label={{ value: `UL (${ul})`, fontSize: 10, fill: "#dc2626" }} />
                )}
                <Line type="monotone" dataKey="v" name="Vacuum (mbar)" stroke="#2563eb" strokeWidth={2} dot={{ r: 2 }} connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}
