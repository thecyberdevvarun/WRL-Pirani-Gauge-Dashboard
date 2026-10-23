import { useEffect, useRef, useState } from "react";
import { useSelector } from "react-redux";
import { FiPlay } from "react-icons/fi";
import { getMaterialByCode, startTest as startTestApi } from "../api/client";
import { toast } from "react-hot-toast";

function extractModelCode(serial) {
  return serial.substring(2, 6);
}

function validateSerial(serial) {
  const normalizedSerial = serial.trim().toUpperCase();

  if (normalizedSerial.length !== 15) {
    return {
      ok: false,
      msg: "Serial must be exactly 15 characters",
    };
  }

  if (!normalizedSerial.startsWith("S4")) {
    return {
      ok: false,
      msg: "Serial must start with S4",
    };
  }

  if (!/^S4\d{13}$/.test(normalizedSerial)) {
    return {
      ok: false,
      msg: "Invalid serial format (S4 + 13 digits)",
    };
  }

  return { ok: true };
}

// Accept any gauge ID with 1 or 2 digits.
function validateGauge(value) {
  if (!value) {
    return {
      ok: false,
      msg: "Gauge ID required",
    };
  }

  if (!/^\d{1,2}$/.test(value)) {
    return {
      ok: false,
      msg: "Gauge ID must contain only 1 or 2 digits",
    };
  }

  if (value.startsWith("0")) {
    return {
      ok: false,
      msg: "Gauge ID cannot start with 0",
    };
  }

  return { ok: true };
}

