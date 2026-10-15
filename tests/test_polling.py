"""PollingService against a simulated plant of fake USRs (no hardware needed)."""
import dataclasses
import logging
import socket
import threading
import time

import pytest
from pymodbus.exceptions import ConnectionException, ModbusIOException
from pymodbus.pdu import ExceptionResponse

from lines_config import load_config
from polling import PollingService, SingleOwnerLease


# ---------------------------------------------------------------------------
# A simulated plant
# ---------------------------------------------------------------------------
class _Resp:
    def __init__(self, registers):
        self.registers = registers

    def isError(self):
        return False


class Plant:
    """host -> {"up": bool, "gauges": {slave: behaviour}}.

    A behaviour is a number (the vacuum in mbar), or one of "timeout",
    "exception", "short", "garbage", "drop", "slow", or a list of those used
    once each in order (the last item then repeats).
    """

    def __init__(self):
        self.hosts = {}
        self.connect_log = []     # (host, time) of every connect() call
        self.read_log = []        # (host, slave)
        self.factory_calls = []   # host of every client created
        self.closed = []
        self.slow_sec = 0.3
        self.lock = threading.Lock()

    def add(self, host, gauges, up=True):
        self.hosts[host] = {"up": up, "gauges": dict(gauges)}

    def factory(self, host, port, timeout=5):
        self.factory_calls.append(host)
        return _FakeClient(self, host)


class _FakeClient:
    def __init__(self, plant, host):
        self.plant, self.host = plant, host

    def connect(self):
        self.plant.connect_log.append((self.host, time.time()))
        return self.plant.hosts[self.host]["up"]

    def close(self):
        self.plant.closed.append(self.host)

    def read_holding_registers(self, address, count, unit):
        plant = self.plant
        plant.read_log.append((self.host, unit))
        with plant.lock:
            behaviour = plant.hosts[self.host]["gauges"].get(unit, "timeout")
            if isinstance(behaviour, list):
                current = behaviour[0]
                if len(behaviour) > 1:
                    behaviour.pop(0)
                behaviour = current
        if behaviour == "slow":
            time.sleep(plant.slow_sec)
            return _Resp([0, 1])
        if behaviour == "timeout":
            return ModbusIOException("No Response received from the remote unit")
        if behaviour == "exception":
            return ExceptionResponse(0x03, 2)
        if behaviour == "short":
            return _Resp([0])
        if behaviour == "garbage":
            return _Resp([0, "xx"])
        if behaviour == "drop":
            raise ConnectionException("connection dropped")
        return _Resp([0, int(round(behaviour * 1000))])


def _env(**extra):
    env = {
        "LINES": "CHOC,FRZ,SUS",
        "POLLING_MODE": "centralized",
        "LINE_CHOC_USERNAME": "c", "LINE_CHOC_PASSWORD": "p", "LINE_CHOC_GAUGES": "6",
        "LINE_CHOC_UPPER_LIMIT": "1",
        "LINE_CHOC_GATEWAYS": "10.2.0.3:502:1-2,10.2.0.4:502:3-4,10.2.0.5:502:5-6",
        "LINE_FRZ_USERNAME": "f", "LINE_FRZ_PASSWORD": "p", "LINE_FRZ_GAUGES": "4",
        "LINE_FRZ_UPPER_LIMIT": "1",
        "LINE_FRZ_GATEWAYS": "10.1.0.3:502:1-2,10.1.0.4:502:3-4",
        "LINE_SUS_USERNAME": "s", "LINE_SUS_PASSWORD": "p", "LINE_SUS_GAUGES": "2",
        "LINE_SUS_UPPER_LIMIT": "1", "LINE_SUS_GATEWAYS": "10.4.0.3",
    }
    env.update(extra)
    return env


def make(plant, env=None, **settings_override):
    cfg = load_config(env or _env())
    fast = dict(backoff_initial_sec=0.05, backoff_max_sec=0.2, cycle_pause_sec=0.05,
                modbus_timeout_sec=0.5, stale_after_sec=30.0)
    fast.update(settings_override)
    settings = dataclasses.replace(cfg.settings, **fast)
    svc = PollingService(cfg.lines, settings, client_factory=plant.factory)
    return svc


