import { useMemo } from "react";

const SLOT_COUNT = 64;
const BOUNDS = { left: 40, top: 36, right: 860, bottom: 524 };

const COLOR_MAP = {
  green: "bg-signal-pass text-white",
  red: "bg-signal-fail text-white",
  yellow: "bg-signal-run text-ink-950",
  orange: "bg-signal-err text-white",
  gray: "bg-signal-idle text-white",
};

/** Computes evenly-spaced perimeter coordinates around the rectangle-with-rounded-ends track. */
function buildSlots() {
  const { left, top, right, bottom } = BOUNDS;
  const w = right - left;
  const h = bottom - top;
  const spacing = (2 * (w + h)) / SLOT_COUNT;
  const slots = [];
  for (let i = 0; i < SLOT_COUNT; i++) {
    let d = i * spacing;
    if (d <= w) slots.push({ x: left + d, y: top });
    else if ((d -= w) <= h) slots.push({ x: right, y: top + d });
    else if ((d -= h) <= w) slots.push({ x: right - d, y: bottom });
    else slots.push({ x: left, y: bottom - (d - w) });
  }
  return slots;
}

export default function ConveyorTrack({ fixtures, onSelect }) {
  const slots = useMemo(buildSlots, []);

  return (
    <section className="relative bg-white border rounded-xl shadow h-[600px] overflow-hidden">
      <div className="absolute top-3 right-4 text-xs text-slate-400 font-medium">↓ ENTRY</div>
      <div className="absolute bottom-3 right-4 text-xs text-slate-400 font-medium">↑ EXIT</div>

      {/* the track itself, drawn as a rounded rectangle outline */}
      <div
        className="absolute border-2 border-dashed border-slate-200 rounded-[120px]"
        style={{
          left: BOUNDS.left - 22,
          top: BOUNDS.top - 22,
          width: BOUNDS.right - BOUNDS.left + 44,
          height: BOUNDS.bottom - BOUNDS.top + 44,
        }}
      />

      <div className="absolute inset-0">
        {fixtures.map((f) => {
          const slot = slots[(f.slave_id - 1) % SLOT_COUNT];
          if (!slot) return null;
          return (
            <button
              type="button"
              key={f.slave_id}
              onClick={() => onSelect(f.slave_id)}
              title={`Gauge ${f.slave_id} — ${f.status}${f.serial_no ? " | " + f.serial_no : ""}`}
              className={`absolute w-11 h-11 rounded-full flex items-center justify-center font-bold shadow text-xs select-none transition-transform hover:scale-110 tabular ${
                COLOR_MAP[f.color] || COLOR_MAP.gray
              } ${f.status === "RUNNING" ? "running-pulse" : ""}`}
              style={{ left: slot.x - 22, top: slot.y - 22 }}
            >
              {f.slave_id}
            </button>
          );
        })}
      </div>
    </section>
  );
}
