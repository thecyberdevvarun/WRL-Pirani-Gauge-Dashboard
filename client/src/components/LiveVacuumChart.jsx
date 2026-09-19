import { LineChart, Line, XAxis, YAxis, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip } from "recharts";

export default function LiveVacuumChart({ data, ul }) {
  const ulNum = Number(ul) || 1;
  const values = data.map((d) => d.v).filter((v) => typeof v === "number" && Number.isFinite(v));

  // No lower limit concept anymore — the axis floor just comes from the
  // data itself (readings are never negative in practice), the ceiling
  // from whichever is bigger: the Upper Limit or the highest reading seen.
  const floor = Math.min(0, ...values);
  const ceiling = Math.max(ulNum, ...values);
  const pad = (ceiling - floor) * 0.18 || 0.05;

  return (
    <div className="h-42.5">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="t" hide />
          <YAxis
            domain={[floor - pad, ceiling + pad]}
            tick={{ fontSize: 10, fill: "#64748b" }}
            tickFormatter={(v) => v.toFixed(3)}
            width={48}
          />
          <Tooltip
            formatter={(v) => [`${Number(v).toFixed(3)} mbar`, "Vacuum"]}
            labelFormatter={() => ""}
            contentStyle={{ fontSize: 12 }}
          />
          <ReferenceLine y={ulNum} stroke="#ef4444" strokeDasharray="5 4" label={{ value: `UL ${ulNum}`, fontSize: 10, fill: "#ef4444", position: "insideTopRight" }} />
          <Line type="monotone" dataKey="v" stroke="#16a34a" strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
