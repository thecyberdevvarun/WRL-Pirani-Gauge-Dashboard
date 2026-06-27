import { Fragment } from "react";
import {
  FiLoader,
  FiChevronDown,
  FiChevronRight,
  FiFileText,
} from "react-icons/fi";
import ReportAccordion from "./ReportAccordion";
import { reportPdfUrl } from "../api/client";

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

const RESULT_BADGE = {
  PASS: "bg-signal-pass/10 text-signal-pass ring-1 ring-inset ring-signal-pass/30",
  FAIL: "bg-signal-fail/10 text-signal-fail ring-1 ring-inset ring-signal-fail/30",
};
const DEFAULT_BADGE =
  "bg-signal-err/10 text-signal-err ring-1 ring-inset ring-signal-err/30";

const COLUMN_COUNT = 11;

export default function ReportTable({
  rows,
  loading,
  error,
  expandedId,
  onToggleExpand,
  emptyMessage = "No records found",
}) {
  return (
    <section className="bg-white rounded-xl shadow overflow-x-auto scroll-thin">
      {loading && (
        <div className="py-8 text-center text-slate-400 text-sm flex items-center justify-center gap-2">
          <FiLoader className="animate-spin text-emerald-600" /> Loading
          reports…
        </div>
      )}

      {!loading && (
        <table className="min-w-full text-sm">
          <thead className="bg-ink-900 text-[11px] text-slate-300 uppercase tracking-wide">
            <tr>
              <th className="px-3 py-2.5 w-6" />
              <th className="px-3 py-2.5 text-left">Start Time</th>
              <th className="px-3 py-2.5 text-left">End Time</th>
              <th className="px-3 py-2.5">Gauge</th>
              <th className="px-3 py-2.5 text-left">Serial</th>
              <th className="px-3 py-2.5">Model</th>
              <th className="px-3 py-2.5 text-left">Model Name</th>
              <th className="px-3 py-2.5">Line</th>
              <th className="px-3 py-2.5">Duration</th>
              <th className="px-3 py-2.5">Last Vac.</th>
              <th className="px-3 py-2.5">Result</th>
              <th className="px-3 py-2.5">PDF</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {error && (
              <tr>
                <td
                  colSpan={COLUMN_COUNT + 1}
                  className="text-center py-6 text-signal-fail"
                >
                  Error loading data: {error}
                </td>
              </tr>
            )}
            {!error && rows.length === 0 && (
              <tr>
                <td
                  colSpan={COLUMN_COUNT + 1}
                  className="text-center py-10 text-slate-400"
                >
                  {emptyMessage}
                </td>
              </tr>
            )}
            {!error &&
              rows.map((r, idx) => {
                const res = r.final_result;
                const badgeClass = RESULT_BADGE[res] || DEFAULT_BADGE;
                const lastVac =
                  r.last_vacuum != null
                    ? Number(r.last_vacuum).toFixed(3)
                    : "—";
                const isOpen = expandedId === r.test_id;
                const zebra = idx % 2 === 0 ? "bg-white" : "bg-slate-50/60";

                return (
                  <Fragment key={r.test_id}>
                    <tr
                      onClick={() => onToggleExpand(r.test_id)}
                      className={`cursor-pointer transition-colors ${
                        isOpen
                          ? "bg-emerald-50 hover:bg-emerald-50"
                          : `${zebra} hover:bg-emerald-50/50`
                      }`}
                    >
                      <td className="px-3 py-2 text-center">
                        {isOpen ? (
                          <FiChevronDown className="text-emerald-600" />
                        ) : (
                          <FiChevronRight className="text-slate-400" />
                        )}
                      </td>
                      <td className="px-3 py-2 text-slate-700 whitespace-nowrap">
                        {fmtDateTime(r.start_time)}
                      </td>
                      <td className="px-3 py-2 text-slate-500 whitespace-nowrap">
                        {fmtDateTime(r.end_time)}
                      </td>
                      <td className="px-3 py-2 text-center font-semibold text-ink-900 tabular">
                        {r.gauge_id}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-slate-600">
                        {r.serial_no || "—"}
                      </td>
                      <td className="px-3 py-2 text-center text-slate-700">
                        {r.model_code || "—"}
                      </td>
                      <td className="px-3 py-2 text-slate-600">
                        {r.model_name || "—"}
                      </td>
                      <td className="px-3 py-2 text-center text-slate-500">
                        {r.line_name || "—"}
                      </td>
                      <td className="px-3 py-2 text-center text-slate-500 tabular">
                        {fmtDuration(r.start_time, r.end_time)}
                      </td>
                      <td className="px-3 py-2 text-center font-mono tabular text-slate-700">
                        {lastVac}
                      </td>
                      <td className="px-3 py-2 text-center">
                        <span
                          className={`inline-block px-2.5 py-1 rounded-full text-xs font-bold ${badgeClass}`}
                        >
                          {res || "—"}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-center">
                        <a
                          href={reportPdfUrl(r.test_id)}
                          onClick={(e) => e.stopPropagation()}
                          title="Download report as PDF"
                          className="inline-flex items-center justify-center w-7 h-7 rounded-md text-slate-400 hover:text-white hover:bg-ink-900 transition-colors"
                        >
                          <FiFileText size={15} />
                        </a>
                      </td>
                    </tr>

                    {isOpen && (
                      <tr className="bg-emerald-50">
                        <td
                          colSpan={COLUMN_COUNT + 1}
                          className="p-0 border-l-4 border-emerald-500"
                        >
                          <ReportAccordion row={r} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
          </tbody>
        </table>
      )}
    </section>
  );
}
