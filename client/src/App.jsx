import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import FixturesPage from "./pages/FixturesPage";
import RecipesPage from "./pages/RecipesPage";
import ReportsPage from "./pages/ReportsPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<FixturesPage />} />
        <Route path="/recipes" element={<RecipesPage />} />
        <Route path="/reports" element={<ReportsPage />} />
      </Route>
    </Routes>
  );
}
