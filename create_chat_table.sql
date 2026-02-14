-- Chat messages table for admin dashboard
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,           -- Socket.IO session ID
    user_id INTEGER,                     -- User ID if logged in
    username TEXT NOT NULL,               -- Display name
    message TEXT NOT NULL,                 -- Message content
    sender_type TEXT NOT NULL,             -- 'customer', 'admin', or 'ai'
    room TEXT NOT NULL,                   -- Chat room identifier
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    admin_read BOOLEAN DEFAULT FALSE,        -- Whether admin has read this message
    FOREIGN KEY (user_id) REFERENCES users (id)
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_chat_messages_room ON chat_messages(room);
CREATE INDEX IF NOT EXISTS idx_chat_messages_timestamp ON chat_messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_chat_messages_admin_read ON chat_messages(admin_read);
