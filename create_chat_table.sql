-- Chat messages table for admin dashboard (PostgreSQL)
CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,           -- Socket.IO session ID
    user_id INTEGER,                     -- User ID if logged in
    username TEXT NOT NULL,               -- Display name
    message TEXT NOT NULL,                 -- Message content
    sender_type TEXT NOT NULL,             -- 'customer', 'admin', or 'ai'
    room TEXT NOT NULL,                   -- Chat room identifier
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    admin_read BOOLEAN DEFAULT FALSE,        -- Whether admin has read this message
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_chat_messages_room ON chat_messages(room);
CREATE INDEX IF NOT EXISTS idx_chat_messages_timestamp ON chat_messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_chat_messages_admin_read ON chat_messages(admin_read);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id);

-- Add comments for documentation
COMMENT ON TABLE chat_messages IS 'Stores all chat messages from customer service system';
COMMENT ON COLUMN chat_messages.session_id IS 'Socket.IO session identifier';
COMMENT ON COLUMN chat_messages.user_id IS 'Foreign key to users table, null for anonymous/AI';
COMMENT ON COLUMN chat_messages.username IS 'Display name of the sender';
COMMENT ON COLUMN chat_messages.message IS 'Message content';
COMMENT ON COLUMN chat_messages.sender_type IS 'Type: customer, admin, or ai';
COMMENT ON COLUMN chat_messages.room IS 'Chat room identifier';
COMMENT ON COLUMN chat_messages.timestamp IS 'When the message was sent';
COMMENT ON COLUMN chat_messages.admin_read IS 'Whether admin has read this message';
