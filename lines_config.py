"""Production-line configuration, read entirely from the environment (.env).

Adding or changing a line never needs a code change or a database edit:
edit .env and restart the app. See .env.example for the full format.

Conventions
-----------
* Gauge number == Modbus slave ID, counting from 1 *within each line*
  (Chocolate 1-18, Visi Cooler 1-30, Freezer 1-54, SUS 1-15). Two lines may
  therefore both have a "gauge 1" -- everything downstream is keyed by
  (line, gauge), never by slave ID alone.
* A line owns one or more Modbus TCP gateways (USR devices). Each gateway
  serves a contiguous range of that line's gauges and has a stable ID such as
  "freezer-usr-03" (the line key plus its position in LINE_<KEY>_GATEWAYS --
  keep the order stable). The IP address is configuration, not identity.
* Users: every line has its own login, and extra USERS may be authorised for
  several lines (admins, supervisors).
* Polling: this process polls only the lines in POLL_LINES
  (POLLING_MODE=line_specific, one PC per line) or all of them
  (POLLING_MODE=centralized, only when one host can reach every line network).
"""

import ipaddress
import os
import re
from dataclasses import dataclass
from typing import Mapping, Optional

from dotenv import load_dotenv

from register_maps import REGISTER_MAPS

load_dotenv()

KEY_RE = re.compile(r"^[A-Za-z0-9_]{1,50}$")

# Same limits the old Settings page enforced, so behaviour is unchanged.
MAX_SLAVE_ID = 247  # Modbus: valid unit IDs are 1..247
GAP_RANGE = (0, 500)
READING_DELAY_RANGE = (0, 3600)
POLL_INTERVAL_RANGE = (60, 3600)
MIN_DURATION_RANGE = (0, 3600)

POLLING_MODES = ("line_specific", "centralized")
ROLES = ("operator", "admin")


