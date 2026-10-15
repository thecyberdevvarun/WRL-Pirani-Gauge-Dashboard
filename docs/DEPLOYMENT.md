# Deployment, network and rollback guide

Four production lines, 117 gauges, 23 USR devices. Everything described here
is configured in `.env`; check an edit without starting the app with
`python lines_config.py`.

> **Status.** The software has been tested against simulated USR devices only.
> **No test has been run on the real equipment**, and the IP addresses below
> are the *proposed* ones from the requirements document. Both are listed as
> pending in sections 7 and 8.

## 1. How it fits together

```
 Browsers (company network 10.100.x.x)  ──►  http://<line PC company IP>:5000
                                                   │
                       ┌───────────────────────────┴───────────────┐
                       │  Line PC  (runs this application)         │
   company NIC ────────┤   • serves the dashboard + API            │
                       │   • polls ONLY its own line's USRs        │──► SQL Server 10.100.95.160
   line NIC ───────────┤   • 192.168.N.1 / 24                      │      (shared by all PCs)
                       └─────────────────┬─────────────────────────┘
                                         │ line subnet 192.168.N.0/24
                          router .2 ─────┴──── USR .3 … USR .k  ──► RS485 ──► Pirani gauges
```

* **Each line PC runs the same application and the same `.env`.** The only
  setting that differs between PCs is `POLL_LINES` (section 4).
* The database is shared, so a line PC can still show **test results** for the
  other lines. It cannot show **live readings** or **start tests** for them,
  because it has no network route to their USRs. The dashboard says so.
* A gauge is identified by **line + slave ID** (the slave ID is the gauge number
  within its line). A USR's identity is its **position in the line's list**
  (`freezer-usr-03`), not its IP address, so changing an address never
  changes history.

## 2. IP plan (proposed — validate before applying)

Network addresses end in `.0` and broadcast addresses in `.255`; neither may be
given to a device. The application refuses to start if a USR, PC or router
address is one of those, is outside the line's subnet, or duplicates another
address.

| Line | Subnet | PC (line side) | Router | USRs | Gauges |
|---|---|---|---|---|---|
| Freezer | 192.168.1.0/24 | 192.168.1.1 | 192.168.1.2 | .3 – .13 (11) | 54 |
| Chocolate | 192.168.2.0/24 | 192.168.2.1 | 192.168.2.2 | .3 – .5 (3) | 18 |
| Visi Cooler | 192.168.3.0/24 | 192.168.3.1 | 192.168.3.2 | .3 – .8 (6) | 30 |
| SUS | 192.168.4.0/24 | 192.168.4.1 | 192.168.4.2 | .3 – .5 (3) | 15 |

| Line | Company-network PC address |
|---|---|
| Freezer | 10.100.95.193 |
| Chocolate | 10.100.99.59 |
| Visi Cooler | 10.100.99.214 |
| SUS | **not yet confirmed — left blank in `.env`** |

USR layout (`GATEWAYS=host:port:first-last`): Freezer USRs 1–10 carry 5 gauges
each and USR 11 carries gauges 51–54; Chocolate 6 per USR; Visi Cooler and SUS
5 per USR. The full list is printed by `python lines_config.py`.

Reserve `.1`–`.2` for the PC and router and `.3` upward for USRs; keep a
written allocation list for any future device (each /24 has 254 usable addresses).

## 3. Network isolation and routing checklist

The application does not create isolation; the network must. Confirm each item
on site and tick it off.

- [ ] Each line PC has **two** network interfaces: company and line side. The line-side interface has the address above, a `255.255.255.0` mask and **no default gateway** (a second default gateway makes Windows route company traffic the wrong way).
- [ ] The company-side address is **not changed** by this work.
- [ ] IP forwarding / routing between the two interfaces on the line PC is **off** (Windows: `IPEnableRouter = 0`; no "Internet Connection Sharing"), and the router does not bridge the four line subnets together. *Different subnets are not isolated if something routes or bridges them.*
- [ ] Confirm whether each "router" is a plain switch, a router, or a NAT device. If it NATs/port-forwards, list the forwarded ports and use them in `GATEWAYS` (the same host with different ports is allowed).
- [ ] No overlapping routes between production networks (`route print` on each PC).
- [ ] Windows Firewall on each line PC allows: **inbound TCP 5000** from the company network only; **outbound TCP 502** to that line's USRs only; **outbound TCP 1433** to `10.100.95.160`.
- [ ] Before powering the USRs: ping-sweep the subnet to find **duplicate or unexpected addresses**; assign each USR's address and confirm exactly one device answers.
- [ ] From the line PC: every USR address is reachable on TCP 502 (`Test-NetConnection 192.168.2.3 -Port 502`).
- [ ] Write down the final routing and firewall rules next to this document.

