import { FiMaximize, FiBarChart2 } from "react-icons/fi";
import { Link } from "react-router-dom";

const DOT = "w-3 h-3 rounded-full inline-block";

export default function StatusCountersBar({ counts }) {
  const toggleFullscreen = () => {
    if (!document.fullscreenElement)
      document.documentElement.requestFullscreen();
    else document.exitFullscreen();
  };

  return (
    <div className="flex justify-between items-center px-4 py-2.5 bg-white border-b shadow-sm">
      <div className="flex gap-6 text-sm">
        <div className="flex items-center gap-2">
          <span className={`${DOT} bg-signal-pass`} />
          <span className="tabular">PASS: {counts.pass}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className={`${DOT} bg-signal-fail`} />
          <span className="tabular">FAIL: {counts.fail}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className={`${DOT} bg-signal-run`} />
          <span className="tabular">RUNNING: {counts.run}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className={`${DOT} bg-signal-idle`} />
          <span className="tabular">IDLE: {counts.idle}</span>
        </div>
      </div>
      <div className="flex items-center gap-2 text-xs">
        <button
          type="button"
          onClick={toggleFullscreen}
          className="flex items-center gap-1.5 border px-3 py-1.5 rounded hover:bg-slate-50 text-slate-600"
        >
          <FiMaximize /> Fullscreen
        </button>
        <Link
          to="/reports"
          className="flex items-center gap-1.5 border px-3 py-1.5 rounded hover:bg-slate-50 text-slate-600"
        >
          <FiBarChart2 /> Full Reports
        </Link>
      </div>
    </div>
  );
}
