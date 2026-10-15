"""Background Modbus polling, managed by the backend.

* One worker thread per enabled USR (Modbus TCP gateway). A slow, dead or
  misbehaving USR only ever delays its own gauges: workers share nothing but
  the status tables below.
* Workers belong to the service, not to a browser session, so page refreshes,
  logins and extra tabs never create or stop one. ``start()`` is idempotent.
* Device and gauge health are tracked separately -- a connected USR does not
  prove that every gauge behind it answers.
* Only the lines in ``settings.poll_lines`` are polled by this process
  (see POLLING_MODE in .env).

Status vocabulary
-----------------
connection     connected | disconnected | unknown          (USR TCP link)
polling        running | delayed | stopped | error         (worker health)
communication  success | timeout | connection_error | invalid_response |
               modbus_exception | decode_error             (last read of a gauge)
freshness      valid | stale | unavailable                 (can the value be trusted now)
"""

import logging
import socket
import threading
import time
from datetime import datetime

from pymodbus.client.sync import ModbusTcpClient

from register_maps import (
    CONNECTION_ERROR,
    REGISTER_MAPS,
    SUCCESS,
    read_gauge,
)

logger = logging.getLogger(__name__)

CONNECTED, DISCONNECTED, UNKNOWN = "connected", "disconnected", "unknown"
RUNNING, DELAYED, STOPPED, ERROR = "running", "delayed", "stopped", "error"
VALID, STALE, UNAVAILABLE = "valid", "stale", "unavailable"


def _iso(ts):
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds") if ts else None


class SingleOwnerLease:
    """Lets only one process on this PC poll the gauges.

    Two processes polling the same USRs would double the traffic on a serial
    bus. The lease is a local TCP port that only one process can bind; the OS
    releases it automatically if the owner dies, so there is no stale lock
    file to clean up.
    """

    def __init__(self, port):
        self.port = port
        self._sock = None

    @property
    def held(self):
        return self._sock is not None

    def acquire(self):
        if self._sock is not None:
            return True
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", self.port))
        except OSError:
            sock.close()
            return False
        self._sock = sock
        return True

    def release(self):
        if self._sock is not None:
            self._sock.close()
            self._sock = None