class ConfigError(Exception):
    """Raised with *every* problem found, so one restart fixes them all."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__(
            "Invalid line configuration in .env:\n  - " + "\n  - ".join(self.problems)
        )


@dataclass(frozen=True)
class Gateway:
    """One USR / Modbus TCP gateway and the gauge numbers wired behind it."""

    host: str
    port: int
    first: int
    last: int
    usr_id: str = ""        # stable identity, e.g. "freezer-usr-03"
    enabled: bool = True    # a disabled USR is not polled and its gauges are out of service

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def gauge_numbers(self) -> range:
        return range(self.first, self.last + 1)


@dataclass(frozen=True)
class Line:
    key: str
    label: str
    username: str
    password: str
    gauge_count: int
    gateways: tuple
    disabled_gauges: frozenset
    upper_limit: float
    poll_interval_sec: int
    reading_delay_sec: int
    min_duration_sec: int
    gap: int
    # Network documentation, validated at startup when given.
    subnet: Optional[str] = None          # line-side network, e.g. 192.168.1.0/24
    pc_line_ip: Optional[str] = None      # this line's PC on the line-side network
    router_ip: Optional[str] = None
    company_pc_ip: Optional[str] = None   # the line PC's address on the company network
    register_map: str = "pirani_default"

    @property
    def gauge_ids(self) -> list:
        """Enabled gauge numbers (== slave IDs), ascending."""
        return [
            n for n in range(1, self.gauge_count + 1) if n not in self.disabled_gauges
        ]

    def gateway_for(self, gauge_id: int) -> Optional[Gateway]:
        for gw in self.gateways:
            if gw.first <= gauge_id <= gw.last:
                return gw
        return None

    def gateway_by_id(self, usr_id: str) -> Optional[Gateway]:
        for gw in self.gateways:
            if gw.usr_id == usr_id:
                return gw
        return None


@dataclass(frozen=True)
class User:
    username: str
    password: str
    lines: tuple      # authorised line keys; one = auto-selected, several = chooser
    role: str = "operator"


@dataclass(frozen=True)
class Settings:
    """Process-wide polling behaviour."""

    polling_mode: str
    poll_lines: frozenset
    modbus_timeout_sec: float
    read_retries: int
    backoff_initial_sec: float
    backoff_max_sec: float
    cycle_pause_sec: float
    stale_after_sec: float
    lease_port: int


@dataclass(frozen=True)
class Config:
    lines: dict
    users: dict       # lower-case username -> User
    settings: Settings


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------
def _get(env, name):
    value = env.get(name)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _parse_int_list(text, problems, var):
    """'5,7,10-12' -> {5, 7, 10, 11, 12}"""
    out = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(\d+)(?:\s*-\s*(\d+))?", part)
        if not m:
            problems.append(f"{var}: '{part}' is not a number or range like 10-12")
            continue
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else lo
        if hi < lo:
            problems.append(f"{var}: range '{part}' runs backwards")
            continue
        out.update(range(lo, hi + 1))
    return out


def _parse_gateways(text, gauge_count, problems, var, key=""):
    """'host:port:first-last, host:port:first-last' -> [Gateway, ...]

    With a single gateway the range may be left out ('192.168.1.10:502'), and
    it then serves every gauge of the line. The port may also be left out
    when it is the Modbus default (502).
    """
    specs = [s.strip() for s in text.split(",") if s.strip()]
    if not specs:
        problems.append(f"{var}: at least one gateway is required")
        return []

    gateways = []
    for spec in specs:
        parts = [p.strip() for p in spec.split(":")]
        if len(parts) > 3 or not parts[0]:
            problems.append(f"{var}: '{spec}' should look like host:port:first-last")
            continue

        host = parts[0]
        port = 502
        if len(parts) >= 2:
            if not parts[1].isdigit() or not (1 <= int(parts[1]) <= 65535):
                problems.append(f"{var}: '{spec}' has an invalid port '{parts[1]}'")
                continue
            port = int(parts[1])

        if len(parts) == 3:
            m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", parts[2])
            if not m:
                problems.append(
                    f"{var}: '{spec}' has an invalid gauge range '{parts[2]}' (use e.g. 1-6)"
                )
                continue
            first, last = int(m.group(1)), int(m.group(2))
        elif len(specs) == 1:
            first, last = 1, gauge_count
        else:
            problems.append(
                f"{var}: '{spec}' needs a gauge range (host:port:first-last) "
                "because the line has more than one gateway"
            )
            continue

        if first < 1 or last < first or last > gauge_count:
            problems.append(
                f"{var}: gauge range {first}-{last} in '{spec}' is outside 1-{gauge_count}"
            )
            continue
        usr_id = f"{key.lower().replace('_', '-')}-usr-{len(gateways) + 1:02d}"
        gateways.append(Gateway(host, port, first, last, usr_id=usr_id))

    # Every gauge 1..N must sit behind exactly one gateway.
    owner = {}
    for gw in gateways:
        for n in gw.gauge_numbers:
            if n in owner:
                problems.append(
                    f"{var}: gauge {n} is assigned to both {owner[n].address} and {gw.address}"
                )
            else:
                owner[n] = gw
    missing = [n for n in range(1, gauge_count + 1) if n not in owner]
    if missing and gateways:
        problems.append(
            f"{var}: gauge(s) {_compress(missing)} are not assigned to any gateway"
        )
    return gateways


def _compress(numbers):
    """[1,2,3,7,9,10] -> '1-3, 7, 9-10'"""
    numbers = sorted(numbers)
    runs, start, prev = [], None, None
    for n in numbers:
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            runs.append((start, prev))
            start = prev = n
    if start is not None:
        runs.append((start, prev))
    return ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in runs)


def _int_setting(env, var, default, bounds, problems):
    raw = _get(env, var)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        problems.append(f"{var}: '{raw}' is not a whole number")
        return default
    lo, hi = bounds
    if not (lo <= value <= hi):
        problems.append(f"{var}: {value} is outside the allowed range {lo}-{hi}")
        return default
    return value


# ---------------------------------------------------------------------------
# Network helpers
# ---------------------------------------------------------------------------
def _ip(text, problems, var):
    """Optional IPv4 setting. Blank -> None."""
    if not text:
        return None
    try:
        return str(ipaddress.IPv4Address(text))
    except ValueError:
        problems.append(f"{var}: '{text}' is not a valid IPv4 address")
        return None


def _usable(net, ip):
    """True for an address that may be given to a device: inside the subnet and
    neither the network address (…​.0) nor the broadcast address (…​.255)."""
    return ip in net and ip not in (net.network_address, net.broadcast_address)


def _check_line_network(key, net, pc_ip, router_ip, gateways, problems):
    p = f"LINE_{key}_"
    reserved = {}
    for name, ip in (("PC_IP", pc_ip), ("ROUTER_IP", router_ip)):
        if ip is None:
            continue
        addr = ipaddress.IPv4Address(ip)
        if not _usable(net, addr):
            problems.append(f"{p}{name}: {ip} is not a usable host address in {net}")
        reserved[addr] = name
    if pc_ip and router_ip and pc_ip == router_ip:
        problems.append(f"{p}PC_IP and {p}ROUTER_IP are both {pc_ip}")

    seen = {}
    for gw in gateways:
        try:
            addr = ipaddress.IPv4Address(gw.host)
        except ValueError:
            problems.append(
                f"{p}GATEWAYS: '{gw.host}' must be an IPv4 address because {p}SUBNET is set"
            )
            continue
        if not _usable(net, addr):
            problems.append(
                f"{p}GATEWAYS: {gw.usr_id} address {gw.host} is not a usable host address in {net}"
            )
        if addr in reserved:
            problems.append(
                f"{p}GATEWAYS: {gw.usr_id} address {gw.host} is the same as {p}{reserved[addr]}"
            )
        if gw.host in seen:
            problems.append(
                f"{p}GATEWAYS: address {gw.host} is assigned to both {seen[gw.host]} and {gw.usr_id}"
            )
        seen.setdefault(gw.host, gw.usr_id)


def _parse_disabled_usrs(text, gateways, problems, var):
    """'3, 5' or 'freezer-usr-03' -> set of usr_ids"""
    by_number = {i + 1: gw.usr_id for i, gw in enumerate(gateways)}
    known = {gw.usr_id for gw in gateways}
    out = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if part.isdigit() and int(part) in by_number:
            out.add(by_number[int(part)])
        elif part.lower() in known:
            out.add(part.lower())
        else:
            problems.append(
                f"{var}: '{part}' is not one of this line's USRs "
                f"(use 1-{len(gateways)} or an id such as {next(iter(known), 'x-usr-01')})"
            )
    return out


# ---------------------------------------------------------------------------
# Lines
# ---------------------------------------------------------------------------
def _parse_lines(env, problems) -> dict:
    raw_keys = _get(env, "LINES")
    if not raw_keys:
        problems.append(
            "LINES is not set -- list your production lines, e.g. LINES=CHOCOLATE,FREEZER"
        )
        return {}

    keys = []
    for k in raw_keys.split(","):
        k = k.strip()
        if not k:
            continue
        if not KEY_RE.match(k):
            problems.append(f"LINES: '{k}' may only contain letters, digits and _")
            continue
        k = k.upper()
        if k in keys:
            problems.append(f"LINES: '{k}' is listed twice")
            continue
        keys.append(k)

    lines = {}
    nets = {}
    for key in keys:
        p = f"LINE_{key}_"

        label = _get(env, p + "LABEL") or key.replace("_", " ").title()

        username = _get(env, p + "USERNAME")
        password = _get(env, p + "PASSWORD")
        if not username:
            problems.append(f"{p}USERNAME is required")
        if not password:
            problems.append(f"{p}PASSWORD is required")

        gauge_count = 0
        raw_count = _get(env, p + "GAUGES")
        if raw_count is None:
            problems.append(f"{p}GAUGES is required (number of gauges on this line)")
        elif not raw_count.isdigit() or not (1 <= int(raw_count) <= MAX_SLAVE_ID):
            problems.append(f"{p}GAUGES: '{raw_count}' must be a number from 1 to {MAX_SLAVE_ID}")
        else:
            gauge_count = int(raw_count)

        raw_gw = _get(env, p + "GATEWAYS")
        gateways = []
        if raw_gw is None:
            problems.append(f"{p}GATEWAYS is required (host:port:first-last, ...)")
        elif gauge_count:
            gateways = _parse_gateways(raw_gw, gauge_count, problems, p + "GATEWAYS", key)

        # Out-of-service USRs: not polled, and their gauges are out of service.
        disabled = set()
        raw_disabled_usrs = _get(env, p + "DISABLED_USRS")
        if raw_disabled_usrs and gateways:
            off = _parse_disabled_usrs(raw_disabled_usrs, gateways, problems, p + "DISABLED_USRS")
            gateways = [
                Gateway(g.host, g.port, g.first, g.last, g.usr_id, enabled=g.usr_id not in off)
                for g in gateways
            ]
            for g in gateways:
                if not g.enabled:
                    disabled.update(g.gauge_numbers)

        raw_disabled = _get(env, p + "DISABLED_GAUGES")
        if raw_disabled:
            extra = _parse_int_list(raw_disabled, problems, p + "DISABLED_GAUGES")
            outside = sorted(n for n in extra if not (1 <= n <= gauge_count))
            if outside and gauge_count:
                problems.append(
                    f"{p}DISABLED_GAUGES: {_compress(outside)} outside 1-{gauge_count}"
                )
            disabled.update(extra)

        raw_ul = _get(env, p + "UPPER_LIMIT")
        upper_limit = 0.0
        if raw_ul is None:
            problems.append(f"{p}UPPER_LIMIT is required (pass/fail ceiling in mbar)")
        else:
            try:
                upper_limit = float(raw_ul)
                if upper_limit < 0:
                    raise ValueError
            except ValueError:
                problems.append(f"{p}UPPER_LIMIT: '{raw_ul}' must be a number >= 0")
                upper_limit = 0.0

        poll = _int_setting(env, p + "POLL_INTERVAL_SEC", 60, POLL_INTERVAL_RANGE, problems)
        delay = _int_setting(env, p + "READING_DELAY_SEC", 0, READING_DELAY_RANGE, problems)
        min_dur = _int_setting(env, p + "MIN_DURATION_SEC", 600, MIN_DURATION_RANGE, problems)
        gap = _int_setting(env, p + "GAP", 0, GAP_RANGE, problems)

        register_map = _get(env, p + "REGISTER_MAP") or "pirani_default"
        if register_map not in REGISTER_MAPS:
            problems.append(
                f"{p}REGISTER_MAP: '{register_map}' is unknown "
                f"(available: {', '.join(sorted(REGISTER_MAPS))})"
            )

        # Network documentation (all optional) -- validated so that typos and
        # address clashes are caught before commissioning, not on site.
        net = None
        raw_net = _get(env, p + "SUBNET")
        if raw_net:
            try:
                net = ipaddress.IPv4Network(raw_net, strict=True)
                nets[key] = net
            except ValueError:
                problems.append(
                    f"{p}SUBNET: '{raw_net}' is not a valid network such as 192.168.1.0/24 "
                    "(the address must be the network address, ending in .0 for a /24)"
                )
        pc_ip = _ip(_get(env, p + "PC_IP"), problems, p + "PC_IP")
        router_ip = _ip(_get(env, p + "ROUTER_IP"), problems, p + "ROUTER_IP")
        company_pc_ip = _ip(_get(env, p + "COMPANY_PC_IP"), problems, p + "COMPANY_PC_IP")
        if net is not None:
            _check_line_network(key, net, pc_ip, router_ip, gateways, problems)

        lines[key] = Line(
            key=key,
            label=label,
            username=username or "",
            password=password or "",
            gauge_count=gauge_count,
            gateways=tuple(gateways),
            disabled_gauges=frozenset(disabled),
            upper_limit=upper_limit,
            poll_interval_sec=poll,
            reading_delay_sec=delay,
            min_duration_sec=min_dur,
            gap=gap,
            subnet=str(net) if net is not None else None,
            pc_line_ip=pc_ip,
            router_ip=router_ip,
            company_pc_ip=company_pc_ip,
            register_map=register_map,
        )

    # Cross-line checks: line networks must not overlap, logins must be
    # unambiguous, and a gateway must belong to exactly one line (a shared
    # gateway would put two lines' "gauge 1" on one Modbus bus).
    names = list(nets)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if nets[a].overlaps(nets[b]):
                problems.append(
                    f"Line networks overlap: {a} ({nets[a]}) and {b} ({nets[b]}) -- "
                    "each production line needs its own subnet"
                )

    seen_users = {}
    for line in lines.values():
        if not line.username:
            continue
        other = seen_users.setdefault(line.username.lower(), line.key)
        if other != line.key:
            problems.append(
                f"Username '{line.username}' is used by both {other} and {line.key} "
                "-- each line needs its own login"
            )

    seen_gateways = {}
    for line in lines.values():
        for gw in line.gateways:
            other = seen_gateways.setdefault((gw.host, gw.port), line.key)
            if other != line.key:
                problems.append(
                    f"Gateway {gw.address} is used by both {other} and {line.key} "
                    "-- each line must have its own gateways"
                )
    return lines


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
def _parse_users(env, lines, problems) -> dict:
    """Every line's own login (one line, operator) plus any extra USERS."""
    users = {}
    for line in lines.values():
        if line.username and line.password:
            users[line.username.lower()] = User(
                line.username, line.password, (line.key,), "operator"
            )

    raw = _get(env, "USERS")
    if not raw:
        return users

    for name in (n.strip().upper() for n in raw.split(",")):
        if not name:
            continue
        if not KEY_RE.match(name):
            problems.append(f"USERS: '{name}' may only contain letters, digits and _")
            continue
        p = f"USER_{name}_"
        username = _get(env, p + "USERNAME")
        password = _get(env, p + "PASSWORD")
        raw_lines = _get(env, p + "LINES")
        role = (_get(env, p + "ROLE") or "operator").lower()

        if not username:
            problems.append(f"{p}USERNAME is required")
        if not password:
            problems.append(f"{p}PASSWORD is required")
        if role not in ROLES:
            problems.append(f"{p}ROLE: '{role}' must be one of {', '.join(ROLES)}")
            role = "operator"

        granted = []
        if not raw_lines:
            problems.append(f"{p}LINES is required (line keys, or ALL)")
        elif raw_lines.strip().upper() == "ALL":
            granted = list(lines)
        else:
            for lk in (x.strip().upper() for x in raw_lines.split(",")):
                if not lk:
                    continue
                if lk not in lines:
                    problems.append(f"{p}LINES: '{lk}' is not a line listed in LINES")
                elif lk not in granted:
                    granted.append(lk)
            if not granted:
                problems.append(f"{p}LINES: no valid lines")

        if username and password and granted:
            if username.lower() in users:
                problems.append(
                    f"Username '{username}' (USER_{name}) is already used by another login"
                )
            else:
                users[username.lower()] = User(username, password, tuple(granted), role)
    return users


