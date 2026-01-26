-- Migration to add role/permissions columns and create rooms/bookings tables
-- Run this on existing databases: mysql -u root -p ispj_hotel < migration_add_permissions_and_rooms.sql

-- Add role and permissions columns to users table if they don't exist
-- Check and add role column
SET @dbname = DATABASE();
SET @tablename = 'users';
SET @columnname = 'role';
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE
      (table_name = @tablename)
      AND (table_schema = @dbname)
      AND (column_name = @columnname)
  ) > 0,
  'SELECT 1',
  'ALTER TABLE users ADD COLUMN role VARCHAR(50) DEFAULT NULL'
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- Check and add permissions column
SET @columnname = 'permissions';
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE
      (table_name = @tablename)
      AND (table_schema = @dbname)
      AND (column_name = @columnname)
  ) > 0,
  'SELECT 1',
  'ALTER TABLE users ADD COLUMN permissions TEXT DEFAULT NULL'
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- Create rooms table
CREATE TABLE IF NOT EXISTS rooms (
    id INT AUTO_INCREMENT PRIMARY KEY,
    room_type VARCHAR(100) NOT NULL,
    total_count INT NOT NULL DEFAULT 0,
    available_count INT NOT NULL DEFAULT 0,
    occupied_count INT NOT NULL DEFAULT 0,
    cleaning_count INT NOT NULL DEFAULT 0,
    maintenance_count INT NOT NULL DEFAULT 0,
    price_per_night DECIMAL(10, 2) NOT NULL,
    updated_at DATETIME NOT NULL
);

-- Create bookings table
CREATE TABLE IF NOT EXISTS bookings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    guest_name VARCHAR(255) NOT NULL,
    guest_email VARCHAR(255) NOT NULL,
    guest_phone VARCHAR(50),
    room_type VARCHAR(100) NOT NULL,
    check_in_date DATE NOT NULL,
    check_out_date DATE NOT NULL,
    num_guests INT NOT NULL DEFAULT 1,
    total_price DECIMAL(10, 2) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    special_requests TEXT,
    notes TEXT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    created_by INT,
    FOREIGN KEY (created_by) REFERENCES users (id)
);

-- Create guest_profiles table
CREATE TABLE IF NOT EXISTS guest_profiles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    guest_name VARCHAR(255) NOT NULL,
    guest_email VARCHAR(255) NOT NULL UNIQUE,
    guest_phone VARCHAR(50),
    preferences TEXT,
    notes TEXT,
    total_bookings INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

-- Insert sample room types (optional - adjust as needed)
INSERT INTO rooms (room_type, total_count, available_count, occupied_count, cleaning_count, maintenance_count, price_per_night, updated_at)
VALUES 
    ('Standard', 20, 20, 0, 0, 0, 100.00, NOW()),
    ('Deluxe', 15, 15, 0, 0, 0, 150.00, NOW()),
    ('Suite', 10, 10, 0, 0, 0, 250.00, NOW()),
    ('Presidential Suite', 5, 5, 0, 0, 0, 500.00, NOW())
ON DUPLICATE KEY UPDATE room_type=room_type;
