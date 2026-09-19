import { useEffect, useMemo, useRef, useState } from "react";
import { FiActivity } from "react-icons/fi";

const COLOR_MAP = {
  green: "bg-signal-pass text-white",
  red: "bg-signal-fail text-white",
  yellow: "bg-signal-run text-ink-950",
  orange: "bg-signal-err text-white",
  gray: "bg-signal-idle text-white",
};

const MARKER_DOT_MAP = {
  green: "bg-signal-pass",
  red: "bg-signal-fail",
  yellow: "bg-signal-run",
  orange: "bg-signal-err",
  gray: "bg-signal-idle",
};

const MS_PER_STEP = 450;
const MIN_LAP_MS = 1600;
const MAX_LAP_MS = 9000;

function lerp(a, b, t) {
  return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t };
}

/** Animates a small dot forward around the ring (increasing index, wrapping)
 * from the IN gauge's point to its configured exit point, looping
 * continuously — matching auto_stop_cycle_gauge in app.py, which now sweeps
 * the `gap` positions ahead of the scanned-in gauge. This is a decorative
 * approximation — there's no real position sensor feeding this, so it's
 * paced by a fixed animation speed, not actual elapsed/remaining test time. */
function TravelingMarker({ points, fromIdx, toIdx, color, fromLabel, toLabel }) {
  const [pos, setPos] = useState(null);
  const frameRef = useRef(null);

  const waypoints = useMemo(() => {
    const n = points.length;
    if (!n) return [];
    const steps = ((toIdx - fromIdx) % n + n) % n;
    if (steps === 0) return [];
    const pts = [];
    for (let s = 0; s <= steps; s++) {
      pts.push(points[((fromIdx + s) % n + n) % n]);
    }
    return pts;
  }, [points, fromIdx, toIdx]);

  useEffect(() => {
    if (waypoints.length < 2) {
      setPos(null);
      return undefined;
    }

    const steps = waypoints.length - 1;
    const durationMs = Math.min(MAX_LAP_MS, Math.max(MIN_LAP_MS, steps * MS_PER_STEP));
    const start = performance.now();

    const tick = (now) => {
      const elapsed = (now - start) % durationMs;
      const t = (elapsed / durationMs) * steps;
      const segIdx = Math.min(Math.max(Math.floor(t), 0), steps - 1);
      const frac = t - segIdx;
      const a = waypoints[segIdx];
      const b = waypoints[segIdx + 1];
      if (a && b) setPos(lerp(a, b, frac));
      frameRef.current = requestAnimationFrame(tick);
    };
    frameRef.current = requestAnimationFrame(tick);

    return () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
    };
  }, [waypoints]);

  if (!pos) return null;

  return (
    <div
      className="absolute pointer-events-none"
      style={{ left: pos.x, top: pos.y, transform: "translate(-50%, -50%)" }}
      title={`En route: Gauge ${fromLabel} → Gauge ${toLabel}`}
    >
      <span
        className={`absolute inset-0 -m-1.5 rounded-full ${MARKER_DOT_MAP[color] || MARKER_DOT_MAP.gray} opacity-40 animate-ping`}
      />
      <span
        className={`block w-3 h-3 rounded-full ring-2 ring-white shadow ${MARKER_DOT_MAP[color] || MARKER_DOT_MAP.gray}`}
      />
    </div>
  );
}

export default function ConveyorTrack({
  fixtures,
  gaugeIds,
  lineLabel,
  gap = 0,
  onSelect,
}) {
  const pathRef = useRef(null);
  const [points, setPoints] = useState([]);
  const gaugeCount = gaugeIds.length;

  // Compute positions ON the curved rectangle
  useEffect(() => {
    if (!pathRef.current || gaugeCount === 0) return;

    const path = pathRef.current;
    const length = path.getTotalLength();

    // SVG <rect> paths are traced clockwise by default (right along the top,
    // down the right side, left along the bottom, up the left side). Walking
    // the index backward from 0 keeps gauge 1 anchored at the same starting
    // point but places every other gauge counter-clockwise from it instead.
    const newPoints = [];
    for (let i = 0; i < gaugeCount; i++) {
      const t = (gaugeCount - i) % gaugeCount;
      const pt = path.getPointAtLength((t / gaugeCount) * length);
      newPoints.push(pt);
    }

    setPoints(newPoints);
  }, [gaugeCount]);

  // Map slave_id -> its position index in gaugeIds, since gauges may not
  // be a contiguous 1..N range once configured via Settings.
  const indexBySlaveId = useMemo(
    () => new Map(gaugeIds.map((id, i) => [id, i])),
    [gaugeIds]
  );

  if (!gaugeCount) {
    return (
      <section className="relative bg-white border rounded-xl shadow w-full aspect-16/10 flex items-center justify-center">
        <div className="text-center text-slate-400">
          <FiActivity className="mx-auto text-4xl mb-3" />
          <p>Please select a line</p>
        </div>
      </section>
    );
  }

  return (
    <section className="relative bg-white border rounded-xl shadow w-full aspect-16/10">
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
          rx="15%" // rounded corners
          ry="15%"
          fill="none"
          stroke="#e2e8f0"
          strokeWidth="2"
          strokeDasharray="6 6"
        />
      </svg>

      {/* Traveling markers for running tests, moving from their IN gauge
          toward the line's configured IN/OUT exit gauge */}
      {gap > 0 &&
        points.length > 0 &&
        fixtures
          .filter((f) => f.status === "RUNNING")
          .map((f) => {
            const fromIdx = indexBySlaveId.get(f.slave_id);
            if (fromIdx === undefined) return null;
            const toIdx = ((fromIdx + gap) % gaugeCount + gaugeCount) % gaugeCount;
            const toSlaveId = gaugeIds[toIdx];
            return (
              <TravelingMarker
                key={`marker-${f.slave_id}`}
                points={points}
                fromIdx={fromIdx}
                toIdx={toIdx}
                color={f.color}
                fromLabel={f.slave_id}
                toLabel={toSlaveId}
              />
            );
          })}

      {/* Gauges */}
      <div className="absolute inset-0">
        {fixtures.map((f) => {
          const idx = indexBySlaveId.get(f.slave_id);
          const pt = idx === undefined ? undefined : points[idx];
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
