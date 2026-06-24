import { useState } from "react";
import ReportFilters from "../components/ReportFilters";
import ReportSummary from "../components/ReportSummary";
import ReportTable from "../components/ReportTable";
import TrendModal from "../components/TrendModal";
import { getReports, exportReportsUrl } from "../api/client";

function toISODate(d) {
  return d.toISOString().slice(0, 10);
}

const today = toISODate(new Date());

export default function ReportsPage() {
  const [filters, setFilters] = useState({
    start: today,
    end: today,
    model: "",
    line: "",
    gauge: "",
    result: "",
  });
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [trendRow, setTrendRow] = useState(null);

  const runSearch = async (overrideFilters) => {
    const f = overrideFilters || filters;
    if (!f.start || !f.end) {
      alert("Select a date range");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await getReports(f);
      setData(result);
      setHasSearched(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleQuickRange = (days) => {
    const t = new Date();
    const from = new Date(t);
    if (days === 1) {
      from.setDate(t.getDate() - 1);
      t.setDate(t.getDate() - 1);
    } else if (days > 1) {
      from.setDate(t.getDate() - (days - 1));
    }
    const next = { ...filters, start: toISODate(from), end: toISODate(t) };
    setFilters(next);
    runSearch(next);
  };

  const handleExport = () => {
    window.location.href = exportReportsUrl(filters);
  };

  return (
    <main className="p-6 max-w-[1900px] mx-auto">
      <h2 className="text-2xl font-semibold mb-4 font-display">Test Reports</h2>

      <ReportFilters
        filters={filters}
        setFilters={setFilters}
        onSearch={() => runSearch()}
        onExport={handleExport}
        onQuickRange={handleQuickRange}
      />

      {hasSearched && !loading && <ReportSummary data={data} />}

      <ReportTable
        rows={hasSearched ? data : []}
        loading={loading}
        error={error}
        onRowClick={setTrendRow}
        emptyMessage={hasSearched ? "No records found" : "Select a date range and click Search"}
      />

      <TrendModal row={trendRow} onClose={() => setTrendRow(null)} />
    </main>
  );
}
