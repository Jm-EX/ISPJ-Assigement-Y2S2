import psycopg
from psycopg.rows import dict_row
from datetime import datetime
from flask import current_app, g
import os

def get_db():
    """Get database connection"""
    if 'db' not in g:
        g.db = psycopg.connect(
            host=current_app.config['DB_HOST'],
            database=current_app.config['DB_NAME'],
            user=current_app.config['DB_USER'],
            password=current_app.config['DB_PASSWORD'],
            port=current_app.config['DB_PORT']
        )
        g.db.row_factory = dict_row
    return g.db

def close_db():
    """Close database connection"""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_chat_db():
    """Initialize chat database tables"""
    db = get_db()
    cursor = db.cursor()
    
    # Create chat_messages table
    cursor.execute("""
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
        )
    """)
    
    # Create indexes for better performance
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id ON chat_messages(user_id)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_chat_messages_timestamp ON chat_messages(timestamp)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_chat_messages_room ON chat_messages(room)
    """)
    
    db.commit()
    print("Chat database initialized successfully")

def save_chat_message(session_id, user_id, username, user_email, message, sender_type, room):
    """Save a chat message to database"""
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO chat_messages 
            (session_id, user_id, username, user_email, message, sender_type, room)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (session_id, user_id, username, user_email, message, sender_type, room))
        
        db.commit()
        print(f"Chat message saved: {username} ({sender_type}) in {room}")
        return True
    except Exception as e:
        print(f"Error saving chat message: {e}")
        db.rollback()
        return False

def get_chat_history(session_id=None, user_id=None, room=None, limit=50):
    """Get chat history for a user"""
    db = get_db()
    cursor = db.cursor()
    
    query = """
        SELECT cm.*, u.username as user_username, u.email as user_email
        FROM chat_messages cm
        LEFT JOIN users u ON cm.user_id = u.id
        WHERE 1=1
    """
    params = []
    
    if session_id:
        query += " AND cm.session_id = %s"
        params.append(session_id)
    
    if user_id:
        query += " AND cm.user_id = %s"
        params.append(user_id)
    
    if room:
        query += " AND cm.room = %s"
        params.append(room)
    
    query += " ORDER BY cm.timestamp ASC LIMIT %s"
    params.append(limit)
    
    cursor.execute(query, params)
    return cursor.fetchall()

def get_recent_messages(room=None, hours=24, limit=100):
    """Get recent messages from the last N hours"""
    db = get_db()
    cursor = db.cursor()
    
    query = """
        SELECT cm.*, u.username as user_username, u.email as user_email
        FROM chat_messages cm
        LEFT JOIN users u ON cm.user_id = u.id
        WHERE cm.timestamp >= NOW() - INTERVAL '%s hours'
    """ % hours
    
    params = []
    
    if room:
        query += " AND cm.room = %s"
        params.append(room)
    
    query += " ORDER BY cm.timestamp DESC LIMIT %s"
    params.append(limit)
    
    cursor.execute(query, params)
    return cursor.fetchall()

def get_active_chat_sessions(hours=24):
    """Get active chat sessions from the last N hours"""
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT DISTINCT ON (session_id) 
            session_id,
            user_id,
            username,
            user_email,
            room,
            MAX(timestamp) as last_message_time,
            COUNT(*) FILTER (WHERE admin_read = FALSE AND sender_type != 'admin') as unread_count
        FROM chat_messages 
        WHERE timestamp >= NOW() - INTERVAL '%s hours'
        GROUP BY session_id, user_id, username, user_email, room
        ORDER BY last_message_time DESC
    """ % hours)
    
    return cursor.fetchall()

def mark_messages_as_read(session_id=None, room=None):
    """Mark messages as read by admin"""
    db = get_db()
    cursor = db.cursor()
    
    query = "UPDATE chat_messages SET admin_read = TRUE WHERE admin_read = FALSE"
    params = []
    
    if session_id:
        query += " AND session_id = %s"
        params.append(session_id)
    
    if room:
        query += " AND room = %s"
        params.append(room)
    
    cursor.execute(query, params)
    db.commit()
    print(f"Messages marked as read for session: {session_id}, room: {room}")

def cleanup_old_messages(hours=48):
    """Delete messages older than N hours"""
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        DELETE FROM chat_messages 
        WHERE timestamp < NOW() - INTERVAL '%s hours'
    """ % hours)
    
    deleted_count = cursor.rowcount
    db.commit()
    print(f"Cleaned up {deleted_count} old messages (older than {hours} hours)")
    return deleted_count
