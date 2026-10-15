# Test results

Run on 12 October 2026 against the finished code. **Nothing was tested on real
equipment, a real SQL Server, or in a real browser** — see "Not tested" below.
Hardware tests are tracked in `docs/DEPLOYMENT.md` section 8 and are all PENDING.

## Automated tests (`python -m pytest tests`)

**161 passed, 0 failed.**

| File | Tests | Covers |
|---|---:|---|
| `test_lines_config.py` | 40 | Loading and validating `.env`: all four lines; gauge-to-USR coverage and overlaps; stable USR ids; disabled USRs/gauges; subnet, `.0`/`.255`, PC/router clashes, duplicate IPs, overlapping line networks; users and roles; polling settings. Includes an acceptance test that the shipped `.env` / `.env.example` match the documented plant exactly (4 lines, **117 gauges, 23 USRs**, every address and slave range). |
| `test_app.py` | 83 | Login and sessions; multi-line users and the line chooser; unauthorised line selection; every data endpoint refusing anonymous access; **line isolation** (fixtures, live values, reports, trend, PDF, stats, settings, diagnostics all scoped to the session's line, a client-supplied line ignored, report cache not shared across lines); same gauge number on different lines; start/stop/IN-OUT auto-stop; admin-only connection test and its refusal of foreign hosts; line-specific mode; stale/failed readings never shown as current; logins/switches/logout not touching workers. |
| `test_polling.py` | 19 | The polling service against simulated USRs: one worker per USR; **idempotent start**; one failed USR not stopping others; a slow USR not delaying others; per-gauge failures leaving the USR connected; recovery; connection lost mid-poll; exponential back-off with a cap; bounded retries; line-specific mode; disabled USRs/gauges; freshness over time; graceful stop and restart; log output (once per change, with line/usr/gauge/slave); the single-owner lease. |
| `test_register_maps.py` | 12 | Every Modbus outcome classified: success, timeout, connection error, invalid response, Modbus exception, decode error; scaling. |
| `test_test_runner.py` | 7 | Test lifecycle, including two lines running "gauge 1" at once without colliding. |

### How much to trust them

* **Mutation check.** I deliberately broke the line-isolation logic in nine places (report cache key, report filter, live lookup, trusting a client line, host allow-list, runner key, fixtures, trend, PDF, …). Each break made a test fail. One did not at first (trend hard-coded to one line); the tests were strengthened and it now fails as it should.
* **Flakiness.** Timing-based tests were stress-run in parallel under CPU load. Two races in *my new tests* were found and fixed. A third was already in the original `test_test_runner.py` (it failed 23 of 72 runs on the original code; a background thread could write into the next test's results); it is fixed (0 of 72). Final result: **the whole suite, 24 runs in parallel, 0 failures**.
* **Hermetic.** Tests ignore your real `.env` and the surrounding shell; they pass with a deliberately hostile environment.

## End-to-end against simulated USRs (`python tools/simulated_plant_e2e.py`)

**23 checks, all passed.** Real Modbus TCP traffic between the real application and fake USR devices on localhost, fully offline. Verified: gauge 1 on two lines reads from its own USR; an **offline USR** shows *Disconnected / Error / No data* while every other USR keeps updating; a **dead gauge** behind a healthy USR shows *Timeout* with its USR still *Connected* and neighbours unaffected; the USR **coming back** is picked up automatically; a real test runs and logs readings through the right USR; a stale reading is not shown as current; a multi-line admin must choose a line, sees only that line, and switching changes scope; logins/switching leave the 3 workers untouched; operator refused / admin allowed for the connection test; shutdown stops all workers and frees the lease.

Also checked with real separate processes: with one instance polling, a second instance refuses to poll (logs why); after the first exits the lease is free again.

## Frontend

* `npm run build`: succeeds. `npm run lint`: 0 errors, 4 warnings (all of the same kind that existed before this work; one fewer than the original).
* **UI behaviour check — 27 checks passed.** The real React app was run in a simulated browser (jsdom) against a mock of the API (one-off script, not included). Covered: login and wrong-password message; single-line user goes straight to the dashboard; multi-line user sees the line chooser and no data is requested before choosing; choosing, switching and re-fetching the line's configuration; gauge details show USR id/address/slave ID and Live / Stale / No data badges; a stale gauge shows "last known … (stale)" and a missing reading shows "—" (not `0.000`); Settings shows the network and per-USR status; Test button only for admins on a line this PC polls; warning for a line this PC does not poll.
* Fixed along the way: the gauge panel used `Number(null)`, which is `0`, so a gauge with no reading would have displayed and charted as `0.000`; and the gauge-id selector rebuilt its array on every store update, re-rendering consumers each time.

## Not tested

| What | Why it matters |
|---|---|
| Real USR devices and gauges | Everything above uses simulators. Real timing, RS485 behaviour and USR connection limits are unproven. |
| SQL Server | The database code runs against fakes only. The queries are new/changed for per-line filtering (`h.line_name = ?`, latest test per line and gauge); they have not been executed on SQL Server. The migration scripts have not been run. |
| Real browsers and screens | jsdom has no layout engine. How the gauge ring looks at 54 gauges on a real screen, and touch behaviour, are unseen. |
| Windows | Developed and tested on Linux. The polling lease, `start_app.bat` and the firewall steps have not been run on Windows. |
| Network isolation | Subnets and routing are checked only as configuration values; whether the real network isolates the lines is a site check (`DEPLOYMENT.md` section 3). |
| Long runs | No multi-hour or multi-day soak test. |
