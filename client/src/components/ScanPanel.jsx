import { useEffect, useRef, useState } from "react";
import { useSelector } from "react-redux";
import { FiPlay } from "react-icons/fi";
import { getMaterialByCode, startTest as startTestApi } from "../api/client";
import { toast } from "react-hot-toast";

function extractModelCode(serial) {
  return serial.substring(2, 6);
}

function validateSerial(serial) {
  if (serial.length !== 15)
    return { ok: false, msg: "Serial must be exactly 15 characters" };
  if (!serial.startsWith("S4"))
    return { ok: false, msg: "Serial must start with S4" };
  if (!/^S4\d{13}$/.test(serial))
    return { ok: false, msg: "Invalid serial format (S4 + 13 digits)" };
  return { ok: true };
}

export default function ScanPanel({
  gaugeId,
  gaugeIds,
  lineLabel,
  onGaugeIdChange,
  onStarted,
}) {
  const line = useSelector((s) => s.auth.line);

  const [serial, setSerial] = useState("");
  const [modelCode, setModelCode] = useState("");
  const [modelName, setModelName] = useState("");
  const [starting, setStarting] = useState(false);
  const serialRef = useRef(null);
  const gaugeRef = useRef(null);

  useEffect(() => {
    serialRef.current?.focus();
  }, []);

  const handleSerialChange = (e) => {
    const v = e.target.value;
    setSerial(v);
    // Scanners type the full serial instantly — jump on to Gauge ID once it is complete.
    if (validateSerial(v.trim()).ok) gaugeRef.current?.focus();
  };

  const handleSerialKeyDown = (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    gaugeRef.current?.focus();
  };

  const handleGaugeKeyDown = (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    if (!starting) handleStart();
  };

  const handleSerialBlur = async () => {
    const s = serial.trim();
    const v = validateSerial(s);
    if (!v.ok) return;
    const code = extractModelCode(s);
    setModelCode(code);
    try {
      const material = await getMaterialByCode(code);
      setModelName(material.exists ? material.name : "UNKNOWN MODEL");
    } catch {
      setModelName("UNKNOWN MODEL");
    }
  };

  const handleStart = async () => {
    if (!line) return toast.error("No line selected — please log in again");

    const serialNo = serial.trim();
    const gid = parseInt(gaugeId, 10);

    if (!serialNo) return toast.error("Serial number required");
    const v = validateSerial(serialNo);
    if (!v.ok) return toast.error(v.msg);
    if (!gid || !gaugeIds.includes(gid))
      return toast.error("Enter a valid Gauge ID for this line");

    const code = extractModelCode(serialNo);
    setStarting(true);
    try {
      // Display-only — a missing Material record no longer blocks starting a test.
      const material = await getMaterialByCode(code).catch(() => ({ exists: false, name: null }));
      setModelCode(code);
      setModelName(material.exists ? material.name : "UNKNOWN MODEL");

      const res = await startTestApi({
        serial_no: serialNo,
        gauge_id: gid,
        line,
        model_code: code,
      });
      if (res.status === "STARTED") {
        toast.success(`Test started on Gauge ${gid}`);
        setSerial("");
        onGaugeIdChange("");
        setModelCode("");
        setModelName("");
        onStarted?.();
        serialRef.current?.focus();
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
      <h3 className="text-base font-semibold text-emerald-600 mb-1 font-display flex items-center gap-1.5">
        <FiPlay /> Start Test
      </h3>
      <p className="text-xs text-slate-400 mb-4">
        Line:{" "}
        <span className="font-semibold text-slate-600">
          {lineLabel || "—"}
        </span>
        {gaugeIds.length ? ` · ${gaugeIds.length} gauges` : ""}
      </p>

      <label className="block text-xs mb-1 text-slate-500">Serial Number</label>
      <input
        ref={serialRef}
        value={serial}
        onChange={handleSerialChange}
        onKeyDown={handleSerialKeyDown}
        onBlur={handleSerialBlur}
        placeholder="Scan or type serial"
        className="w-full mb-3 px-3 py-2 rounded border focus:border-emerald-600 outline-none text-sm"
      />

      <label className="block text-xs mb-1 text-slate-500">
        Gauge ID <span className="text-slate-400">(click fixture to fill)</span>
      </label>
      <input
        ref={gaugeRef}
        type="number"
        value={gaugeId}
        onKeyDown={handleGaugeKeyDown}
        onChange={(e) => onGaugeIdChange(e.target.value)}
        placeholder={gaugeIds.length ? "e.g. " + gaugeIds[0] : "—"}
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
        Serial format: <code className="bg-slate-100 px-1 rounded">S4</code> +
        4-digit model code + 9 digits
      </p>
    </section>
  );
}