export default function ScanPanel({
  gaugeId,
  gaugeIds = [],
  lineLabel,
  onGaugeIdChange,
  onStarted,
}) {
  const line = useSelector((s) => s.auth.line);

  const [serial, setSerial] = useState("");
  const [modelCode, setModelCode] = useState("");
  const [modelName, setModelName] = useState("");
  const [starting, setStarting] = useState(false);
  const [serialLockedState, setSerialLockedState] = useState(false);

  const serialRef = useRef(null);
  const gaugeRef = useRef(null);
  const startButtonRef = useRef(null);

  // Ref prevents duplicate scans before React re-renders.
  const serialLocked = useRef(false);

  // Tracks the time Gauge ID receives focus.
  const gaugeFocusedAt = useRef(0);

  const serialValid = validateSerial(serial.trim()).ok;

  const gaugeValue = String(gaugeId ?? "");
  const gaugeValidation = validateGauge(gaugeValue);
  const gaugeTouched = gaugeValue !== "";

  const canStart = serialValid && gaugeValidation.ok && !starting;

  const focusSerial = () => {
    serialRef.current?.focus({ preventScroll: true });
  };

  const lockSerial = () => {
    serialLocked.current = true;
    setSerialLockedState(true);

    gaugeFocusedAt.current = Date.now();

    requestAnimationFrame(() => {
      gaugeRef.current?.focus({ preventScroll: true });
    });
  };

  const unlockSerial = () => {
    serialLocked.current = false;
    setSerialLockedState(false);
  };

  // Initial focus and focus management.
  useEffect(() => {
    focusSerial();

    const handleFocusOut = () => {
      requestAnimationFrame(() => {
        const activeElement = document.activeElement;

        if (activeElement === gaugeRef.current) return;
        if (activeElement === startButtonRef.current) return;
        if (activeElement === serialRef.current) return;

        // Do not steal focus while the serial is locked.
        if (serialLocked.current) {
          gaugeRef.current?.focus({ preventScroll: true });
          return;
        }

        focusSerial();
      });
    };

    document.addEventListener("focusout", handleFocusOut);

    return () => {
      document.removeEventListener("focusout", handleFocusOut);
    };
  }, []);

  // Keep Gauge ID cleared until a valid serial is entered.
  useEffect(() => {
    if (serialValid) {
      if (!serialLocked.current) {
        lockSerial();
      }
    } else if (!serialLocked.current && gaugeId) {
      onGaugeIdChange("");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serialValid]);

  // Accept only one valid serial.
  const handleSerialChange = (e) => {
    if (serialLocked.current) return;

    const value = e.target.value.toUpperCase();

    // Prevent extra characters from being appended to a serial.
    const nextValue = value.slice(0, 15);

    setSerial(nextValue);

    if (validateSerial(nextValue).ok) {
      lockSerial();
    }
  };

  const handleSerialKeyDown = (e) => {
    if (e.key !== "Enter") return;

    e.preventDefault();

    // Ignore trailing Enter or extra input after a serial is accepted.
    if (serialLocked.current) {
      gaugeRef.current?.focus({ preventScroll: true });
      return;
    }

    const value = serial.trim().toUpperCase();
    const validation = validateSerial(value);

    if (!validation.ok) {
      toast.error(validation.msg, { id: "serial-invalid" });
      return;
    }

    setSerial(value);
    lockSerial();
  };

  const handleGaugeKeyDown = (e) => {
    if (e.key === "Enter") {
      e.preventDefault();

      // Ignore the serial scanner's trailing Enter.
      if (Date.now() - gaugeFocusedAt.current < 250) {
        return;
      }

      if (!starting) {
        handleStart();
      }

      return;
    }

    // Allow shortcuts and editing/navigation keys.
    if (e.ctrlKey || e.metaKey || e.altKey || e.key.length > 1) {
      return;
    }

    // Allow digits only.
    if (!/^\d$/.test(e.key)) {
      e.preventDefault();
      return;
    }

    // Never allow more than two digits.
    if (e.currentTarget.value.length >= 2) {
      e.preventDefault();
    }
  };

  const handleGaugeChange = (e) => {
    const value = e.target.value;

    if (!/^\d{0,2}$/.test(value)) {
      return;
    }

    onGaugeIdChange(value);
  };

  const handleGaugePaste = (e) => {
    const text = (e.clipboardData.getData("text") || "").trim();

    if (!/^\d{1,2}$/.test(text)) {
      e.preventDefault();
      toast.error("Gauge ID must contain only 1 or 2 digits");
    }
  };

  const handleSerialBlur = async () => {
    const value = serial.trim().toUpperCase();

    if (!validateSerial(value).ok) return;

    const code = extractModelCode(value);
    setModelCode(code);

    try {
      const material = await getMaterialByCode(code);

      setModelName(material.exists ? material.name : "UNKNOWN MODEL");
    } catch {
      setModelName("UNKNOWN MODEL");
    }
  };

  const handleStart = async () => {
    if (starting) return;

    if (!line) {
      toast.error("No line selected — please log in again");
      return;
    }

    const serialNo = serial.trim().toUpperCase();
    const serialCheck = validateSerial(serialNo);

    if (!serialCheck.ok) {
      toast.error(serialCheck.msg);
      return;
    }

    const gaugeCheck = validateGauge(String(gaugeId ?? ""));

    if (!gaugeCheck.ok) {
      toast.error(gaugeCheck.msg);
      return;
    }

    const gid = Number(gaugeId);
    const code = extractModelCode(serialNo);

    setStarting(true);

    try {
      // Material lookup is informational.
      const material = await getMaterialByCode(code).catch(() => ({
        exists: false,
        name: null,
      }));

      setModelCode(code);
      setModelName(material.exists ? material.name : "UNKNOWN MODEL");

      const response = await startTestApi({
        serial_no: serialNo,
        gauge_id: gid,
        line,
        model_code: code,
      });

      if (response.status === "STARTED") {
        toast.success(`Test started on Gauge ${gid}`);

        setSerial("");
        onGaugeIdChange("");
        setModelCode("");
        setModelName("");

        // Unlock for the next serial scan.
        unlockSerial();

        onStarted?.();

        requestAnimationFrame(() => {
          focusSerial();
        });
      } else {
        toast.error(response.message || "Error starting test");
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
        <span className="font-semibold text-slate-600">{lineLabel || "—"}</span>
        {gaugeIds.length ? ` · ${gaugeIds.length} gauges` : ""}
      </p>

      <label className="block text-xs mb-1 text-slate-500">Serial Number</label>

      <input
        ref={serialRef}
        value={serial}
        onChange={handleSerialChange}
        onKeyDown={handleSerialKeyDown}
        onBlur={handleSerialBlur}
        readOnly={serialLockedState}
        placeholder="Scan or type serial"
        autoComplete="off"
        className="w-full mb-3 px-3 py-2 rounded border focus:border-emerald-600 outline-none text-sm read-only:bg-slate-100"
      />

      <label className="block text-xs mb-1 text-slate-500">
        Gauge ID{" "}
        {!serialValid && (
          <span className="text-slate-400">(enter a valid serial first)</span>
        )}
      </label>

      <input
        ref={gaugeRef}
        type="text"
        inputMode="numeric"
        autoComplete="off"
        disabled={!serialValid || starting}
        maxLength={2}
        value={gaugeValue}
        onKeyDown={handleGaugeKeyDown}
        onChange={handleGaugeChange}
        onPaste={handleGaugePaste}
        placeholder={!serialValid ? "Locked" : "Scan or enter gauge ID"}
        className={`w-full px-3 py-2 rounded border outline-none text-sm disabled:bg-slate-100 disabled:text-slate-400 disabled:cursor-not-allowed ${
          serialValid && gaugeTouched && !gaugeValidation.ok
            ? "border-red-400 focus:border-red-500"
            : "focus:border-emerald-600"
        }`}
      />

      <p
        className={`text-xs mt-1 mb-3 min-h-4 ${
          serialValid && gaugeTouched && !gaugeValidation.ok
            ? "text-red-500"
            : "text-transparent"
        }`}
      >
        {serialValid && gaugeTouched && !gaugeValidation.ok
          ? gaugeValidation.msg
          : "."}
      </p>

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
        ref={startButtonRef}
        type="button"
        onClick={handleStart}
        disabled={!canStart}
        className="w-full py-3 rounded bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 disabled:cursor-not-allowed text-white font-bold text-base transition"
      >
        {starting ? "Starting…" : "START TEST"}
      </button>

      <p className="text-xs text-slate-400 mt-2 text-center">
        Serial format: <code className="bg-slate-100 px-1 rounded">S4</code> +
        13 digits
        <br />
        Gauge ID: any 1 or 2 digit number
      </p>
    </section>
  );
}
