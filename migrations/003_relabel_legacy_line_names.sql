-- TEMPLATE. Use only if 001_verify_history.sql query (2) shows tests saved under
-- a line_name that is not one of your line keys, and you want them to appear
-- under a line. Which line they belong to is YOUR decision: this script cannot
-- tell. Nothing is committed until you change ROLLBACK to COMMIT.
--
-- 0. Take a full database backup first.
-- 1. Edit the two values below.
-- 2. Run, read the "rows changed" count, then change ROLLBACK to COMMIT and run again.

DECLARE @old_name NVARCHAR(100) = N'DEFAULT';      -- the legacy value found by query (2)
DECLARE @new_key  NVARCHAR(100) = N'FREEZER';      -- the line key it should become

-- A copy of exactly the rows being changed, so the change can be reversed.
IF OBJECT_ID('pirani_line_name_backup') IS NULL
    CREATE TABLE pirani_line_name_backup (
        test_id         UNIQUEIDENTIFIER NOT NULL,   -- adjust the type to match pirani_test_header.test_id
        old_line_name   NVARCHAR(100)    NULL,
        changed_at      DATETIME         NOT NULL DEFAULT GETDATE()
    );

BEGIN TRANSACTION;

INSERT INTO pirani_line_name_backup (test_id, old_line_name)
SELECT test_id, line_name FROM pirani_test_header WHERE line_name = @old_name;

UPDATE pirani_test_header SET line_name = @new_key WHERE line_name = @old_name;
SELECT @@ROWCOUNT AS rows_changed;

ROLLBACK TRANSACTION;      -- <-- change to COMMIT TRANSACTION once the count looks right

-- TO UNDO AFTER A COMMIT:
-- UPDATE h SET h.line_name = b.old_line_name
-- FROM pirani_test_header h JOIN pirani_line_name_backup b ON b.test_id = h.test_id;
