import { useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { useNavigate } from "react-router-dom";
import { FiUser, FiShield, FiCheckCircle, FiLogIn, FiActivity } from "react-icons/fi";
import toast from "react-hot-toast";
import { CREDENTIALS } from "../config/credentials";
import { LINES } from "../config/lines";
import { login } from "../store/authSlice";

export default function LoginPage() {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const isAuthenticated = useSelector((s) => s.auth.isAuthenticated);

  const [selectedCred, setSelectedCred] = useState(null);
  const [selectedLine, setSelectedLine] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  if (isAuthenticated) {
    navigate("/", { replace: true });
    return null;
  }

  const handleLogin = () => {
    if (!selectedCred) return toast.error("Select who you are logging in as");
    if (!selectedLine) return toast.error("Select a conveyor line");

    setSubmitting(true);
    dispatch(
      login({
        username: selectedCred.username,
        role: selectedCred.role,
        line: selectedLine.key,
      })
    );
    toast.success(`Welcome, ${selectedCred.username} — ${selectedLine.label} line`);
    navigate("/", { replace: true });
  };

  return (
    <div className="min-h-screen bg-ink-950 flex items-center justify-center p-6">
      <div className="w-full max-w-2xl bg-white rounded-2xl shadow-2xl p-8">
        <div className="flex items-center gap-2.5 justify-center mb-1">
          <span className="w-2.5 h-2.5 rounded-full bg-signal-pass shadow-[0_0_10px_2px_rgba(34,197,94,0.7)]" />
          <span className="font-display font-bold tracking-wide text-lg text-ink-900">
            PIRANI<span className="text-signal-pass"> GAUGE DASHBOARD</span>
          </span>
        </div>
        <p className="text-center text-sm text-slate-400 mb-8">Sign in to continue</p>

        {/* Step 1: who's logging in */}
        <div className="mb-7">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-1.5">
            <FiUser /> 1. Select your login
          </h3>
          <div className="grid grid-cols-2 gap-3">
            {CREDENTIALS.map((c) => {
              const active = selectedCred?.username === c.username;
              return (
                <button
                  key={c.username}
                  type="button"
                  onClick={() => setSelectedCred(c)}
                  className={`relative text-left p-4 rounded-xl border-2 transition ${
                    active
                      ? "border-emerald-600 bg-emerald-50"
                      : "border-slate-200 hover:border-emerald-300 hover:bg-slate-50"
                  }`}
                >
                  {active && <FiCheckCircle className="absolute top-3 right-3 text-emerald-600" />}
                  <div className="flex items-center gap-2 font-semibold text-slate-800 capitalize">
                    <FiShield className="text-slate-400" />
                    {c.username}
                  </div>
                  <div className="text-xs text-slate-400 mt-1">{c.role}</div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Step 2: which line */}
        <div className="mb-8">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-1.5">
            <FiActivity /> 2. Select conveyor line
          </h3>
          <div className="grid grid-cols-3 gap-3">
            {LINES.map((l) => {
              const active = selectedLine?.key === l.key;
              return (
                <button
                  key={l.key}
                  type="button"
                  onClick={() => setSelectedLine(l)}
                  className={`relative text-center p-4 rounded-xl border-2 transition ${
                    active
                      ? "border-emerald-600 bg-emerald-50"
                      : "border-slate-200 hover:border-emerald-300 hover:bg-slate-50"
                  }`}
                >
                  {active && <FiCheckCircle className="absolute top-2 right-2 text-emerald-600" />}
                  <div className="font-semibold text-slate-800">{l.label}</div>
                  <div className="text-xs text-slate-400 mt-1 tabular">{l.gaugeCount} gauges</div>
                </button>
              );
            })}
          </div>
        </div>

        <button
          type="button"
          onClick={handleLogin}
          disabled={submitting}
          className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white font-bold text-base transition"
        >
          <FiLogIn /> Login
        </button>
      </div>
    </div>
  );
}
