import { useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { Navigate, useNavigate } from "react-router-dom";
import { FiUser, FiLock, FiLogIn } from "react-icons/fi";
import toast from "react-hot-toast";
import { login as loginApi } from "../api/client";
import { login } from "../store/authSlice";

// Each production line has its own username/password, defined in the server's
// .env. The backend checks them and tells us which line they belong to — the
// browser never sees any other line's credentials.
export default function LoginPage() {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const isAuthenticated = useSelector((s) => s.auth.isAuthenticated);

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  if (isAuthenticated) return <Navigate to="/" replace />; // RequireAuth sends us on to /select-line if needed

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError("Enter your username and password");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const me = await loginApi(username.trim(), password);
      dispatch(login({ username: me.username, role: me.role, line: me.line, lines: me.lines }));
      if (me.needs_line_selection) {
        // Authorised for several lines: choose which one to work on.
        navigate("/select-line", { replace: true });
      } else {
        toast.success(`Welcome — ${me.line_label} line`);
        navigate("/", { replace: true });
      }
    } catch (err) {
      setError(err.message || "Could not sign in — check the server connection");
      setPassword("");
    } finally {
      setSubmitting(false);
    }
  };

  const inputClass =
    "w-full pl-10 pr-3 py-3 rounded-xl border-2 border-slate-200 focus:border-emerald-600 outline-none text-base";

  return (
    <div className="min-h-screen bg-ink-950 flex items-center justify-center p-6">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md bg-white rounded-2xl shadow-2xl p-8"
      >
        <div className="flex items-center gap-2.5 justify-center mb-1">
          <img src="/western-logo.jpg" alt="Western Refrigeration" className="h-12 w-auto rounded-sm" />
          <span className="w-2.5 h-2.5 rounded-full bg-signal-pass shadow-[0_0_10px_2px_rgba(34,197,94,0.7)]" />
          <span className="font-display font-bold tracking-wide text-lg text-ink-900">
            PIRANI<span className="text-signal-pass"> GAUGE DASHBOARD</span>
          </span>
        </div>
        <p className="text-center text-sm text-slate-400 mb-8">
          Sign in with your production line login
        </p>

        <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
          Username
        </label>
        <div className="relative mb-4">
          <FiUser className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
            autoComplete="username"
            autoCapitalize="none"
            className={inputClass}
          />
        </div>

        <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
          Password
        </label>
        <div className="relative mb-4">
          <FiLock className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            className={inputClass}
          />
        </div>

        {error && (
          <p role="alert" className="text-sm text-rose-600 mb-4">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white font-bold text-base transition"
        >
          <FiLogIn /> {submitting ? "Signing in…" : "Login"}
        </button>
      </form>
    </div>
  );
}
