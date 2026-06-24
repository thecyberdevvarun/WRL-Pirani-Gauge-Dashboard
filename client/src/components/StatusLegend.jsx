const ITEMS = [
  { color: "bg-signal-idle", label: "IDLE" },
  { color: "bg-signal-run", label: "RUNNING" },
  { color: "bg-signal-pass", label: "PASS" },
  { color: "bg-signal-fail", label: "FAIL" },
  { color: "bg-signal-err", label: "ERROR" },
];

export default function StatusLegend() {
  return (
    <div className="flex justify-center flex-wrap gap-6 text-xs mb-4">
      {ITEMS.map(({ color, label }) => (
        <div key={label} className="flex items-center gap-1.5">
          <span className={`w-3 h-3 rounded-full ${color}`} />
          {label}
        </div>
      ))}
      <div className="text-slate-400 ml-2">Click any fixture to view details / auto-fill Gauge ID</div>
    </div>
  );
}
