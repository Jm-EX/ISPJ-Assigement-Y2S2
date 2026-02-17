-- Migration to add chat_messages table for chat persistence
-- Run this on Render PostgreSQL database

-- Create chat_messages table if it doesn't exist
CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL,
    user_id INTEGER,
    username VARCHAR(255) NOT NULL,
    user_email VARCHAR(255),
    message TEXT NOT NULL,
    sender_type VARCHAR(50) NOT NULL,
    room VARCHAR(100) NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    admin_read BOOLEAN NOT NULL DEFAULT FALSE,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id ON chat_messages(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_timestamp ON chat_messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_chat_messages_room ON chat_messages(room);
CREATE INDEX IF NOT EXISTS idx_chat_messages_admin_read ON chat_messages(admin_read);

-- Create dh_keys table for Diffie-Hellman key exchange if it doesn't exist
CREATE TABLE IF NOT EXISTS dh_keys (
    session_id VARCHAR(255) PRIMARY KEY,
    public_key TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL DEFAULT (NOW() + INTERVAL '24 hours')
);

-- Create index for dh_keys expiration
CREATE INDEX IF NOT EXISTS idx_dh_keys_expires_at ON dh_keys(expires_at);