class PollingService:
    def __init__(self, lines, settings, client_factory=None, clock=time.time):
        self.lines = lines
        self.settings = settings
        self._client_factory = client_factory or ModbusTcpClient
        self._clock = clock
        self._lock = threading.Lock()
        self._workers = {}   # (line_key, usr_id) -> {"thread", "stop"}
        self._gauges = {}    # (line_key, slave_id) -> status dict
        self._usrs = {}      # (line_key, usr_id)   -> status dict

        for line in lines.values():
            for gw in line.gateways:
                self._usrs[(line.key, gw.usr_id)] = {
                    "connection": UNKNOWN,
                    "polling": STOPPED,
                    "started_at": None,
                    "last_cycle_at": None,
                    "last_cycle_sec": None,
                    "consecutive_failures": 0,
                    "last_error": None,
                    "last_error_time": None,
                }
            for sid in line.gauge_ids:
                self._gauges[(line.key, sid)] = {
                    "value": None,
                    "last_success": None,
                    "communication_status": None,
                    "last_error": None,
                    "last_error_time": None,
                }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def polled_here(self, line_key):
        return line_key in self.settings.poll_lines

    def start(self):
        """Start a worker for every enabled USR of every line polled here.
        Safe to call repeatedly: a USR that already has a live worker is skipped."""
        started = []
        with self._lock:
            for line in self.lines.values():
                if not self.polled_here(line.key):
                    continue
                for gw in line.gateways:
                    if not gw.enabled:
                        continue
                    key = (line.key, gw.usr_id)
                    existing = self._workers.get(key)
                    if existing and existing["thread"].is_alive():
                        continue
                    stop = threading.Event()
                    thread = threading.Thread(
                        target=self._worker, args=(line, gw, stop), daemon=True,
                        name=f"poll-{gw.usr_id}",
                    )
                    self._workers[key] = {"thread": thread, "stop": stop}
                    thread.start()
                    started.append(key)
        return started

    def stop(self, timeout=5.0):
        """Ask every worker to finish and wait (bounded) for them."""
        with self._lock:
            entries = list(self._workers.items())
        for _, entry in entries:
            entry["stop"].set()
        deadline = self._clock() + timeout
        for _, entry in entries:
            entry["thread"].join(max(0.0, deadline - self._clock()))
        with self._lock:
            for key, entry in entries:
                if not entry["thread"].is_alive():
                    self._workers.pop(key, None)

    def worker_alive(self, line_key, usr_id):
        entry = self._workers.get((line_key, usr_id))
        return bool(entry and entry["thread"].is_alive())

    # ------------------------------------------------------------------
    # The worker
    # ------------------------------------------------------------------
    def _worker(self, line, gw, stop):
        s = self.settings
        key = (line.key, gw.usr_id)
        reg_map = REGISTER_MAPS[line.register_map]
        slave_ids = [n for n in gw.gauge_numbers if n not in line.disabled_gauges]
        ctx = f"line={line.key} usr={gw.usr_id} host={gw.host}:{gw.port}"
        logger.info("polling worker started %s gauges=%s-%s", ctx, gw.first, gw.last)

        with self._lock:
            self._usrs[key].update(polling=RUNNING, started_at=self._clock())

        client = None
        backoff = s.backoff_initial_sec
        try:
            while not stop.is_set():
                cycle_start = self._clock()
                try:
                    if client is None:
                        client = self._client_factory(
                            host=gw.host, port=gw.port, timeout=s.modbus_timeout_sec
                        )
                    if not client.connect():
                        raise ConnectionError("cannot connect to the USR")
                    self._usr_connected(key, ctx)
                    backoff = s.backoff_initial_sec

                    lost = False
                    for sid in slave_ids:
                        if stop.is_set():
                            break
                        result = self._read_with_retries(client, sid, reg_map, stop)
                        self._record(line, gw, sid, result)
                        if result.status == CONNECTION_ERROR:
                            lost = True
                            break
                        stop.wait(0.03)
                    if lost:
                        raise ConnectionError("connection to the USR was lost while polling")

                    self._usr_cycle_done(key, self._clock() - cycle_start)
                    stop.wait(s.cycle_pause_sec)

                except Exception as exc:
                    self._usr_failed(line, gw, ctx, str(exc) or exc.__class__.__name__)
                    self._close(client)
                    client = None
                    stop.wait(backoff)
                    backoff = min(backoff * 2, s.backoff_max_sec)
        finally:
            self._close(client)
            with self._lock:
                self._usrs[key]["polling"] = STOPPED
            logger.info("polling worker stopped %s", ctx)

    @staticmethod
    def _close(client):
        try:
            if client:
                client.close()
        except Exception:
            pass

    def _read_with_retries(self, client, sid, reg_map, stop):
        """One read, plus up to `read_retries` more for failures that are
        about the gauge (a lost USR connection is handled by the caller)."""
        result = read_gauge(client, sid, reg_map)
        for _ in range(self.settings.read_retries):
            if result.status in (SUCCESS, CONNECTION_ERROR) or stop.is_set():
                break
            stop.wait(0.2)
            result = read_gauge(client, sid, reg_map)
        return result

    # ------------------------------------------------------------------
    # Status recording (all under the lock)
    # ------------------------------------------------------------------
    def _record(self, line, gw, sid, result):
        now = self._clock()
        with self._lock:
            g = self._gauges[(line.key, sid)]
            previous = g["communication_status"]
            g["communication_status"] = result.status
            if result.status == SUCCESS:
                g["value"] = result.value
                g["last_success"] = now
            else:
                g["last_error"] = result.error
                g["last_error_time"] = now
        # Log changes only -- a dead gauge must not write a line every cycle.
        if result.status != previous:
            fields = f"line={line.key} usr={gw.usr_id} gauge={sid} slave={sid}"
            if result.status == SUCCESS:
                if previous is not None:
                    logger.info("gauge recovered %s", fields)
            else:
                logger.warning("gauge read failed %s status=%s error=%s",
                               fields, result.status, result.error)

    def _usr_connected(self, key, ctx):
        with self._lock:
            u = self._usrs[key]
            was = u["connection"]
            u["connection"] = CONNECTED
            u["polling"] = RUNNING
        if was == DISCONNECTED:
            logger.info("USR reconnected %s", ctx)

    def _usr_cycle_done(self, key, duration):
        with self._lock:
            u = self._usrs[key]
            u.update(last_cycle_at=self._clock(), last_cycle_sec=duration,
                     consecutive_failures=0, polling=RUNNING)

    def _usr_failed(self, line, gw, ctx, error):
        now = self._clock()
        with self._lock:
            u = self._usrs[(line.key, gw.usr_id)]
            was = u["connection"]
            u.update(connection=DISCONNECTED, polling=ERROR, last_error=error,
                     last_error_time=now, consecutive_failures=u["consecutive_failures"] + 1)
            # Nothing behind an unreachable USR can be trusted.
            for sid in gw.gauge_numbers:
                g = self._gauges.get((line.key, sid))
                if g is not None:
                    g.update(communication_status=CONNECTION_ERROR, last_error=error,
                             last_error_time=now)
            failures = u["consecutive_failures"]
        if was != DISCONNECTED:
            logger.warning("USR unreachable %s error=%s", ctx, error)
        else:
            logger.debug("USR still unreachable %s attempts=%s", ctx, failures)

    # ------------------------------------------------------------------
    # Read side
    # ------------------------------------------------------------------
    def _effective_polling(self, line_key, usr_id, usr, now):
        if not self.polled_here(line_key) or not self.worker_alive(line_key, usr_id):
            return STOPPED
        if usr["polling"] == ERROR:
            return ERROR
        if usr["polling"] != RUNNING:
            return usr["polling"]
        reference = usr["last_cycle_at"] or usr["started_at"] or now
        return DELAYED if now - reference > self.settings.stale_after_sec else RUNNING

    def usr_snapshot(self, line_key, usr_id):
        line = self.lines[line_key]
        gw = line.gateway_by_id(usr_id)
        now = self._clock()
        with self._lock:
            u = dict(self._usrs[(line_key, usr_id)])
        return {
            "usr_id": usr_id,
            "host": gw.host,
            "port": gw.port,
            "first_gauge": gw.first,
            "last_gauge": gw.last,
            "enabled": gw.enabled,
            "polled_here": self.polled_here(line_key),
            "worker_alive": self.worker_alive(line_key, usr_id),
            "connection_status": u["connection"],
            "polling_status": self._effective_polling(line_key, usr_id, u, now),
            "last_cycle_at": _iso(u["last_cycle_at"]),
            "last_cycle_sec": round(u["last_cycle_sec"], 2) if u["last_cycle_sec"] is not None else None,
            "consecutive_failures": u["consecutive_failures"],
            "last_error": u["last_error"],
            "last_error_time": _iso(u["last_error_time"]),
        }

    def gauge_snapshot(self, line_key, slave_id):
        """Everything known about one gauge right now, or None if the line has no such gauge."""
        line = self.lines[line_key]
        gw = line.gateway_for(slave_id)
        if gw is None or slave_id not in line.gauge_ids:
            return None
        now = self._clock()
        with self._lock:
            g = dict(self._gauges[(line_key, slave_id)])
            u = dict(self._usrs[(line_key, gw.usr_id)])

        if g["last_success"] is None:
            freshness = UNAVAILABLE
        elif (g["communication_status"] == SUCCESS
              and now - g["last_success"] <= self.settings.stale_after_sec):
            freshness = VALID
        else:
            freshness = STALE

        return {
            "line": line_key,
            "gauge_id": slave_id,
            "slave_id": slave_id,
            "usr_id": gw.usr_id,
            "usr_ip": gw.host,
            "usr_port": gw.port,
            # `value` is only ever a trustworthy current reading; the last
            # known value stays visible separately so the UI can grey it out.
            "value": g["value"] if freshness == VALID else None,
            "last_value": g["value"],
            "unit": REGISTER_MAPS[line.register_map].unit,
            "freshness": freshness,
            "communication_status": g["communication_status"],
            "connection_status": u["connection"],
            "polling_status": self._effective_polling(line_key, gw.usr_id, u, now),
            "last_success": _iso(g["last_success"]),
            "last_error": g["last_error"],
            "last_error_time": _iso(g["last_error_time"]),
            "polled_here": self.polled_here(line_key),
        }

    def line_snapshot(self, line_key):
        """USR-by-USR health for a line, each with its gauges' snapshots."""
        line = self.lines[line_key]
        out = []
        for gw in line.gateways:
            snap = self.usr_snapshot(line_key, gw.usr_id)
            snap["gauges"] = {
                sid: self.gauge_snapshot(line_key, sid)
                for sid in gw.gauge_numbers if sid in line.gauge_ids
            }
            out.append(snap)
        return out
