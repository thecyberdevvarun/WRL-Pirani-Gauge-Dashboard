import { useEffect, useState } from "react";
import { FiLoader } from "react-icons/fi";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  Legend,
} from "recharts";
import { getReportTrend, getRecipeByModel } from "../api/client";

function fmtTime(dt) {
  const t = new Date(dt);
  if (Number.isNaN(t.getTime())) return dt;
  return `${String(t.getHours()).padStart(2, "0")}:${String(t.getMinutes()).padStart(2, "0")}:${String(
    t.getSeconds(),
  ).padStart(2, "0")}`;
}

/**
 * Expanded-row panel for ReportTable. Fetches every individual poll-interval
 * reading logged for this test (pirani_test_log, via /api/report/:id/trend)
 * plus the recipe limits, and shows a trend chart and the full readings list.
 */
export default function ReportAccordion({ row }) {
  const [state, setState] = useState({
    loading: true,
    error: null,
    readings: [],
    ll: null,
    ul: null,
  });

  useEffect(() => {
    let cancelled = false;
    setState({ loading: true, error: null, readings: [], ll: null, ul: null });

    Promise.all([getReportTrend(row.test_id), getRecipeByModel(row.model_code)])
      .then(([trendData, recipe]) => {
        if (cancelled) return;
        setState({
          loading: false,
          error: null,
          readings: trendData,
          ll: recipe.ll ?? null,
          ul: recipe.ul ?? null,
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setState({
          loading: false,
          error: err.message,
          readings: [],
          ll: null,
          ul: null,
        });
      });

    return () => {
      cancelled = true;
    };
  }, [row.test_id, row.model_code]);

  const { loading, error, readings, ll, ul } = state;

  if (loading) {
    return (
      <div className="py-8 text-center text-slate-400 text-sm flex items-center justify-center gap-2">
        <FiLoader className="animate-spin text-emerald-600" /> Loading readings…
      </div>
    );
  }

  if (error) {
    return (
      <div className="py-6 text-center text-sm text-rose-500">
        Error loading readings: {error}
      </div>
    );
  }

  if (readings.length === 0) {
    return (
      <div className="py-6 text-center text-sm text-slate-400">
        No poll readings were recorded for this test.
      </div>
    );
  }

  const vals = readings
    .map((r) => r.vacuum)
    .filter((v) => v !== null && v !== undefined);
  const stats = vals.length
    ? {
        min: Math.min(...vals).toFixed(3),
        max: Math.max(...vals).toFixed(3),
        avg: (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(3),
        count: vals.length,
      }
    : null;

  const chartPoints = readings.map((r) => ({
    label: fmtTime(r.time),
    v: r.vacuum,
  }));
  const allY = [
    ...vals,
    ...(ll != null ? [ll] : []),
    ...(ul != null ? [ul] : []),
  ];
  const yPad = allY.length
    ? (Math.max(...allY) - Math.min(...allY)) * 0.15 || 0.05
    : 0.5;
  const yMin = allY.length ? Math.min(...allY) - yPad : undefined;
  const yMax = allY.length ? Math.max(...allY) + yPad : undefined;

  return (
    <div className="p-4 bg-slate-50 grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div>
        {stats && (
          <div className="grid grid-cols-4 gap-2 mb-3 text-xs text-center">
            <div className="bg-white rounded p-2 shadow-sm">
              <div className="font-bold text-slate-700 tabular">
                {stats.min}
              </div>
              <div className="text-slate-400">Min (mbar)</div>
            </div>
            <div className="bg-white rounded p-2 shadow-sm">
              <div className="font-bold text-slate-700 tabular">
                {stats.max}
              </div>
              <div className="text-slate-400">Max (mbar)</div>
            </div>
            <div className="bg-white rounded p-2 shadow-sm">
              <div className="font-bold text-slate-700 tabular">
                {stats.avg}
              </div>
              <div className="text-slate-400">Avg (mbar)</div>
            </div>
            <div className="bg-white rounded p-2 shadow-sm">
              <div className="font-bold text-slate-700 tabular">
                {stats.count}
              </div>
              <div className="text-slate-400">Readings</div>
            </div>
          </div>
        )}
        <div className="h-64 bg-white rounded-lg shadow-sm p-2">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={chartPoints}
              margin={{ top: 8, right: 16, bottom: 8, left: -8 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 10 }}
                interval="preserveStartEnd"
              />
              <YAxis
                domain={[yMin, yMax]}
                tick={{ fontSize: 10 }}
                tickFormatter={(v) => Number(v).toFixed(3)}
                width={56}
              />
              <Tooltip
                formatter={(v) => [
                  v != null ? `${Number(v).toFixed(3)} mbar` : "No reading",
                  "Vacuum",
                ]}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {ll != null && (
                <ReferenceLine
                  y={ll}
                  stroke="#f97316"
                  strokeDasharray="7 5"
                  label={{ value: `LL (${ll})`, fontSize: 10, fill: "#f97316" }}
                />
              )}
              {ul != null && (
                <ReferenceLine
                  y={ul}
                  stroke="#dc2626"
                  strokeDasharray="7 5"
                  label={{ value: `UL (${ul})`, fontSize: 10, fill: "#dc2626" }}
                />
              )}
              <Line
                type="monotone"
                dataKey="v"
                name="Vacuum (mbar)"
                stroke="#2563eb"
                strokeWidth={2}
                dot={{ r: 2 }}
                connectNulls
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow-sm overflow-hidden">
        <div className="px-3 py-2 text-xs font-semibold text-slate-500 uppercase border-b bg-slate-50">
          Every poll reading ({readings.length})
        </div>
        <div className="max-h-64 overflow-y-auto scroll-thin">
          <table className="min-w-full text-xs">
            <thead className="bg-slate-50 text-slate-400 sticky top-0">
              <tr>
                <th className="px-3 py-1.5 text-left">Sr.No.</th>
                <th className="px-3 py-1.5 text-left">Time</th>
                <th className="px-3 py-1.5 text-right">Vacuum (mbar)</th>
                <th className="px-3 py-1.5 text-center">Result</th>
              </tr>
            </thead>
            <tbody>
              {readings.map((r, i) => (
                <tr key={`${row.test_id}-${i}`} className="border-t">
                  <td className="px-3 py-1 text-slate-400">{i + 1}</td>
                  <td className="px-3 py-1 text-slate-600 whitespace-nowrap">
                    {fmtTime(r.time)}
                  </td>
                  <td className="px-3 py-1 text-right font-mono tabular">
                    {r.vacuum != null ? Number(r.vacuum).toFixed(3) : "—"}
                  </td>
                  <td className="px-3 py-1 text-center text-slate-500">
                    {r.result || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
