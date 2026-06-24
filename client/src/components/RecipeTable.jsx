import { FiEdit2, FiCopy, FiTrash2 } from "react-icons/fi";

export default function RecipeTable({ recipes, onEdit, onClone, onDelete }) {
  return (
    <div className="bg-white rounded-xl shadow overflow-x-auto scroll-thin">
      <table className="min-w-full text-sm text-center border-collapse" aria-label="Recipe Master Table">
        <thead className="bg-slate-100 text-xs text-slate-500 uppercase">
          <tr>
            <th className="px-3 py-2 text-left border">Model Code</th>
            <th className="px-3 py-2 text-left border">Model Name</th>
            <th className="px-3 py-2 border">LL (mbar)</th>
            <th className="px-3 py-2 border">UL (mbar)</th>
            <th className="px-3 py-2 border">Duration (min)</th>
            <th className="px-3 py-2 border">Poll (sec)</th>
            <th className="px-3 py-2 border">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {recipes.length === 0 && (
            <tr>
              <td colSpan={7} className="py-8 text-center text-slate-400">
                No recipes found
              </td>
            </tr>
          )}
          {recipes.map((r) => (
            <tr key={r.model_code} className="hover:bg-slate-50">
              <td className="border px-3 py-2 text-left font-mono font-semibold">{r.model_code}</td>
              <td className="border px-3 py-2 text-left">{r.model_name || "—"}</td>
              <td className="border px-3 py-2 tabular">{Number(r.lower_limit).toFixed(3)}</td>
              <td className="border px-3 py-2 tabular">{Number(r.upper_limit).toFixed(3)}</td>
              <td className="border px-3 py-2 tabular">{r.test_duration_min}</td>
              <td className="border px-3 py-2 tabular">{r.poll_interval_sec}</td>
              <td className="border px-3 py-2 whitespace-nowrap">
                <div className="flex gap-1 justify-center">
                  <button
                    type="button"
                    onClick={() => onEdit(r.model_code)}
                    className="flex items-center gap-1 px-2 py-1 bg-sky-600 hover:bg-sky-700 text-white rounded text-xs"
                  >
                    <FiEdit2 className="text-[11px]" /> Edit
                  </button>
                  <button
                    type="button"
                    onClick={() => onClone(r.model_code)}
                    className="flex items-center gap-1 px-2 py-1 bg-indigo-600 hover:bg-indigo-700 text-white rounded text-xs"
                  >
                    <FiCopy className="text-[11px]" /> Clone
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(r.model_code)}
                    className="flex items-center gap-1 px-2 py-1 bg-rose-600 hover:bg-rose-700 text-white rounded text-xs"
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
