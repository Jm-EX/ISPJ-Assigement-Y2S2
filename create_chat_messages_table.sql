-- Create chat_messages table for persistent chat history
CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL,
    user_id INTEGER,
    username VARCHAR(255) NOT NULL,
    user_email VARCHAR(255),
    message TEXT NOT NULL,
    sender_type VARCHAR(50) NOT NULL, -- 'user', 'admin', 'ai', 'system'
    room VARCHAR(100) NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    admin_read BOOLEAN NOT NULL DEFAULT FALSE,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id ON chat_messages(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_timestamp ON chat_messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_chat_messages_room ON chat_messages(room);
CREATE INDEX IF NOT EXISTS idx_chat_messages_admin_read ON chat_messages(admin_read);

-- Add comment to explain the table
COMMENT ON TABLE chat_messages IS 'Stores all chat messages for AI and concierge support with persistent history';