def wait_for(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def plant():
    p = Plant()
    p.add("10.2.0.3", {1: 0.11, 2: 0.12})
    p.add("10.2.0.4", {3: 0.13, 4: 0.14})
    p.add("10.2.0.5", {5: 0.15, 6: 0.16})
    p.add("10.1.0.3", {1: 5.01, 2: 5.02})
    p.add("10.1.0.4", {3: 5.03, 4: 5.04})
    p.add("10.4.0.3", {1: 9.01, 2: 9.02})
    return p


@pytest.fixture
def running(plant):
    services = []

    def _make(**kw):
        svc = make(plant, **kw)
        services.append(svc)
        return svc

    yield _make
    for svc in services:
        svc.stop(timeout=3)


def valid(svc, line, sid):
    return svc.gauge_snapshot(line, sid)["freshness"] == "valid"


# ---------------------------------------------------------------------------
# Normal operation
# ---------------------------------------------------------------------------
def test_every_usr_gets_a_worker_and_every_gauge_its_own_reading(plant, running):
    svc = running()
    started = svc.start()
    assert len(started) == 3 + 2 + 1       # one worker per USR, all lines
    assert wait_for(lambda: all(valid(svc, "CHOC", n) for n in range(1, 7))
                    and all(valid(svc, "FRZ", n) for n in range(1, 5))
                    and all(valid(svc, "SUS", n) for n in (1, 2)))

    # Same slave number on different lines stays separate (each USR answers for its own).
    assert svc.gauge_snapshot("CHOC", 1)["value"] == 0.11
    assert svc.gauge_snapshot("FRZ", 1)["value"] == 5.01
    assert svc.gauge_snapshot("SUS", 1)["value"] == 9.01
    snap = svc.gauge_snapshot("CHOC", 4)
    assert (snap["usr_id"], snap["usr_ip"], snap["slave_id"]) == ("choc-usr-02", "10.2.0.4", 4)
    assert (snap["connection_status"], snap["polling_status"]) == ("connected", "running")
    assert snap["communication_status"] == "success" and snap["last_success"]

    # Each gauge was only ever asked of the USR that owns it.
    owners = {(h, u) for h, u in plant.read_log}
    assert ("10.2.0.3", 3) not in owners and ("10.2.0.4", 1) not in owners
    assert ("10.2.0.5", 5) in owners and ("10.1.0.4", 4) in owners


def test_start_is_idempotent(plant, running):
    svc = running()
    first = svc.start()
    assert svc.start() == [] and svc.start() == []          # nothing new started
    assert wait_for(lambda: valid(svc, "CHOC", 1))
    assert len(first) == 6
    assert plant.factory_calls.count("10.2.0.3") == 1        # one client, one worker, per USR
    workers = [t for t in threading.enumerate() if t.name.startswith("poll-choc-usr-01")]
    assert len(workers) == 1


def test_start_after_a_worker_died_restarts_only_that_worker(plant, running):
    svc = running()
    svc.start()
    assert wait_for(lambda: valid(svc, "CHOC", 1))
    key = ("CHOC", "choc-usr-01")
    svc._workers[key]["stop"].set()
    svc._workers[key]["thread"].join(3)
    assert not svc.worker_alive(*key)
    assert svc.start() == [key]
    assert wait_for(lambda: svc.worker_alive(*key))


# ---------------------------------------------------------------------------
# Independent failure
# ---------------------------------------------------------------------------
def test_one_failed_usr_does_not_stop_the_others(plant, running):
    plant.hosts["10.2.0.4"]["up"] = False                     # choc-usr-02 is down
    svc = running()
    svc.start()
    healthy = (("CHOC", 1), ("CHOC", 5), ("CHOC", 6), ("FRZ", 1), ("FRZ", 4), ("SUS", 2))
    assert wait_for(lambda: all(valid(svc, line, sid) for line, sid in healthy))
    assert wait_for(lambda: svc.usr_snapshot("CHOC", "choc-usr-02")["connection_status"] == "disconnected")

    dead = svc.usr_snapshot("CHOC", "choc-usr-02")
    assert dead["polling_status"] == "error" and dead["consecutive_failures"] >= 1
    assert dead["last_error"] and dead["last_error_time"]
    for sid in (3, 4):
        g = svc.gauge_snapshot("CHOC", sid)
        assert (g["communication_status"], g["freshness"], g["value"]) == ("connection_error", "unavailable", None)

    # Neighbours on other USRs, and other lines, are healthy and keep updating.
    for line, sid in (("CHOC", 1), ("CHOC", 6), ("FRZ", 1), ("SUS", 2)):
        g = svc.gauge_snapshot(line, sid)
        assert g["freshness"] == "valid" and g["connection_status"] == "connected"
    before = len([r for r in plant.read_log if r[0] == "10.2.0.3"])
    assert wait_for(lambda: len([r for r in plant.read_log if r[0] == "10.2.0.3"]) > before + 2)


def test_a_slow_usr_does_not_delay_the_others(plant, running):
    plant.hosts["10.2.0.3"]["gauges"] = {1: "slow", 2: "slow"}   # each read takes 0.3 s
    svc = running()
    svc.start()
    time.sleep(1.5)
    slow_reads = len([r for r in plant.read_log if r[0] == "10.2.0.3"])
    fast_reads = len([r for r in plant.read_log if r[0] == "10.2.0.4"])
    assert slow_reads <= 6
    assert fast_reads > slow_reads * 4                        # the fast USR kept its own pace


def test_gauge_failures_are_per_gauge_and_leave_the_usr_connected(plant, running):
    plant.hosts["10.2.0.3"]["gauges"] = {1: "timeout", 2: 0.12}
    plant.hosts["10.2.0.4"]["gauges"] = {3: "exception", 4: "short"}
    plant.hosts["10.2.0.5"]["gauges"] = {5: "garbage", 6: 0.16}
    svc = running()
    svc.start()
    assert wait_for(lambda: valid(svc, "CHOC", 2) and valid(svc, "CHOC", 6))

    want = {1: "timeout", 3: "modbus_exception", 4: "invalid_response", 5: "decode_error"}
    assert wait_for(lambda: all(svc.gauge_snapshot("CHOC", s)["communication_status"] == st
                                for s, st in want.items()))
    for sid in want:
        g = svc.gauge_snapshot("CHOC", sid)
        assert g["freshness"] == "unavailable" and g["last_error"] and g["last_error_time"]
        # The USR itself is fine -- a connected USR does not prove its gauges respond.
        assert g["connection_status"] == "connected"
    assert svc.gauge_snapshot("CHOC", 2)["communication_status"] == "success"


def test_recovery_after_the_usr_comes_back(plant, running):
    plant.hosts["10.2.0.4"]["up"] = False
    svc = running()
    svc.start()
    assert wait_for(lambda: svc.usr_snapshot("CHOC", "choc-usr-02")["connection_status"] == "disconnected")
    assert not valid(svc, "CHOC", 3)

    plant.hosts["10.2.0.4"]["up"] = True
    assert wait_for(lambda: valid(svc, "CHOC", 3) and valid(svc, "CHOC", 4))
    # The failure counter clears only after a whole successful cycle, so that a
    # flapping USR cannot hide behind a reset on every reconnect.
    assert wait_for(lambda: svc.usr_snapshot("CHOC", "choc-usr-02")["consecutive_failures"] == 0)
    usr = svc.usr_snapshot("CHOC", "choc-usr-02")
    assert (usr["connection_status"], usr["polling_status"], usr["consecutive_failures"]) == ("connected", "running", 0)
    assert usr["last_error"]                       # the history of the outage stays visible


def test_connection_lost_mid_poll_marks_the_usr_down_then_reconnects(plant, running):
    plant.hosts["10.2.0.3"]["gauges"] = {1: ["drop", "drop", 0.11], 2: 0.12}
    svc = running()
    svc.start()
    assert wait_for(lambda: svc.usr_snapshot("CHOC", "choc-usr-01")["connection_status"] == "disconnected"
                    or plant.factory_calls.count("10.2.0.3") > 1)
    assert wait_for(lambda: valid(svc, "CHOC", 1) and valid(svc, "CHOC", 2))
    assert plant.factory_calls.count("10.2.0.3") >= 2        # a fresh client after the drop
    assert "10.2.0.3" in plant.closed                        # the broken one was closed


def test_reconnect_attempts_back_off_exponentially_up_to_a_cap(plant, running):
    plant.hosts["10.4.0.3"]["up"] = False
    svc = running(backoff_initial_sec=0.05, backoff_max_sec=0.2)
    svc.start()
    assert wait_for(lambda: len([c for c in plant.connect_log if c[0] == "10.4.0.3"]) >= 7, 6)
    times = [t for h, t in plant.connect_log if h == "10.4.0.3"]
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert gaps[0] < 0.1                       # ~0.05
    assert gaps[3] > gaps[0] * 2               # grown
    assert max(gaps) < 0.2 + 0.15              # ...but capped near max


# ---------------------------------------------------------------------------
# Retries
# ---------------------------------------------------------------------------
def test_bounded_retries_turn_a_blip_into_a_success(plant, running):
    plant.hosts["10.4.0.3"]["gauges"] = {1: ["timeout", "timeout", 0.42], 2: 0.5}
    svc = running(read_retries=2)
    svc.start()
    assert wait_for(lambda: valid(svc, "SUS", 1))
    assert svc.gauge_snapshot("SUS", 1)["value"] == 0.42


def test_without_retries_the_first_failure_is_recorded(plant, running):
    plant.hosts["10.4.0.3"]["gauges"] = {1: ["timeout", 0.42], 2: 0.5}
    svc = running(read_retries=0)
    svc.start()
    assert wait_for(lambda: svc.gauge_snapshot("SUS", 1)["communication_status"] is not None)
    assert svc.gauge_snapshot("SUS", 1)["last_error"]      # the blip was seen
    assert wait_for(lambda: valid(svc, "SUS", 1))           # and cleared by the next cycle


def test_retries_are_bounded(plant, running):
    plant.hosts["10.4.0.3"]["gauges"] = {1: "timeout", 2: 0.5}
    svc = running(read_retries=2, cycle_pause_sec=5)
    svc.start()
    assert wait_for(lambda: valid(svc, "SUS", 2))
    time.sleep(0.4)
    assert len([r for r in plant.read_log if r == ("10.4.0.3", 1)]) == 3   # 1 try + 2 retries


# ---------------------------------------------------------------------------
# What is (not) polled
# ---------------------------------------------------------------------------
def test_line_specific_mode_polls_only_the_configured_lines(plant, running):
    svc = running(polling_mode="line_specific", poll_lines=frozenset({"FRZ"}))
    started = svc.start()
    assert {k[0] for k in started} == {"FRZ"} and len(started) == 2
    assert wait_for(lambda: valid(svc, "FRZ", 1))
    time.sleep(0.2)
    assert not any(h.startswith(("10.2.", "10.4.")) for h, _ in plant.read_log)
    assert not any(h.startswith(("10.2.", "10.4.")) for h in plant.factory_calls)

    g = svc.gauge_snapshot("CHOC", 1)
    assert (g["polled_here"], g["polling_status"], g["freshness"]) == (False, "stopped", "unavailable")


def test_disabled_usrs_and_gauges_are_not_polled(plant, running):
    env = _env(LINE_CHOC_DISABLED_USRS="2", LINE_CHOC_DISABLED_GAUGES="6")
    svc = make(plant, env)
    try:
        started = svc.start()
        assert ("CHOC", "choc-usr-02") not in started and len(started) == 5
        assert wait_for(lambda: valid(svc, "CHOC", 1) and valid(svc, "CHOC", 5))
        time.sleep(0.2)
        assert not any(h == "10.2.0.4" for h, _ in plant.read_log)      # whole USR skipped
        assert ("10.2.0.5", 6) not in plant.read_log                     # single gauge skipped
        assert svc.gauge_snapshot("CHOC", 3) is None and svc.gauge_snapshot("CHOC", 6) is None
    finally:
        svc.stop(3)


def test_unknown_gauge_has_no_snapshot(plant, running):
    svc = running()
    assert svc.gauge_snapshot("CHOC", 7) is None and svc.gauge_snapshot("CHOC", 0) is None


# ---------------------------------------------------------------------------
# Freshness
# ---------------------------------------------------------------------------
def test_freshness_follows_the_clock(plant):
    now = [1000.0]
    cfg = load_config(_env())
    svc = PollingService(cfg.lines, dataclasses.replace(cfg.settings, stale_after_sec=30),
                         client_factory=plant.factory, clock=lambda: now[0])
    assert svc.gauge_snapshot("SUS", 1)["freshness"] == "unavailable"

    svc._gauges[("SUS", 1)].update(value=0.3, last_success=now[0], communication_status="success")
    assert svc.gauge_snapshot("SUS", 1)["freshness"] == "valid"
    now[0] += 29
    assert svc.gauge_snapshot("SUS", 1)["freshness"] == "valid"
    now[0] += 5
    s = svc.gauge_snapshot("SUS", 1)
    assert s["freshness"] == "stale" and s["value"] is None and s["last_value"] == 0.3


# ---------------------------------------------------------------------------
# Shutdown and restart
# ---------------------------------------------------------------------------
def test_stop_ends_every_worker_closes_clients_and_allows_a_restart(plant, running):
    svc = running()
    svc.start()
    # Every worker must have connected, or there is nothing for it to close.
    assert wait_for(lambda: {"10.2.0.3", "10.2.0.4", "10.2.0.5", "10.1.0.3", "10.1.0.4", "10.4.0.3"}
                    <= {h for h, _ in plant.read_log})
    svc.stop(timeout=3)

    assert not any(t.is_alive() for t in threading.enumerate() if t.name.startswith("poll-"))
    assert svc.usr_snapshot("CHOC", "choc-usr-01")["polling_status"] == "stopped"
    assert set(plant.closed) >= {"10.2.0.3", "10.2.0.4", "10.2.0.5", "10.1.0.3", "10.1.0.4", "10.4.0.3"}

    assert len(svc.start()) == 6                          # restart works
    assert wait_for(lambda: valid(svc, "CHOC", 1))


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def test_a_dead_gauge_logs_once_with_line_usr_gauge_and_slave(plant, running, caplog):
    plant.hosts["10.4.0.3"]["gauges"] = {1: "timeout", 2: 0.5}
    caplog.set_level(logging.INFO, logger="polling")
    svc = running(cycle_pause_sec=0.02)
    svc.start()
    assert wait_for(lambda: len([r for r in plant.read_log if r == ("10.4.0.3", 1)]) >= 6)

    failures = [r.getMessage() for r in caplog.records if "gauge read failed" in r.getMessage()]
    assert len(failures) == 1                              # not one line per cycle
    msg = failures[0]
    for field in ("line=SUS", "usr=sus-usr-01", "gauge=1", "slave=1", "status=timeout"):
        assert field in msg
    started = [r.getMessage() for r in caplog.records if "polling worker started" in r.getMessage()]
    assert len(started) == 6 and all("line=" in m and "usr=" in m for m in started)


# ---------------------------------------------------------------------------
# Single-owner lease
# ---------------------------------------------------------------------------
def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_only_one_owner_can_hold_the_lease():
    port = _free_port()
    first, second = SingleOwnerLease(port), SingleOwnerLease(port)
    try:
        assert first.acquire() is True and first.held
        assert first.acquire() is True                     # re-acquire by the owner is harmless
        assert second.acquire() is False and not second.held
        first.release()
        assert not first.held
        assert second.acquire() is True                    # free again once released
    finally:
        first.release()
        second.release()
