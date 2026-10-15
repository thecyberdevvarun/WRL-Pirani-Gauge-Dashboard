// One place that defines how every status in the spec is shown, so the live
// panel, the settings page and the diagnostics all use the same colours.
const GREEN = "bg-emerald-100 text-emerald-700";
const AMBER = "bg-amber-100 text-amber-700";
const RED = "bg-rose-100 text-rose-700";
const GREY = "bg-slate-200 text-slate-600";

const STYLES = {
  connection: {
    connected: [GREEN, "Connected"],
    disconnected: [RED, "Disconnected"],
    unknown: [GREY, "Unknown"],
  },
  polling: {
    running: [GREEN, "Running"],
    delayed: [AMBER, "Delayed"],
    error: [RED, "Error"],
    stopped: [GREY, "Stopped"],
  },
  communication: {
    success: [GREEN, "OK"],
    timeout: [RED, "Timeout"],
    connection_error: [RED, "Connection error"],
    invalid_response: [RED, "Invalid response"],
    modbus_exception: [RED, "Modbus exception"],
    decode_error: [RED, "Decode error"],
  },
  freshness: {
    valid: [GREEN, "Live"],
    stale: [AMBER, "Stale"],
    unavailable: [GREY, "No data"],
  },
};

export default function StatusBadge({ kind, value, className = "" }) {
  const [cls, label] = STYLES[kind]?.[value] || [GREY, value ? String(value) : "Not read yet"];
  return (
    <span
      className={`inline-block px-1.5 py-0.5 rounded text-[11px] font-semibold whitespace-nowrap ${cls} ${className}`}
    >
      {label}
    </span>
  );
}
