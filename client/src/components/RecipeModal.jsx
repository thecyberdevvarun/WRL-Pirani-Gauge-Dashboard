import { useEffect, useState } from "react";

const EMPTY = { model: "", model_name: "", ll: "", ul: "", duration: "", poll: "" };

export default function RecipeModal({ open, mode, initial, onClose, onSave }) {
  const [form, setForm] = useState(EMPTY);
  const [llUlError, setLlUlError] = useState(false);
  const [validationMsg, setValidationMsg] = useState("");

  useEffect(() => {
    if (open) {
      setForm(initial || EMPTY);
      setLlUlError(false);
      setValidationMsg("");
    }
  }, [open, initial]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const handleSave = () => {
    setValidationMsg("");
    setLlUlError(false);

    const model = form.model.trim();
    const modelName = form.model_name.trim();
    const ll = parseFloat(form.ll);
    const ul = parseFloat(form.ul);
    const duration = parseInt(form.duration, 10);
    const poll = parseInt(form.poll, 10);

    if (!model) return setValidationMsg("Model code is required");
    if (!modelName) return setValidationMsg("Model name is required");
    if (Number.isNaN(ll) || ll < 0) return setValidationMsg("Enter a valid lower limit (≥ 0)");
    if (Number.isNaN(ul) || ul < 0) return setValidationMsg("Enter a valid upper limit (≥ 0)");
    if (ll >= ul) return setLlUlError(true);
    if (Number.isNaN(duration) || duration < 1 || duration > 480)
      return setValidationMsg("Duration must be between 1 and 480 minutes");
    if (Number.isNaN(poll) || poll < 60) return setValidationMsg("Poll interval must be ≥ 60 seconds");

    onSave({ model, model_name: modelName, ll, ul, duration, poll });
  };

  const titles = { add: "Add Recipe", edit: "Edit Recipe", clone: "Clone Recipe" };

  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
      role="dialog"
      aria-modal="true"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-white rounded-xl shadow-xl p-6 w-[440px]">
        <h3 className="text-lg font-semibold mb-4 text-emerald-700 font-display">{titles[mode]}</h3>

        <div className="space-y-3 text-sm">
          <div>
            <label className="block mb-1 font-medium">
              Model Code <span className="text-rose-500">*</span>
            </label>
            <input
              value={form.model}
              onChange={set("model")}
              disabled={mode === "edit"}
              placeholder="e.g. 1234"
              className="w-full px-3 py-2 border rounded focus:border-emerald-600 outline-none bg-slate-50 disabled:opacity-60"
            />
          </div>

          <div>
            <label className="block mb-1 font-medium">
              Model Name <span className="text-rose-500">*</span>
            </label>
            <input
              value={form.model_name}
              onChange={set("model_name")}
              placeholder="e.g. Deep Freezer 250L"
              className="w-full px-3 py-2 border rounded focus:border-emerald-600 outline-none"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block mb-1 font-medium">
                Lower Limit (mbar) <span className="text-rose-500">*</span>
              </label>
              <input
                type="number"
                step="0.001"
                min="0"
                value={form.ll}
                onChange={set("ll")}
                placeholder="e.g. 0.200"
                className="w-full px-3 py-2 border rounded focus:border-emerald-600 outline-none"
              />
            </div>
            <div>
              <label className="block mb-1 font-medium">
                Upper Limit (mbar) <span className="text-rose-500">*</span>
              </label>
              <input
                type="number"
                step="0.001"
                min="0"
                value={form.ul}
                onChange={set("ul")}
                placeholder="e.g. 0.600"
                className="w-full px-3 py-2 border rounded focus:border-emerald-600 outline-none"
              />
            </div>
          </div>
          {llUlError && <p className="text-xs text-rose-500">LL must be less than UL</p>}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block mb-1 font-medium">
                Duration (min) <span className="text-slate-400 font-normal">1–480</span>
              </label>
              <input
                type="number"
                min="1"
                max="480"
                value={form.duration}
                onChange={set("duration")}
                placeholder="e.g. 30"
                className="w-full px-3 py-2 border rounded focus:border-emerald-600 outline-none"
              />
            </div>
            <div>
              <label className="block mb-1 font-medium">
                Poll Interval (sec) <span className="text-slate-400 font-normal">≥ 60</span>
              </label>
              <input
                type="number"
                min="60"
                value={form.poll}
                onChange={set("poll")}
                placeholder="e.g. 60"
                className="w-full px-3 py-2 border rounded focus:border-emerald-600 outline-none"
              />
            </div>
          </div>
        </div>

        {validationMsg && <p className="mt-2 text-xs text-rose-500 font-medium">{validationMsg}</p>}

        <div className="flex justify-end gap-3 mt-5">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded bg-slate-200 hover:bg-slate-300 text-sm"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            className="px-4 py-2 rounded bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-sm"
          >
            Save Recipe
          </button>
        </div>
      </div>
    </div>
  );
}
