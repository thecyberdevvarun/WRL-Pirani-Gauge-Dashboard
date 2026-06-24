import { FiLoader } from "react-icons/fi";

function fmtDateTime(dt) {
  if (!dt || dt === "None" || dt === "NaT") return "—";
  return new Date(dt).toLocaleString();
}

function fmtDuration(start, end) {
  if (!start || !end || end === "None" || end === "NaT") return "—";
  const ms = new Date(end) - new Date(start);
  if (ms <= 0) return "—";
  const m = Math.floor(ms / 60000);
  const s = Math.floor((ms % 60000) / 1000);
  return `${m}m ${String(s).padStart(2, "0")}s`;
}

export default function ReportTable({ rows, loading, error, onRowClick, emptyMessage = "No records found" }) {
  return (
    <section className="bg-white rounded-xl shadow overflow-x-auto scroll-thin">
      {loading && (
        <div className="py-8 text-center text-slate-400 text-sm flex items-center justify-center gap-2">
          <FiLoader className="animate-spin text-emerald-600" /> Loading reports…
        </div>
      )}

      {!loading && (
        <table className="min-w-full text-sm">
          <thead className="bg-slate-100 text-xs text-slate-500 uppercase">
            <tr>
              <th className="px-3 py-2 text-left">Start Time</th>
              <th className="px-3 py-2 text-left">End Time</th>
              <th className="px-3 py-2">Gauge</th>
              <th className="px-3 py-2 text-left">Serial</th>
              <th className="px-3 py-2">Model</th>
              <th className="px-3 py-2 text-left">Model Name</th>
              <th className="px-3 py-2">Line</th>
              <th className="px-3 py-2">Duration</th>
              <th className="px-3 py-2">Last Vac.</th>
              <th className="px-3 py-2">Result</th>
            </tr>
          </thead>
          <tbody>
            {error && (
              <tr>
                <td colSpan={10} className="text-center py-6 text-rose-500">
                  Error loading data: {error}
                </td>
              </tr>
            )}
            {!error && rows.length === 0 && (
              <tr>
                <td colSpan={10} className="text-center py-10 text-slate-400">
                  {emptyMessage}
                </td>
              </tr>
            )}
            {!error &&
              rows.map((r) => {
                const res = r.final_result;
                const resClass =
                  res === "PASS" ? "text-signal-pass font-bold" : res === "FAIL" ? "text-signal-fail font-bold" : "text-signal-err";
                const lastVac = r.last_vacuum != null ? Number(r.last_vacuum).toFixed(3) : "—";
                return (
                  <tr key={r.test_id} onClick={() => onRowClick(r)} className="border-t hover:bg-slate-50 cursor-pointer">
                    <td className="px-3 py-2 text-slate-600 whitespace-nowrap">{fmtDateTime(r.start_time)}</td>
                    <td className="px-3 py-2 text-slate-500 whitespace-nowrap">{fmtDateTime(r.end_time)}</td>
                    <td className="px-3 py-2 text-center font-medium tabular">{r.gauge_id}</td>
                    <td className="px-3 py-2 font-mono text-xs">{r.serial_no || "—"}</td>
                    <td className="px-3 py-2 text-center">{r.model_code || "—"}</td>
                    <td className="px-3 py-2 text-slate-600">{r.model_name || "—"}</td>
                    <td className="px-3 py-2 text-center text-slate-500">{r.line_name || "—"}</td>
                    <td className="px-3 py-2 text-center text-slate-500">{fmtDuration(r.start_time, r.end_time)}</td>
                    <td className="px-3 py-2 text-center font-mono tabular">{lastVac}</td>
                    <td className={`px-3 py-2 text-center ${resClass}`}>{res || "—"}</td>
                  </tr>
                );
              })}
          </tbody>
        </table>
      )}
    </section>
  );
}
