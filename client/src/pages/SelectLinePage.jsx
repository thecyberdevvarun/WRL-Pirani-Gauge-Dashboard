import { useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { Navigate, useNavigate } from "react-router-dom";
import { FiChevronRight, FiLogOut } from "react-icons/fi";
import toast from "react-hot-toast";
import { getMe, logout as logoutApi, selectLine } from "../api/client";
import { changeLine, login, logout } from "../store/authSlice";

// Shown to users who are authorised for more than one production line.
// The server re-checks the choice, so only lines the user may use work.
export default function SelectLinePage() {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const { isAuthenticated, username, role, line, lines } = useSelector((s) => s.auth);
  const [busy, setBusy] = useState(null);

  // Refresh the list from the server (e.g. after a page reload with an old saved session).
  useEffect(() => {
    if (!isAuthenticated) return;
    getMe()
      .then((me) =>
        dispatch(login({ username: me.username, role: me.role, line: me.line, lines: me.lines }))
      )
      .catch(() => {});
  }, [isAuthenticated, dispatch]);

  if (!isAuthenticated) return <Navigate to="/login" replace />;
  // One line only: nothing to choose.
  if (lines.length === 1 && line) return <Navigate to="/" replace />;

  const choose = async (key) => {
    setBusy(key);
    try {
      const me = await selectLine(key);
      dispatch(changeLine(me.line));
      navigate("/", { replace: true });
    } catch (err) {
      toast.error(err.message || "Could not select that line");
    } finally {
      setBusy(null);
    }
  };

  const handleLogout = () => {
    logoutApi().catch(() => {});
    dispatch(logout());
    navigate("/login", { replace: true });
  };

  return (
    <div className="min-h-screen bg-ink-950 flex items-center justify-center p-6">
      <div className="w-full max-w-lg bg-white rounded-2xl shadow-2xl p-8">
        <h1 className="text-xl font-bold font-display text-ink-900 text-center">
          Choose a production line
        </h1>
        <p className="text-center text-sm text-slate-400 mt-1 mb-6">
          Signed in as <b className="capitalize text-slate-600">{username}</b> ({role})
        </p>

        <ul className="space-y-3">
          {lines.map((l) => (
            <li key={l.key}>
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => choose(l.key)}
                className={`w-full flex items-center justify-between px-5 py-4 rounded-xl border-2 text-left transition
                  ${l.key === line ? "border-emerald-600 bg-emerald-50" : "border-slate-200 hover:border-emerald-500"}
                  disabled:opacity-60`}
              >
                <span>
                  <span className="block font-semibold text-slate-800">{l.label}</span>
                  <span className="block text-xs text-slate-400">
                    {l.gauge_count} gauges{l.key === line ? " · current line" : ""}
                  </span>
                </span>
                <FiChevronRight className="text-slate-400" />
              </button>
            </li>
          ))}
        </ul>

        <button
          type="button"
          onClick={handleLogout}
          className="mt-6 mx-auto flex items-center gap-1.5 text-sm text-slate-400 hover:text-rose-500"
        >
          <FiLogOut /> Logout
        </button>
      </div>
    </div>
  );
}
