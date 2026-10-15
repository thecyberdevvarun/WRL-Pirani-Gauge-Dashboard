# Database migrations

**None of these scripts have been run.** They were written without access to
your SQL Server, so review them and run them in a **test copy** of the database
first. Back up before running anything that changes data.

The application needs **no schema or data migration** to run the four-line
version: the existing tables already identify a test by `line_name` + `gauge_id`,
and those are exactly the keys the application now uses. Nothing here is
required; run them only if you need what they do.

| Script | Changes data? | Purpose |
|---|---|---|
| `001_verify_history.sql` | No (read-only) | Run **before and after** deploying. Counts tests per line/gauge and finds history the app will not show. |
| `002_add_line_gauge_index.sql` | Adds an index | Speeds up the lookups the app now does per (line, gauge). Optional. Has a rollback. |
| `003_relabel_legacy_line_names.sql` | Yes (template) | Only if old tests were saved under a `line_name` that is not one of your line keys. Backs up first; ends in `ROLLBACK` until you change it. |

## Why there are no new gauge / reading tables

A gauge's identity is `(line_name, gauge_id)` = (line key, slave ID). It is
stored on every test header (and, through `test_id`, every logged reading), so
history stays attached to the right gauge when an IP address changes: the IP
lives only in `.env`, never in the data.

Live readings are held in memory and written to `pirani_test_log` only while a
test is running, as before. Recording every gauge every few seconds would add
roughly 117 gauges × 30 reads/min ≈ 5 million rows a day, so it was not added.
If you want continuous history, decide the retention first, then it can be
added as a separate table.

## Rolling back a deployment

The application changes are code and `.env` only: restore the previous
application folder and `.env`. Data written by the new version (tests with
`line_name` = the line key) remains valid for the old version as long as the
old version's lines use the same keys.