# ---------------------------------------------------------------------------
# Process settings
# ---------------------------------------------------------------------------
def _float_setting(env, var, default, bounds, problems):
    raw = _get(env, var)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        problems.append(f"{var}: '{raw}' is not a number")
        return default
    lo, hi = bounds
    if not (lo <= value <= hi):
        problems.append(f"{var}: {value:g} is outside the allowed range {lo:g}-{hi:g}")
        return default
    return value


def _parse_settings(env, lines, problems) -> Settings:
    mode = (_get(env, "POLLING_MODE") or "line_specific").lower()
    if mode not in POLLING_MODES:
        problems.append(f"POLLING_MODE: '{mode}' must be one of {', '.join(POLLING_MODES)}")
        mode = "line_specific"

    raw = _get(env, "POLL_LINES")
    poll_lines = set()
    if raw and raw.strip().upper() == "ALL":
        poll_lines = set(lines)
    elif raw:
        for k in (x.strip().upper() for x in raw.split(",")):
            if not k:
                continue
            if k not in lines:
                problems.append(f"POLL_LINES: '{k}' is not a line listed in LINES")
            else:
                poll_lines.add(k)
    elif mode == "centralized":
        poll_lines = set(lines)       # centralized with no list = every line
    else:
        problems.append(
            "POLL_LINES is required when POLLING_MODE=line_specific -- name the line(s) "
            "this PC is wired to, e.g. POLL_LINES=CHOCOLATE"
        )

    timeout = _float_setting(env, "MODBUS_TIMEOUT_SEC", 5.0, (0.5, 60), problems)
    retries = _int_setting(env, "MODBUS_READ_RETRIES", 0, (0, 5), problems)
    b_init = _float_setting(env, "MODBUS_BACKOFF_INITIAL_SEC", 5.0, (0.5, 600), problems)
    b_max = _float_setting(env, "MODBUS_BACKOFF_MAX_SEC", 60.0, (0.5, 3600), problems)
    if b_max < b_init:
        problems.append("MODBUS_BACKOFF_MAX_SEC must not be smaller than MODBUS_BACKOFF_INITIAL_SEC")
    pause = _float_setting(env, "POLL_CYCLE_PAUSE_SEC", 2.0, (0.0, 600), problems)
    stale = _float_setting(env, "STALE_AFTER_SEC", 30.0, (1, 3600), problems)
    lease = _int_setting(env, "POLL_LEASE_PORT", 47653, (1024, 65535), problems)

    return Settings(
        polling_mode=mode,
        poll_lines=frozenset(poll_lines),
        modbus_timeout_sec=timeout,
        read_retries=retries,
        backoff_initial_sec=b_init,
        backoff_max_sec=b_max,
        cycle_pause_sec=pause,
        stale_after_sec=stale,
        lease_port=lease,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def load_config(env: Mapping[str, str]) -> Config:
    """Lines, users and polling settings, validated together so that one
    restart reports every mistake in .env."""
    problems = []
    lines = _parse_lines(env, problems)
    users = _parse_users(env, lines, problems)
    settings = _parse_settings(env, lines, problems)
    if problems:
        raise ConfigError(problems)
    return Config(lines=lines, users=users, settings=settings)


def load_config_from_environment() -> Config:
    return load_config(os.environ)


def warnings_for(config: Config) -> list:
    """Non-fatal things worth showing in the log at startup."""
    out = []
    for line in config.lines.values():
        if line.upper_limit <= 0:
            out.append(
                f"Line {line.key}: LINE_{line.key}_UPPER_LIMIT is 0 -- every test on this "
                "line will FAIL until a real limit is set."
            )
        if line.subnet is None:
            out.append(f"Line {line.key}: no LINE_{line.key}_SUBNET set -- addresses are not validated.")
    s = config.settings
    if s.polling_mode == "centralized" and len(s.poll_lines) > 1:
        out.append(
            "POLLING_MODE=centralized: this PC polls several lines, so it must have a "
            "verified route to every one of those line networks."
        )
    return out


def describe(config: Config) -> str:
    """A readable summary of what .env configures (never includes passwords)."""
    out = []
    s = config.settings
    out.append(f"Polling mode : {s.polling_mode}")
    out.append(f"This PC polls: {', '.join(sorted(s.poll_lines)) or '(nothing)'}")
    out.append("")
    total_g = total_u = 0
    for line in config.lines.values():
        total_g += len(line.gauge_ids)
        total_u += sum(1 for g in line.gateways if g.enabled)
        net = line.subnet or "no subnet configured"
        out.append(f"{line.key}  \"{line.label}\"  {len(line.gauge_ids)}/{line.gauge_count} gauges enabled  [{net}]")
        out.append(f"    login '{line.username}'  upper limit {line.upper_limit} mbar  register map {line.register_map}")
        if line.pc_line_ip or line.router_ip or line.company_pc_ip:
            out.append(f"    PC {line.pc_line_ip or '-'}  router {line.router_ip or '-'}  company PC {line.company_pc_ip or '-'}")
        for g in line.gateways:
            state = "" if g.enabled else "   (DISABLED)"
            out.append(f"    {g.usr_id:<22} {g.address:<22} gauges {g.first}-{g.last}{state}")
    out.append("")
    out.append(f"Total: {len(config.lines)} lines, {total_g} gauges, {total_u} USR devices")
    out.append("Logins: " + ", ".join(
        f"{u.username} ({u.role}: {', '.join(u.lines)})" for u in config.users.values()))
    return "\n".join(out)


if __name__ == "__main__":
    # `python lines_config.py` checks .env without starting the application.
    import sys

    try:
        _config = load_config_from_environment()
    except ConfigError as exc:
        print(exc)
        sys.exit(1)
    print(describe(_config))
    for _w in warnings_for(_config):
        print("WARNING:", _w)
    print("\n.env is valid.")
