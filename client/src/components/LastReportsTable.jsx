import { Link } from "react-router-dom";

const RESULT_CLASS = {
  PASS: "text-signal-pass",
  FAIL: "text-signal-fail",
};

export default function LastReportsTable({ rows, onRowClick }) {
  return (
    <section className="mt-5 mx-4 bg-white border rounded-xl shadow mb-6">
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <span className="font-semibold text-slate-700 font-display">
          Your Latest Scan
        </span>
        <Link
          to="/reports"
          className="text-xs text-emerald-700 hover:underline"
        >
          View all →
        </Link>
      </div>
      <div className="overflow-x-auto scroll-thin">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs text-slate-500 uppercase">
            <tr>
              <th className="px-3 py-2 text-left">Time</th>
              <th className="px-3 py-2">Gauge</th>
              <th className="px-3 py-2 text-left">Serial</th>
              <th className="px-3 py-2">Model</th>
              <th className="px-3 py-2">Line</th>
              <th className="px-3 py-2">Result</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={6} className="text-center py-6 text-slate-400">
                  No test results yet
                </td>
              </tr>
            )}
            {rows.map((r) => (
              <tr
                key={r.test_id}
                onClick={() => onRowClick?.(r.gauge_id)}
                className="hover:bg-slate-50 cursor-pointer border-t"
              >
                <td className="px-3 py-2 text-slate-500 whitespace-nowrap">
                  {r.start_time ? new Date(r.start_time).toLocaleString() : "—"}
                </td>
                <td className="px-3 py-2 text-center font-medium tabular">
                  {r.gauge_id}
                </td>
                <td className="px-3 py-2 font-mono text-xs">
                  {r.serial_no || "—"}
                </td>
                <td className="px-3 py-2 text-center">{r.model_code || "—"}</td>
                <td className="px-3 py-2 text-center text-slate-500">
                  {r.line_name || "—"}
                </td>
                <td
                  className={`px-3 py-2 text-center font-bold ${RESULT_CLASS[r.final_result] || "text-orange-500"}`}
                >
                  {r.final_result || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
