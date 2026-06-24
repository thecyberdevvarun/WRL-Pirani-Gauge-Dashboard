import { NavLink, Outlet } from "react-router-dom";
import { useEffect, useState } from "react";
import { FiActivity, FiList, FiBarChart2, FiWifi, FiWifiOff } from "react-icons/fi";
import { getHealth } from "../api/client";

const NAV_ITEMS = [
  { to: "/", label: "Live Floor", icon: FiActivity },
  { to: "/recipes", label: "Recipes", icon: FiList },
  { to: "/reports", label: "Reports", icon: FiBarChart2 },
];

export default function Layout() {
  const [online, setOnline] = useState(true);

  useEffect(() => {
    let mounted = true;
    const ping = () =>
      getHealth()
        .then(() => mounted && setOnline(true))
        .catch(() => mounted && setOnline(false));
    ping();
    const t = setInterval(ping, 15000);
    return () => {
      mounted = false;
      clearInterval(t);
    };
  }, []);

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-ink-900 text-slate-200 sticky top-0 z-40 shadow-lg shadow-black/20">
        <div className="px-5 h-14 flex items-center gap-8 max-w-[1900px] mx-auto w-full">
          <div className="flex items-center gap-2.5">
            <span className="w-2.5 h-2.5 rounded-full bg-signal-pass shadow-[0_0_10px_2px_rgba(34,197,94,0.7)]" />
            <span className="font-display font-bold tracking-wide text-[15px] text-white">
              PIRANI<span className="text-signal-pass"> GAUGE DASHBOARD</span>
            </span>
          </div>

          <nav className="flex items-center gap-1 text-sm">
            {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === "/"}
                className={({ isActive }) =>
                  `flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium transition-colors ${
                    isActive
                      ? "bg-white/10 text-white"
                      : "text-slate-400 hover:text-slate-100 hover:bg-white/5"
                  }`
                }
              >
                <Icon className="text-[15px]" />
                {label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2 text-xs font-medium">
            {online ? (
              <span className="flex items-center gap-1.5 text-signal-pass">
                <FiWifi /> SYSTEM ONLINE
              </span>
            ) : (
              <span className="flex items-center gap-1.5 text-signal-fail">
                <FiWifiOff /> SYSTEM OFFLINE
              </span>
            )}
          </div>
        </div>
      </header>

      <main className="flex-1 bg-[#eef1f6]">
        <Outlet />
      </main>
    </div>
  );
}
