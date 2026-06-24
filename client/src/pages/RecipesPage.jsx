import { useEffect, useMemo, useState } from "react";
import { FiPlus, FiSearch } from "react-icons/fi";
import RecipeTable from "../components/RecipeTable";
import RecipeModal from "../components/RecipeModal";
import { listRecipes, saveRecipe, deleteRecipe as deleteRecipeApi } from "../api/client";
import { toast } from "react-hot-toast";

export default function RecipesPage() {
  // using react-hot-toast
  const [recipes, setRecipes] = useState([]);
  const [query, setQuery] = useState("");
  const [modal, setModal] = useState({ open: false, mode: "add", initial: null });

  const loadRecipes = () =>
    listRecipes()
      .then(setRecipes)
      .catch(() => toast.error("Failed to load recipes"));

  useEffect(() => {
    loadRecipes();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const filtered = useMemo(() => {
    const q = query.toLowerCase();
    return recipes.filter(
      (r) => r.model_code.toLowerCase().includes(q) || (r.model_name || "").toLowerCase().includes(q)
    );
  }, [recipes, query]);

  const openAdd = () => setModal({ open: true, mode: "add", initial: null });

  const openEdit = (modelCode) => {
    const r = recipes.find((x) => x.model_code === modelCode);
    if (!r) return;
    setModal({
      open: true,
      mode: "edit",
      initial: {
        model: r.model_code,
        model_name: r.model_name,
        ll: r.lower_limit,
        ul: r.upper_limit,
        duration: r.test_duration_min,
        poll: r.poll_interval_sec,
      },
    });
  };

  const openClone = (modelCode) => {
    const r = recipes.find((x) => x.model_code === modelCode);
    if (!r) return;
    setModal({
      open: true,
      mode: "clone",
      initial: {
        model: "",
        model_name: r.model_name,
        ll: r.lower_limit,
        ul: r.upper_limit,
        duration: r.test_duration_min,
        poll: r.poll_interval_sec,
      },
    });
  };

  const handleSave = async (payload) => {
    try {
      await saveRecipe(payload);
      setModal({ open: false, mode: "add", initial: null });
      loadRecipes();
      toast.success(modal.mode === "edit" ? "Recipe updated" : "Recipe saved");
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleDelete = async (modelCode) => {
    if (!confirm(`Delete recipe "${modelCode}"? This cannot be undone.`)) return;
    try {
      await deleteRecipeApi(modelCode);
      loadRecipes();
      toast.success("Recipe deleted");
    } catch {
      toast.error("Delete failed");
    }
  };

  return (
    <main className="p-6 max-w-[1900px] mx-auto">
      <div className="flex justify-between items-center mb-4">
        <div>
          <h2 className="text-2xl font-semibold font-display">Recipe Master</h2>
          <p className="text-sm text-slate-400 mt-0.5">{recipes.length} recipes configured</p>
        </div>
        <button
          type="button"
          onClick={openAdd}
          className="flex items-center gap-1.5 px-4 py-2 rounded bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-sm"
        >
          <FiPlus /> Add Recipe
        </button>
      </div>

      <div className="mb-3 relative w-80">
        <FiSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by model code or model name…"
          aria-label="Search recipes"
          className="w-full pl-9 pr-3 py-2 border rounded focus:border-emerald-600 outline-none text-sm"
        />
      </div>

      <RecipeTable recipes={filtered} onEdit={openEdit} onClone={openClone} onDelete={handleDelete} />

      <RecipeModal
        open={modal.open}
        mode={modal.mode}
        initial={modal.initial}
        onClose={() => setModal({ open: false, mode: "add", initial: null })}
        onSave={handleSave}
      />
    </main>
  );
}
