import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import RequireAuth from "./components/RequireAuth";
import LoginPage from "./pages/LoginPage";
import FixturesPage from "./pages/FixturesPage";
import RecipesPage from "./pages/RecipesPage";
import ReportsPage from "./pages/ReportsPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route element={<RequireAuth />}>
        <Route element={<Layout />}>
          <Route path="/" element={<FixturesPage />} />
          <Route path="/recipes" element={<RecipesPage />} />
          <Route path="/reports" element={<ReportsPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
