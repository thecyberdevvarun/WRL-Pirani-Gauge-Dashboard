-- OPTIONAL. Speeds up "latest test per line and gauge", which the application
-- runs every 2 seconds across all lines, and the per-line report filters.
-- Test on a copy first; creating an index briefly locks the table, so run it
-- outside production hours if the table is large.

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE  name = 'IX_pirani_test_header_line_gauge_start'
      AND  object_id = OBJECT_ID('pirani_test_header')
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_pirani_test_header_line_gauge_start
        ON pirani_test_header (line_name, gauge_id, start_time DESC)
        INCLUDE (serial_no, final_result);
END
GO

-- ROLLBACK (removes only the index; no data is touched):
-- DROP INDEX IX_pirani_test_header_line_gauge_start ON pirani_test_header;
