export default function ReportSummary({ data }) {
  const total = data.length;
  const pass = data.filter((r) => r.final_result === "PASS").length;
  const fail = data.filter((r) => r.final_result === "FAIL").length;
  const other = total - pass - fail;
  const rate = total > 0 ? `${((pass / total) * 100).toFixed(1)}%` : "—";

  const cards = [
    { value: total, label: "Total Tests", color: "text-slate-700" },
    { value: pass, label: "PASS", color: "text-signal-pass" },
    { value: fail, label: "FAIL", color: "text-signal-fail" },
    { value: other, label: "ERROR / Running", color: "text-signal-err" },
    { value: rate, label: "Pass Rate", color: "text-sky-600" },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
      {cards.map((c) => (
        <div key={c.label} className="bg-white rounded-xl shadow p-4 text-center">
          <div className={`text-2xl font-bold tabular ${c.color}`}>{c.value}</div>
          <div className="text-xs text-slate-400 mt-1">{c.label}</div>
        </div>
      ))}
    </div>
  );
}
