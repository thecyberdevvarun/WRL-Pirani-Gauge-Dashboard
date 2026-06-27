import { FiEdit2, FiCopy, FiTrash2 } from "react-icons/fi";

export default function RecipeTable({ recipes, onEdit, onClone, onDelete }) {
  return (
    <div className="bg-white rounded-xl shadow overflow-x-auto scroll-thin">
      <table
        className="min-w-full text-sm text-center"
        aria-label="Recipe Master Table"
      >
        <thead className="bg-ink-900 text-[11px] text-slate-300 uppercase tracking-wide">
          <tr>
            <th className="px-3 py-2.5 text-left">Model Code</th>
            <th className="px-3 py-2.5 text-left">Model Name</th>
            <th className="px-3 py-2.5">LL (mbar)</th>
            <th className="px-3 py-2.5">UL (mbar)</th>
            <th className="px-3 py-2.5">Duration (min)</th>
            <th className="px-3 py-2.5">Poll (sec)</th>
            <th className="px-3 py-2.5">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {recipes.length === 0 && (
            <tr>
              <td colSpan={7} className="py-8 text-center text-slate-400">
                No recipes found
              </td>
            </tr>
          )}
          {recipes.map((r, idx) => (
            <tr
              key={r.model_code}
              className={`${idx % 2 === 0 ? "bg-white" : "bg-slate-50/60"} hover:bg-emerald-50/50 transition-colors`}
            >
              <td className="px-3 py-2 text-left font-mono font-semibold text-ink-900">
                {r.model_code}
              </td>
              <td className="px-3 py-2 text-left text-slate-600">
                {r.model_name || "—"}
              </td>
              <td className="px-3 py-2 tabular text-slate-700">
                {Number(r.lower_limit).toFixed(3)}
              </td>
              <td className="px-3 py-2 tabular text-slate-700">
                {Number(r.upper_limit).toFixed(3)}
              </td>
              <td className="px-3 py-2 tabular text-slate-500">
                {r.test_duration_min}
              </td>
              <td className="px-3 py-2 tabular text-slate-500">
                {r.poll_interval_sec}
              </td>
              <td className="px-3 py-2 whitespace-nowrap">
                <div className="flex gap-1.5 justify-center">
                  <button
                    type="button"
                    onClick={() => onEdit(r.model_code)}
                    title="Edit recipe"
                    className="flex items-center gap-1 px-2.5 py-1 bg-ink-900 hover:bg-ink-800 text-white rounded-md text-xs font-medium transition-colors"
                  >
                    <FiEdit2 className="text-[11px]" /> Edit
                  </button>
                  <button
                    type="button"
                    onClick={() => onClone(r.model_code)}
                    title="Clone recipe"
                    className="flex items-center gap-1 px-2.5 py-1 bg-white hover:bg-slate-100 text-slate-600 border border-slate-300 rounded-md text-xs font-medium transition-colors"
                  >
                    <FiCopy className="text-[11px]" /> Clone
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(r.model_code)}
                    title="Delete recipe"
                    className="flex items-center gap-1 px-2.5 py-1 bg-signal-fail/10 hover:bg-signal-fail text-signal-fail hover:text-white ring-1 ring-inset ring-signal-fail/30 rounded-md text-xs font-medium transition-colors"
                  >
                    <FiTrash2 className="text-[11px]" /> Delete
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
