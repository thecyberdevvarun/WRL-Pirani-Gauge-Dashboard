import { useSelector } from "react-redux";
import { Navigate, Outlet, useLocation } from "react-router-dom";

export default function RequireAuth() {
  const isAuthenticated = useSelector((s) => s.auth.isAuthenticated);
  const line = useSelector((s) => s.auth.line);
  const location = useLocation();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  // Logged in but no production line chosen yet (users with several lines).
  if (!line) {
    return <Navigate to="/select-line" replace />;
  }
  return <Outlet />;
}
