-- Add active_sessions table for session tracking with risk scoring
CREATE TABLE IF NOT EXISTS active_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    session_token VARCHAR(255) NOT NULL UNIQUE,
    ip_address VARCHAR(255),
    user_agent TEXT,
    device_fingerprint VARCHAR(255),
    country VARCHAR(100),
    risk_score INT NOT NULL DEFAULT 0,
    is_new_device TINYINT NOT NULL DEFAULT 0,
    is_new_country TINYINT NOT NULL DEFAULT 0,
    failed_attempts INT NOT NULL DEFAULT 0,
    last_activity DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id)
);
