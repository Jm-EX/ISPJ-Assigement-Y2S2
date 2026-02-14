import psycopg
from psycopg.rows import dict_row
from datetime import datetime
from flask import current_app, g, request
import os


def get_db():
    if "db" not in g:
        # Check if DATABASE_URL is provided (Render PostgreSQL)
        database_url = os.environ.get("DATABASE_URL")
        if database_url:
            g.db = psycopg.connect(database_url, row_factory=dict_row)
            g.db.autocommit = True
        else:
            # Fallback to individual config values for local development
            g.db = psycopg.connect(
                host=current_app.config["MYSQL_HOST"],
                port=current_app.config["MYSQL_PORT"],
                user=current_app.config["MYSQL_USER"],
                password=current_app.config["MYSQL_PASSWORD"],
                dbname=current_app.config["MYSQL_DATABASE"],
                row_factory=dict_row
            )
            g.db.autocommit = True
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_chat_db(app):
    """
    Initialize chat database.
    Note: Table creation should be done via SQL file: create_chat_messages_table.sql
    This function just verifies the table exists.
    """
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Check if chat_messages table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'chat_messages'
            );
        """)
        
        table_exists = cursor.fetchone()[0]
        
        if table_exists:
            print("Chat messages table exists and is ready")
        else:
            print("WARNING: chat_messages table not found. Please run create_chat_messages_table.sql")
            
    except Exception as e:
        print(f"Error checking chat database: {e}")
        print("Please ensure create_chat_messages_table.sql has been executed")


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
        
        print(f"Chat message saved: {username} ({sender_type}) in {room}")
        return True
    except Exception as e:
        print(f"Error saving chat message: {e}")
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
    print(f"Cleaned up {deleted_count} old messages (older than {hours} hours)")
    return deleted_count
