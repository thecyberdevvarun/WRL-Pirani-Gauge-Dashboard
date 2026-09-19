import { useEffect } from "react";
import { useDispatch, useSelector } from "react-redux";
import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import RequireAuth from "./components/RequireAuth";
import LoginPage from "./pages/LoginPage";
import FixturesPage from "./pages/FixturesPage";
import ReportsPage from "./pages/ReportsPage";
import SettingsPage from "./pages/SettingsPage";
import { fetchLines, selectLinesStatus } from "./store/linesSlice";

export default function App() {
  const dispatch = useDispatch();
  const linesStatus = useSelector(selectLinesStatus);

  // Fetch once, from here rather than LoginPage — a returning user with a
  // persisted session never mounts LoginPage, so this is the one place
  // guaranteed to mount regardless of auth state.
  useEffect(() => {
    if (linesStatus === "idle") dispatch(fetchLines());
  }, [linesStatus, dispatch]);

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route element={<RequireAuth />}>
        <Route element={<Layout />}>
          <Route path="/" element={<FixturesPage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