## 4. Polling mode and per-PC settings

| Mode | Meaning | Use when |
|---|---|---|
| `line_specific` (default) | This PC polls only the lines in `POLL_LINES`. | Each line has its own PC on its own subnet (the planned layout). |
| `centralized` | This PC polls the lines in `POLL_LINES` (or all). | One host has a **verified** route to every line network. Do not enable it on trust. |

| PC | `POLLING_MODE` | `POLL_LINES` |
|---|---|---|
| Freezer PC (10.100.95.193) | `line_specific` | `FREEZER` |
| Chocolate PC (10.100.99.59) | `line_specific` | `CHOCOLATE` |
| Visi Cooler PC (10.100.99.214) | `line_specific` | `VISI_COOLER` |
| SUS PC (address to be confirmed) | `line_specific` | `SUS` |

Only **one** application instance may run per PC. A second instance fails to
obtain the polling lease (local port `POLL_LEASE_PORT`), logs an error, and
does not poll, so two copies can never double the traffic on a serial bus.

## 5. Logins

* Each line has its own login (`LINE_<KEY>_USERNAME/PASSWORD`): it opens that line directly.
* `USERS=` defines extra logins that may be authorised for several lines (`USER_X_LINES=FREEZER,SUS` or `ALL`). After signing in they choose a line and can switch later from the header.
* `USER_X_ROLE=admin` is needed for the Settings page's **Test connection** button (it opens a connection to a USR). Operators cannot use it.
* The server checks the line on **every** request. Changing a line name in a request cannot reach another line's readings, history or controls.
* Logging out ends only that browser's session; polling belongs to the backend and is unaffected by logins, refreshes or extra tabs.

## 6. Deployment procedure

Do **one line first** (suggested: Chocolate), then the rest.

1. **Back up** the application folder, the current `.env`, and the SQL Server database (full backup).
2. **Inventory** what exists today: IPs, ports, USR serial settings, register maps (section 8).
3. **Confirm the IP plan** with the network team; fix section 2 if it changes.
4. **Network:** configure the line PC's line-side interface, the router and each USR; walk through section 3.
5. Copy the new application files over the old folder (do not copy `.venv`, `.git`).
6. **`.env`:** set the line's `UPPER_LIMIT` (it is `0` = every test FAILS until set), passwords, `SECRET_KEY`, `POLL_LINES`, and the company-side PC address if needed. Run `python lines_config.py` until it prints `.env is valid.`
7. **Database:** in a test copy first, run `migrations/001_verify_history.sql`, record the numbers; optionally `002_add_line_gauge_index.sql`. See `migrations/README.md`.
8. `pip install -r requirements.txt`; run the automated tests: `python -m pytest tests`.
9. Start the application (`start_app.bat`). In the log expect, per USR: `polling worker started line=… usr=…`.
10. **Validate with known values** (section 8): compare a gauge on the dashboard with a reference reading.
11. **Monitor** for a shift (below), then roll out the next line.
12. Keep the backup and the old folder until all four lines have run cleanly.

**What to watch.** Settings page: every USR should be *Connected / Running* and gauges *Live*. Log lines worth alerting on (each carries `line=`, `usr=`, `gauge=`, `slave=`):

| Log text | Meaning |
|---|---|
| `USR unreachable` | A USR stopped answering; it is retried with growing delays (5 s → 60 s). Other USRs are unaffected. |
| `USR reconnected` | It came back. |
| `gauge read failed … status=timeout` | One gauge is not answering though its USR is. Logged once per change, not every cycle. |
| `gauge recovered` | It answers again. |
| `Another process on this PC already holds the polling lease` | A second instance is running; stop it. |
| `Database unavailable at startup` | SQL Server unreachable; the fixture list retries every 2 s. |

