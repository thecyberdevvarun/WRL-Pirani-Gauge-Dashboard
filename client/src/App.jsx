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
import { logout, clearLine } from "./store/authSlice";
import { UNAUTHORIZED_EVENT, SELECT_LINE_EVENT } from "./api/client";
import SelectLinePage from "./pages/SelectLinePage";

export default function App() {
  const dispatch = useDispatch();
  const linesStatus = useSelector(selectLinesStatus);
  const isAuthenticated = useSelector((s) => s.auth.isAuthenticated);
  const activeLine = useSelector((s) => s.auth.line);

  // Load the logged-in line's config (gauges, gateways, limits). The server
  // only returns the line you are logged into. Runs after login, and also for
  // a returning user whose session was restored from the browser.
  useEffect(() => {
    if (isAuthenticated && activeLine && linesStatus === "idle") dispatch(fetchLines());
  }, [isAuthenticated, activeLine, linesStatus, dispatch]);

  // Any 401 from the API means the server session is gone: back to login.
  useEffect(() => {
    const onUnauthorized = () => dispatch(logout());
    const onNoLine = () => dispatch(clearLine());
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    window.addEventListener(SELECT_LINE_EVENT, onNoLine);
    return () => {
      window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
      window.removeEventListener(SELECT_LINE_EVENT, onNoLine);
    };
  }, [dispatch]);

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/select-line" element={<SelectLinePage />} />

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
