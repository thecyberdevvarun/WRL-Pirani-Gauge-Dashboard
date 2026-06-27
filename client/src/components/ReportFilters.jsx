import { FiSearch, FiDownload } from "react-icons/fi";
import { LINES as LINE_CONFIG } from "../config/lines";

const QUICK_RANGES = [
  { label: "Today", days: 0 },
  { label: "Yesterday", days: 1 },
  { label: "Last 7 Days", days: 7 },
  { label: "Last 30 Days", days: 30 },
];

export default function ReportFilters({
  filters,
  setFilters,
  onSearch,
  onExport,
  onQuickRange,
}) {
  const update = (key) => (e) =>
    setFilters((f) => ({ ...f, [key]: e.target.value }));

  return (
    <section className="bg-white rounded-xl shadow p-5 mb-4">
      <div className="flex flex-wrap gap-2 mb-3">
        <span className="text-xs text-slate-500 self-center mr-1">Quick:</span>
        {QUICK_RANGES.map((r) => (
          <button
            key={r.label}
            type="button"
            onClick={() => onQuickRange(r.days)}
            className="px-3 py-1 text-xs rounded border hover:bg-emerald-50 hover:border-emerald-500 hover:text-emerald-700"
          >
            {r.label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3 items-end">
        <div>
          <label className="block text-xs font-medium mb-1">From Date</label>
          <input
            type="date"
            value={filters.start}
            onChange={update("start")}
            className="w-full px-3 py-2 border rounded text-sm"
          />
        </div>
        <div>
          <label className="block text-xs font-medium mb-1">To Date</label>
          <input
            type="date"
            value={filters.end}
            onChange={update("end")}
            className="w-full px-3 py-2 border rounded text-sm"
          />
        </div>
        <div>
          <label className="block text-xs font-medium mb-1">Model Code</label>
          <input
            type="text"
            value={filters.model}
            onChange={update("model")}
            placeholder="e.g. 1234"
            className="w-full px-3 py-2 border rounded text-sm"
          />
        </div>
        <div>
          <label className="block text-xs font-medium mb-1">Line</label>
          <select
            value={filters.line}
            onChange={update("line")}
            className="w-full px-3 py-2 border rounded text-sm"
          >
            <option value="">All Lines</option>
            {LINE_CONFIG.map((l) => (
              <option key={l.key} value={l.key}>
                {l.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium mb-1">Gauge ID</label>
          <input
            type="number"
            min="1"
            max="64"
            value={filters.gauge}
            onChange={update("gauge")}
            placeholder="1–64"
            className="w-full px-3 py-2 border rounded text-sm"
          />
        </div>
        <div>
          <label className="block text-xs font-medium mb-1">Result</label>
          <select
            value={filters.result}
            onChange={update("result")}
            className="w-full px-3 py-2 border rounded text-sm"
          >
            <option value="">All</option>
            <option value="PASS">PASS</option>
            <option value="FAIL">FAIL</option>
          </select>
        </div>
        <div>
          <button
            type="button"
            onClick={onSearch}
            className="w-full flex items-center justify-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-sm font-semibold"
          >
            <FiSearch /> Search
          </button>
        </div>
        <div>
          <button
            type="button"
            onClick={onExport}
            className="w-full flex items-center justify-center gap-1.5 px-4 py-2 bg-sky-600 hover:bg-sky-700 text-white rounded text-sm font-semibold"
          >
            <FiDownload /> Excel
          </button>
        </div>
      </div>
    </section>
  );
}
