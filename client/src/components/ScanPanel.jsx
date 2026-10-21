import { useEffect, useRef, useState } from "react";
import { useSelector } from "react-redux";
import { FiPlay } from "react-icons/fi";
import { getMaterialByCode, startTest as startTestApi } from "../api/client";
import { toast } from "react-hot-toast";

function extractModelCode(serial) {
  return serial.substring(2, 6);
}

function validateSerial(serial) {
  if (serial.length !== 15) {
    return {
      ok: false,
      msg: "Serial must be exactly 15 characters",
    };
  }

  if (!serial.startsWith("S4")) {
    return {
      ok: false,
      msg: "Serial must start with S4",
    };
  }

  if (!/^S4\d{13}$/.test(serial)) {
    return {
      ok: false,
      msg: "Invalid serial format (S4 + 13 digits)",
    };
  }

  return { ok: true };
}

// Same idea as validateSerial, but for the Gauge ID field:
// only a 1/2 digit gauge number (like 1 or 18) that exists on this line.
function validateGauge(value, gaugeIds, maxDigits) {
  if (!value) {
    return { ok: false, msg: "Gauge ID required" };
  }

  if (!/^\d+$/.test(value)) {
    return { ok: false, msg: "Gauge ID must contain digits only" };
  }

  if (value.length > maxDigits) {
    return {
      ok: false,
      msg: `Gauge ID can be at most ${maxDigits} digit${maxDigits > 1 ? "s" : ""}`,
    };
  }

  if (value.startsWith("0")) {
    return { ok: false, msg: "Gauge ID cannot start with 0" };
  }

  if (!gaugeIds.includes(parseInt(value, 10))) {
    return { ok: false, msg: `Gauge ${value} is not available on this line` };
  }

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
  const startButtonRef = useRef(null);

  // Gauge field is locked until a complete, valid serial is entered.
  const serialValid = validateSerial(serial.trim()).ok;

  // Digits allowed = digits in the highest gauge id of this line (54 -> 2).
  const maxGaugeDigits = gaugeIds?.length
    ? String(Math.max(...gaugeIds)).length
    : 2;

  const gaugeValidation = validateGauge(
    String(gaugeId ?? ""),
    gaugeIds || [],
    maxGaugeDigits,
  );
  const gaugeTouched = String(gaugeId ?? "") !== "";
  const canStart = serialValid && gaugeValidation.ok;

  // Timing refs used to ignore the scanner's trailing Enter / detect scans.
  const lastGaugeKeyTime = useRef(0);
  const lastScanBlockedAt = useRef(0);
  const gaugeFocusedAt = useRef(0);

  const rejectGaugeInput = () => {
    lastScanBlockedAt.current = Date.now();
    onGaugeIdChange("");
    toast.error(
      "Gauge ID accepts only the gauge number (e.g. 1 or 18). Scan the serial in the Serial Number field.",
      { id: "gauge-scan-blocked" },
    );
  };

  // Focus Serial Number on page load and restore focus when
  // the user clicks outside the scanning controls.
  useEffect(() => {
    const focusSerial = () => {
      serialRef.current?.focus({ preventScroll: true });
    };

    focusSerial();

    const handleFocusOut = () => {
      requestAnimationFrame(() => {
        const activeElement = document.activeElement;

        // Keep focus while entering Gauge ID.
        if (activeElement === gaugeRef.current) return;

        // Allow interaction with the Start Test button.
        if (activeElement === startButtonRef.current) return;

        // Do not disturb the serial field if it already has focus.
        if (activeElement === serialRef.current) return;

        focusSerial();
      });
    };

    document.addEventListener("focusout", handleFocusOut);

    return () => {
      document.removeEventListener("focusout", handleFocusOut);
    };
  }, []);

  // As soon as the serial becomes valid the Gauge field unlocks and gets focus.
  // (Done in an effect so the input is already enabled when we focus it.)
  useEffect(() => {
    if (serialValid) {
      gaugeFocusedAt.current = Date.now();
      lastGaugeKeyTime.current = 0;
      gaugeRef.current?.focus({ preventScroll: true });
    } else if (gaugeId) {
      // Serial was edited/cleared -> the gauge entry is no longer trustworthy.
      onGaugeIdChange("");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serialValid]);

  const handleSerialChange = (e) => {
    setSerial(e.target.value);
  };

  const handleSerialKeyDown = (e) => {
    if (e.key !== "Enter") return;

    e.preventDefault();

    const validation = validateSerial(serial.trim());

    if (!validation.ok) {
      toast.error(validation.msg, { id: "serial-invalid" });
      return;
    }

    // Valid serial: Enter moves to Gauge ID.
    gaugeFocusedAt.current = Date.now();
    gaugeRef.current?.focus({ preventScroll: true });
  };

  const handleGaugeKeyDown = (e) => {
    // Enter => start the test
    if (e.key === "Enter") {
      e.preventDefault();

      // Ignore the scanner's trailing Enter (arrives right after focus jumps
      // here from the serial field, or right after a blocked scan).
      const now = Date.now();
      if (
        now - gaugeFocusedAt.current < 150 ||
        now - lastScanBlockedAt.current < 500
      ) {
        return;
      }

      if (!starting) handleStart();
      return;
    }

    // Let navigation / editing keys and shortcuts through (Backspace, arrows, Ctrl+A ...)
    if (e.ctrlKey || e.metaKey || e.altKey || e.key.length > 1) {
      lastGaugeKeyTime.current = 0;
      return;
    }

    const now = Date.now();
    const gap = now - lastGaugeKeyTime.current;
    lastGaugeKeyTime.current = now;

    // Any non-digit (a scanned serial starts with "S4...") is blocked.
    if (!/^\d$/.test(e.key)) {
      e.preventDefault();
      rejectGaugeInput();
      return;
    }

    // Keys arriving < 35 ms apart = barcode scanner, not a human typing.
    if (gap > 0 && gap < 35) {
      e.preventDefault();
      rejectGaugeInput();
    }
  };

  const handleGaugeChange = (e) => {
    const digits = e.target.value.replace(/\D/g, "");

    // Too many digits => it was a scan/paste, clear it.
    if (digits.length > maxGaugeDigits) {
      rejectGaugeInput();
      return;
    }

    onGaugeIdChange(digits);
  };

  const handleGaugePaste = (e) => {
    const text = (e.clipboardData.getData("text") || "").trim();
    const pattern = new RegExp(`^\\d{1,${maxGaugeDigits}}$`);

    if (!pattern.test(text)) {
      e.preventDefault();
      rejectGaugeInput();
    }
  };

  const handleSerialBlur = async () => {
    const value = serial.trim();
    const validation = validateSerial(value);

    if (!validation.ok) return;

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
    if (!line) {
      return toast.error("No line selected — please log in again");
    }

    const serialNo = serial.trim();

    if (!serialNo) {
      return toast.error("Serial number required");
    }

    const validation = validateSerial(serialNo);

    if (!validation.ok) {
      return toast.error(validation.msg);
    }

    const gaugeCheck = validateGauge(
      String(gaugeId ?? ""),
      gaugeIds || [],
      maxGaugeDigits,
    );

    if (!gaugeCheck.ok) {
      return toast.error(gaugeCheck.msg);
    }

    const gid = parseInt(gaugeId, 10);
    const code = extractModelCode(serialNo);

    setStarting(true);

    try {
      // Material lookup is informational and does not block the test.
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

        onStarted?.();

        // Ready for the next serial scan.
        requestAnimationFrame(() => {
          serialRef.current?.focus({ preventScroll: true });
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
        placeholder="Scan or type serial"
        autoComplete="off"
        className="w-full mb-3 px-3 py-2 rounded border focus:border-emerald-600 outline-none text-sm"
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
        disabled={!serialValid}
        maxLength={maxGaugeDigits}
        value={gaugeId}
        onFocus={() => {
          lastGaugeKeyTime.current = 0;
        }}
        onKeyDown={handleGaugeKeyDown}
        onChange={handleGaugeChange}
        onPaste={handleGaugePaste}
        placeholder={
          !serialValid
            ? "Locked"
            : gaugeIds.length
              ? `e.g. ${gaugeIds[0]}`
              : "—"
        }
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
        disabled={starting || !canStart}
        className="w-full py-3 rounded bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 disabled:cursor-not-allowed text-white font-bold text-base transition"
      >
        {starting ? "Starting…" : "START TEST"}
      </button>

      <p className="text-xs text-slate-400 mt-2 text-center">
        Serial format: <code className="bg-slate-100 px-1 rounded">S4</code> +
        13 digits
      </p>
    </section>
  );
}