CPU, database writes and error counts: watch Task Manager and the SQL Server
activity for the first shift; there is no new load beyond the polling that
already existed (one TCP connection per USR, one read every ~2 s per gauge).

**Rollback.** Stop the application, restore the previous application folder and
`.env`, start it. No schema change was made unless you ran `002` (drop the index
with the command in that file) or `003` (undo with the command in that file).
Tests recorded by the new version use the line key as `line_name`; keep the same
keys in the old version's settings so they stay visible.

## 7. Unresolved items (nothing here has been guessed)

| Item | State | Who resolves it |
|---|---|---|
| SUS company-side PC address | **Blank.** The SUS PC's `.env` works without it; it is documentation only. | Network team |
| USR protocol and TCP port | Taken from the existing application: **Modbus TCP, port 502** (the old default). Confirm each USR is in its "Modbus TCP ↔ RTU" gateway mode. | Site engineer, USR configuration page |
| Serial settings behind each USR (baud, parity, stop bits) | **Not stored in the application** — they are set on the USR and the gauges, which only need to agree. Record them per USR. | Site engineer |
| Gauge register map and decoding | The existing map is reused unchanged: holding register 3, 2 registers, value = register 2 ÷ 1000, unit mbar. Confirm all four lines use the same gauge model; a different model is added as a new entry in `register_maps.py`. | Instrument engineer / datasheet |
| Polling interval and timeout | Existing values kept: 5 s timeout, 2 s pause between passes. **New** values to confirm: stale after 30 s, reconnect delay 5 s doubling to 60 s, retries 0. | Process owner |
| Network route and firewall design | Section 3 is a checklist, not a design. | Network team |
| Line PC polling vs one central host | Planned: one PC per line (`line_specific`). `centralized` exists but needs a verified route to all four networks. | Network team |
| `UPPER_LIMIT` per line | Placeholders of `0` (fail-safe). The old values are on the old Settings page. | Quality / process owner |

## 8. Hardware tests — all PENDING

None of these have been performed on real equipment. Record the date, who ran it and the result.

| # | Test | Status |
|---|---|---|
| 1 | Each USR reachable from its line PC on TCP 502 | PENDING |
| 2 | Read a known gauge: dashboard value equals a reference instrument | PENDING |
| 3 | Every gauge number maps to the right physical gauge (spot-check at least one per USR, including the last gauge of each line) | PENDING |
| 4 | Unplug one USR: its gauges go *Disconnected/No data* within one stale period; all other USRs keep updating | PENDING |
| 5 | Plug it back: it recovers by itself without restarting the app | PENDING |
| 6 | Disconnect one gauge's RS485 lead: only that gauge shows *Timeout*; its USR stays *Connected* | PENDING |
| 7 | Run a full test on a gauge of each line; compare the stored result and readings | PENDING |
| 8 | Two lines run a test on "gauge 1" at the same time; results land on the right line | PENDING |
| 9 | Start the app twice on one PC: the second instance refuses to poll | PENDING |
| 10 | Reboot the line PC: polling resumes with no operator action | PENDING |
| 11 | Duplicate-IP check and routing isolation (section 3) | PENDING |
| 12 | Load: all gauges of the Freezer line (54) polled for a full shift without growing delays | PENDING |

## 9. Where this deviates from the requirements document

* **Configuration lives in `.env`, not in database tables.** The document allows "structured configuration or database records". `.env` is what was asked for, it is validated at startup, and it needs no schema change. The trade-off: changes need a restart, and there is no in-app editor.
* **No continuous-readings table.** See `migrations/README.md` for the reasoning. Readings are stored while a test runs, as before; live values are in memory.
* **Identity is `(line, slave ID)`**, with the USR derived from the gauge number. The document suggests `UNIQUE(line_id, usr_id, slave_id)`; because slave IDs are unique across a whole line (gauge number = slave ID), the shorter key is equivalent and matches the stored history.
* **Line keys** are `FREEZER`, `CHOCOLATE`, `VISI_COOLER`, `SUS` (upper case, underscore) rather than `visi-cooler`. USR ids use hyphens (`visi-cooler-usr-01`).
* **"Test connection" is admin-only**, per the document's request to restrict device controls to authorised roles.
