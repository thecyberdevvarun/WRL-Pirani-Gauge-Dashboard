import { useState } from "react";
import { FiPlay } from "react-icons/fi";
import { getRecipeByModel, startTest as startTestApi } from "../api/client";
import { toast } from "react-hot-toast";

const LINES = [
  { value: "", label: "Select Line" },
  { value: "FREEZER", label: "Freezer" },
  { value: "SUS", label: "SUS" },
  { value: "CHOCOLATE", label: "Chocolate" },
];

function extractModelCode(serial) {
  return serial.substring(2, 6);
}

function validateSerial(serial) {
  if (serial.length !== 15) return { ok: false, msg: "Serial must be exactly 15 characters" };
  if (!serial.startsWith("S4")) return { ok: false, msg: "Serial must start with S4" };
  if (!/^S4\d{13}$/.test(serial)) return { ok: false, msg: "Invalid serial format (S4 + 13 digits)" };
  return { ok: true };
}

export default function ScanPanel({ gaugeId, onGaugeIdChange, onStarted }) {
  // using react-hot-toast
  const [line, setLine] = useState("");
  const [serial, setSerial] = useState("");
  const [modelCode, setModelCode] = useState("");
  const [modelName, setModelName] = useState("");
  const [starting, setStarting] = useState(false);

  const handleSerialBlur = async () => {
    const s = serial.trim();
    const v = validateSerial(s);
    if (!v.ok) return;
    const code = extractModelCode(s);
    setModelCode(code);
    try {
      const recipe = await getRecipeByModel(code);
      setModelName(recipe.exists ? recipe.model_name : "NOT DEFINED");
    } catch {
      setModelName("NOT DEFINED");
    }
  };

  const handleStart = async () => {
    const serialNo = serial.trim();
    const gid = parseInt(gaugeId, 10);

    if (!serialNo) return toast.error("Serial number required");
    const v = validateSerial(serialNo);
    if (!v.ok) return toast.error(v.msg);
    if (!gid || gid < 1 || gid > 64) return toast.error("Enter a valid Gauge ID (1–64)");

    const code = extractModelCode(serialNo);
    setStarting(true);
    try {
      const recipe = await getRecipeByModel(code);
        if (!recipe.exists) {
        setModelCode(code);
        setModelName("NOT DEFINED");
        toast("Recipe not found for this model", { icon: "⚠️" });
        return;
      }
      setModelCode(code);
      setModelName(recipe.model_name);

      const res = await startTestApi({ serial_no: serialNo, gauge_id: gid, line, model_code: code });
      if (res.status === "STARTED") {
        toast.success(`Test started on Gauge ${gid}`);
        setSerial("");
        onGaugeIdChange("");
        setModelCode("");
        setModelName("");
        onStarted?.();
      } else {
        toast.error(res.message || "Error starting test");
      }
    } catch {
      toast.error("Network error — check server");
    } finally {
      setStarting(false);
    }
  };

  return (
    <section className="bg-white border rounded-xl p-5 shadow">
      <h3 className="text-base font-semibold text-emerald-600 mb-4 font-display flex items-center gap-1.5">
        <FiPlay /> Start Test
      </h3>

      <label className="block text-xs mb-1 text-slate-500">Conveyor Line</label>
      <select
        value={line}
        onChange={(e) => setLine(e.target.value)}
        aria-label="Conveyor Line"
        className="w-full mb-3 px-3 py-2 rounded border focus:border-emerald-600 outline-none text-sm"
      >
        {LINES.map((l) => (
          <option key={l.value} value={l.value}>
            {l.label}
          </option>
        ))}
      </select>

      <label className="block text-xs mb-1 text-slate-500">Serial Number</label>
      <input
        value={serial}
        onChange={(e) => setSerial(e.target.value)}
        onBlur={handleSerialBlur}
        placeholder="Scan or type serial"
        className="w-full mb-3 px-3 py-2 rounded border focus:border-emerald-600 outline-none text-sm"
      />

      <label className="block text-xs mb-1 text-slate-500">
        Gauge ID <span className="text-slate-400">(click fixture to fill)</span>
      </label>
      <input
        type="number"
        min={1}
        max={64}
        value={gaugeId}
        onChange={(e) => onGaugeIdChange(e.target.value)}
        placeholder="1 – 64"
        className="w-full mb-3 px-3 py-2 rounded border focus:border-emerald-600 outline-none text-sm"
      />

      <label className="block text-xs mb-1 text-slate-500">Model Code</label>
      <input
        disabled
        value={modelCode}
        placeholder="—"
        className="w-full mb-1 px-3 py-2 rounded bg-slate-100 text-slate-500 text-sm"
      />

      <label className="block text-xs mb-1 text-slate-500">Model Name</label>
      <input
        disabled
        value={modelName}
        placeholder="—"
        className="w-full mb-5 px-3 py-2 rounded bg-slate-100 text-emerald-700 font-semibold text-sm"
      />

      <button
        type="button"
        onClick={handleStart}
        disabled={starting}
        className="w-full py-3 rounded bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white font-bold text-base transition"
      >
        {starting ? "Starting…" : "START TEST"}
      </button>

      <p className="text-xs text-slate-400 mt-2 text-center">
        Serial format: <code className="bg-slate-100 px-1 rounded">S4</code> + 4-digit model code + 9 digits
      </p>
    </section>
  );
}
