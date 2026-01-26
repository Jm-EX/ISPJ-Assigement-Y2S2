-- Add previous_failed_attempts column to active_sessions table
-- This preserves the failed attempt count even after reset on successful login

SET @column_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'ispj_hotel'
    AND TABLE_NAME = 'active_sessions'
    AND COLUMN_NAME = 'previous_failed_attempts'
);

SET @sql = IF(@column_exists = 0,
    'ALTER TABLE active_sessions ADD COLUMN previous_failed_attempts INT NOT NULL DEFAULT 0 AFTER failed_attempts',
    'SELECT "Column previous_failed_attempts already exists" AS message'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
