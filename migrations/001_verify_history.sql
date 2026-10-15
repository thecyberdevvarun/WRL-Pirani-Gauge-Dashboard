-- READ-ONLY. Run before and after deployment and compare the results.

-- 1) Tests per line: keep these numbers; they must be identical after deployment.
SELECT line_name,
       COUNT(*)                  AS tests,
       COUNT(DISTINCT gauge_id)  AS gauges_used,
       MIN(start_time)           AS first_test,
       MAX(start_time)           AS last_test
FROM   pirani_test_header
GROUP  BY line_name
ORDER  BY line_name;

-- 2) History the application will NOT show: line_name matches none of the
--    configured line keys (edit the list to match LINES in .env).
SELECT line_name, COUNT(*) AS tests
FROM   pirani_test_header
WHERE  line_name IS NULL
   OR  line_name NOT IN ('FREEZER', 'CHOCOLATE', 'VISI_COOLER', 'SUS')
GROUP  BY line_name;

-- 3) Gauge numbers used per line that are higher than the line has gauges.
SELECT line_name, MAX(gauge_id) AS highest_gauge_id
FROM   pirani_test_header
GROUP  BY line_name;
-- Expected maximums: FREEZER 54, CHOCOLATE 18, VISI_COOLER 30, SUS 15.

-- 4) Readings whose test header is missing (should be 0).
SELECT COUNT(*) AS orphan_readings
FROM   pirani_test_log l
LEFT   JOIN pirani_test_header h ON h.test_id = l.test_id
WHERE  h.test_id IS NULL;

-- 5) Total rows, for a before/after comparison.
SELECT (SELECT COUNT(*) FROM pirani_test_header) AS headers,
       (SELECT COUNT(*) FROM pirani_test_log)    AS readings;
