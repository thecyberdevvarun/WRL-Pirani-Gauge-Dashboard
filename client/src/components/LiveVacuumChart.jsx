import { LineChart, Line, XAxis, YAxis, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip } from "recharts";

export default function LiveVacuumChart({ data, ll, ul }) {
  const llNum = Number(ll) || 0;
  const ulNum = Number(ul) || 1;
  const safe = llNum >= ulNum ? { ll: 0, ul: 1 } : { ll: llNum, ul: ulNum };
  const pad = (safe.ul - safe.ll) * 0.18;

  return (
    <div className="h-[170px]">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="t" hide />
          <YAxis
            domain={[safe.ll - pad, safe.ul + pad]}
            tick={{ fontSize: 10, fill: "#64748b" }}
            tickFormatter={(v) => v.toFixed(3)}
            width={48}
          />
          <Tooltip
            formatter={(v) => [`${Number(v).toFixed(3)} mbar`, "Vacuum"]}
            labelFormatter={() => ""}
            contentStyle={{ fontSize: 12 }}
          />
          <ReferenceLine y={safe.ul} stroke="#ef4444" strokeDasharray="5 4" label={{ value: `UL ${safe.ul}`, fontSize: 10, fill: "#ef4444", position: "insideTopRight" }} />
          <ReferenceLine y={safe.ll} stroke="#facc15" strokeDasharray="5 4" label={{ value: `LL ${safe.ll}`, fontSize: 10, fill: "#b45309", position: "insideBottomRight" }} />
          <Line type="monotone" dataKey="v" stroke="#16a34a" strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
