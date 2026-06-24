import { useEffect, useMemo, useRef, useState } from "react";
import { FiActivity } from "react-icons/fi";

const COLOR_MAP = {
  green: "bg-signal-pass text-white",
  red: "bg-signal-fail text-white",
  yellow: "bg-signal-run text-ink-950",
  orange: "bg-signal-err text-white",
  gray: "bg-signal-idle text-white",
};

export default function ConveyorTrack({
  fixtures,
  gaugeCount,
  lineLabel,
  onSelect,
}) {
  const pathRef = useRef(null);
  const [points, setPoints] = useState([]);

  // 🔥 Compute positions ON the curved rectangle
  useEffect(() => {
    if (!pathRef.current || gaugeCount === 0) return;

    const path = pathRef.current;
    const length = path.getTotalLength();

    const newPoints = [];
    for (let i = 0; i < gaugeCount; i++) {
      const pt = path.getPointAtLength((i / gaugeCount) * length);
      newPoints.push(pt);
    }

    setPoints(newPoints);
  }, [gaugeCount]);

  if (!gaugeCount) {
    return (
      <section className="relative bg-white border rounded-xl shadow w-full aspect-[16/10] flex items-center justify-center">
        <div className="text-center text-slate-400">
          <FiActivity className="mx-auto text-4xl mb-3" />
          <p>Please select a line</p>
        </div>
      </section>
    );
  }

  return (
    <section className="relative bg-white border rounded-xl shadow w-full aspect-[16/10]">
      {/* Title */}
      <div className="absolute top-3 left-4 text-xs font-semibold text-slate-500">
        {lineLabel} — {gaugeCount} gauges
      </div>

      {/* SVG Track */}
      <svg className="absolute inset-0 w-full h-full">
        <rect
          ref={pathRef}
          x="5%"
          y="5%"
          width="90%"
          height="90%"
          rx="15%" // 🔥 rounded corners
          ry="15%"
          fill="none"
          stroke="#e2e8f0"
          strokeWidth="2"
          strokeDasharray="6 6"
        />
      </svg>

      {/* Gauges */}
      <div className="absolute inset-0">
        {fixtures.map((f, i) => {
          const pt = points[(f.slave_id - 1) % points.length];
          if (!pt) return null;

          return (
            <button
              key={f.slave_id}
              onClick={() => onSelect(f.slave_id)}
              title={`Gauge ${f.slave_id}`}
              className={`absolute flex items-center justify-center rounded-full font-bold shadow
                w-[clamp(28px,4vw,44px)] h-[clamp(28px,4vw,44px)]
                ${COLOR_MAP[f.color] || COLOR_MAP.gray}
              `}
              style={{
                left: pt.x,
                top: pt.y,
                transform: "translate(-50%, -50%)",
              }}
            >
              {f.slave_id}
            </button>
          );
        })}
      </div>
    </section>
  );
}
