import StatusBadge from "./StatusBadge";
import { formatTime } from "../utils/time";

/** Where a gauge lives and how healthy its communication is right now. */
export default function GaugeDeviceStatus({ live }) {
  if (!live) return null;

  return (
    <div className="mt-3 pt-3 border-t text-xs space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="font-semibold text-slate-600">Device</span>
        <StatusBadge kind="freshness" value={live.freshness} />
      </div>

      <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-slate-500">
        <span>USR</span>
        <b className="text-slate-800 font-mono">{live.usr_id}</b>
        <span>Address</span>
        <b className="text-slate-800 font-mono">
          {live.usr_ip}:{live.usr_port}
        </b>
        <span>Slave ID</span>
        <b className="text-slate-800 font-mono">{live.slave_id}</b>
        <span>Connection</span>
        <span><StatusBadge kind="connection" value={live.connection_status} /></span>
        <span>Polling</span>
        <span><StatusBadge kind="polling" value={live.polling_status} /></span>
        <span>Last read</span>
        <span><StatusBadge kind="communication" value={live.communication_status} /></span>
        <span>Last success</span>
        <span className="text-slate-800 tabular">{formatTime(live.last_success)}</span>
      </div>

      {live.last_error && (
        <div className="rounded bg-rose-50 text-rose-700 px-2 py-1.5">
          <div className="font-semibold">Last error</div>
          <div>{live.last_error}</div>
          <div className="text-rose-500 tabular">{formatTime(live.last_error_time)}</div>
        </div>
      )}

      {!live.polled_here && (
        <div className="rounded bg-slate-100 text-slate-600 px-2 py-1.5">
          This PC does not poll this line, so no live readings are available here.
        </div>
      )}
    </div>
  );
}
