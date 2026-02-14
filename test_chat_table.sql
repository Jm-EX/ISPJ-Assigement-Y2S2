-- Test script to check if chat table exists and works
-- Run this in your PostgreSQL database to verify setup

-- Check if table exists
SELECT table_name, table_type 
FROM information_schema.tables 
WHERE table_schema = 'public' AND table_name = 'chat_messages';

-- If table exists, show its structure
\d chat_messages

-- Test inserting a sample message
INSERT INTO chat_messages (session_id, user_id, username, message, sender_type, room, admin_read)
VALUES ('test_session', NULL, 'Test User', 'Hello, this is a test message', 'customer', 'default', FALSE)
RETURNING *;

-- Test querying messages
SELECT * FROM chat_messages ORDER BY timestamp DESC LIMIT 5;

-- Test the stats functions
SELECT 
    COUNT(*) as total_messages,
    COUNT(*) FILTER (WHERE admin_read = FALSE) as unread_messages,
    COUNT(DISTINCT room) as active_rooms
FROM chat_messages;

-- Clean up test data
DELETE FROM chat_messages WHERE session_id = 'test_session';
