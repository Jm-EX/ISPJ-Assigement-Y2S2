import psycopg
from psycopg.rows import dict_row
from datetime import datetime, timedelta
from flask import current_app, g, request
from werkzeug.security import generate_password_hash
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


def init_db(app):
    # Check if DATABASE_URL is provided (Render PostgreSQL)
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        conn = psycopg.connect(database_url)
        conn.autocommit = True
    else:
        # For local development, connect to default postgres database first
        conn = psycopg.connect(
            host=app.config["MYSQL_HOST"],
            port=app.config["MYSQL_PORT"],
            user=app.config["MYSQL_USER"],
            password=app.config["MYSQL_PASSWORD"],
            dbname="postgres"
        )
        conn.autocommit = True
    try:
        cursor = conn.cursor()
        # PostgreSQL doesn't need CREATE DATABASE or USE statements when using DATABASE_URL
        if not database_url:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {app.config['MYSQL_DATABASE']}")
            conn.close()
            conn = psycopg.connect(
                host=app.config["MYSQL_HOST"],
                port=app.config["MYSQL_PORT"],
                user=app.config["MYSQL_USER"],
                password=app.config["MYSQL_PASSWORD"],
                dbname=app.config["MYSQL_DATABASE"]
            )
            conn.autocommit = True
            cursor = conn.cursor()
        
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255) NOT NULL UNIQUE,
                email VARCHAR(255) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                is_admin SMALLINT NOT NULL DEFAULT 0,
                role VARCHAR(50) DEFAULT NULL,
                permissions TEXT DEFAULT NULL,
                created_at TIMESTAMP NOT NULL,
                last_login TIMESTAMP DEFAULT NULL,
                totp_secret VARCHAR(255) DEFAULT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS otp_challenges (
                token VARCHAR(255) PRIMARY KEY,
                user_id INT NOT NULL,
                otp_hash VARCHAR(255) NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                attempts INT NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                token VARCHAR(255) PRIMARY KEY,
                user_id INT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS passkey_credentials (
                id SERIAL PRIMARY KEY,
                user_id INT NOT NULL,
                credential_id TEXT NOT NULL,
                public_key TEXT NOT NULL,
                sign_count INT NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS security_logs (
                id SERIAL PRIMARY KEY,
                user_id INT,
                username VARCHAR(255),
                event_type VARCHAR(255) NOT NULL,
                ip_address VARCHAR(255),
                user_agent TEXT,
                details TEXT,
                created_at TIMESTAMP NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS rooms (
                id SERIAL PRIMARY KEY,
                room_type VARCHAR(100) NOT NULL,
                total_count INT NOT NULL DEFAULT 0,
                available_count INT NOT NULL DEFAULT 0,
                occupied_count INT NOT NULL DEFAULT 0,
                cleaning_count INT NOT NULL DEFAULT 0,
                maintenance_count INT NOT NULL DEFAULT 0,
                price_per_night DECIMAL(10, 2) NOT NULL,
                updated_at TIMESTAMP NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS bookings (
                id SERIAL PRIMARY KEY,
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
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                created_by INT,
                FOREIGN KEY (created_by) REFERENCES users (id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS guest_profiles (
                id SERIAL PRIMARY KEY,
                guest_name VARCHAR(255) NOT NULL,
                guest_email VARCHAR(255) NOT NULL UNIQUE,
                guest_phone VARCHAR(50),
                preferences TEXT,
                notes TEXT,
                total_bookings INT NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS active_sessions (
                id SERIAL PRIMARY KEY,
                user_id INT NOT NULL,
                session_token VARCHAR(255) NOT NULL UNIQUE,
                ip_address VARCHAR(255),
                user_agent TEXT,
                device_fingerprint VARCHAR(255),
                country VARCHAR(100),
                risk_score INT NOT NULL DEFAULT 0,
                is_new_device SMALLINT NOT NULL DEFAULT 0,
                is_new_country SMALLINT NOT NULL DEFAULT 0,
                failed_attempts INT NOT NULL DEFAULT 0,
                previous_failed_attempts INT NOT NULL DEFAULT 0,
                last_activity TIMESTAMP NOT NULL,
                created_at TIMESTAMP NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
        
        # Create chat_messages table for chat system
        cursor.execute(
            """
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
            """
        )
        
        # Create indexes for chat_messages table
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id ON chat_messages(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_timestamp ON chat_messages(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_room ON chat_messages(room)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_admin_read ON chat_messages(admin_read)")
        
        # Create dh_keys table for Diffie-Hellman key exchange
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS dh_keys (
                id SERIAL PRIMARY KEY,
                session_id VARCHAR(255) NOT NULL UNIQUE,
                public_key TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMP NOT NULL DEFAULT NOW() + INTERVAL '24 hours'
            )
            """
        )
        
        # Create index for dh_keys table
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_dh_keys_session_id ON dh_keys(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_dh_keys_expires_at ON dh_keys(expires_at)")
        
        # Migration: Add totp_secret column if it doesn't exist
        try:
            cursor.execute("""
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='users' AND column_name='totp_secret'
                    ) THEN
                        ALTER TABLE users ADD COLUMN totp_secret VARCHAR(255) DEFAULT NULL;
                    END IF;
                END $$;
            """)
            print("DEBUG: Checked/added totp_secret column to users table")
        except Exception as e:
            print(f"DEBUG: Error adding totp_secret column: {e}")
    finally:
        conn.close()


# =========================
# Chat Database Functions
# =========================

def save_chat_message(session_id, user_id, username, user_email, message, sender_type, room):
    """Save a chat message to database"""
    db = get_db()
    cursor = db.cursor()
    
    print(f"DEBUG save_chat_message: session_id={session_id}, username={username}, sender_type={sender_type}, room={room}")
    print(f"DEBUG save_chat_message: message length={len(message) if message else 0}")
    
    try:
        cursor.execute("""
            INSERT INTO chat_messages 
            (session_id, user_id, username, user_email, message, sender_type, room, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        """, (session_id, user_id, username, user_email, message, sender_type, room))
        
        # autocommit is enabled, so no need to call commit()
        print(f"DEBUG save_chat_message: SUCCESS - Chat message saved: {username} ({sender_type}) in {room}")
        return True
    except Exception as e:
        print(f"DEBUG save_chat_message: ERROR - {e}")
        import traceback
        print(f"DEBUG save_chat_message: Traceback: {traceback.format_exc()}")
        return False


def get_chat_history(session_id=None, user_id=None, room=None, limit=50):
    """Get chat history for a user"""
    db = get_db()
    cursor = db.cursor()
    
    # Simple query without complex JOIN
    query = """
        SELECT id, session_id, user_id, username, user_email, message, sender_type, room, timestamp, admin_read
        FROM chat_messages 
        WHERE 1=1
    """
    params = []
    
    if session_id:
        query += " AND session_id = %s"
        params.append(session_id)
    
    if user_id:
        query += " AND user_id = %s"
        params.append(user_id)
    
    if room:
        query += " AND room = %s"
        params.append(room)
    
    query += " ORDER BY timestamp ASC LIMIT %s"
    params.append(limit)
    
    print(f"DEBUG: get_chat_history query: {query}")
    print(f"DEBUG: get_chat_history params: {params}")
    
    try:
        cursor.execute(query, params)
        result = cursor.fetchall()
        print(f"DEBUG: get_chat_history result count: {len(result)}")
        return result
    except Exception as e:
        print(f"DEBUG: get_chat_history error: {e}")
        import traceback
        print(f"DEBUG: get_chat_history traceback: {traceback.format_exc()}")
        return []


def get_active_conversations(hours=24):
    """Get active chat conversations from the last N hours"""
    db = get_db()
    cursor = db.cursor()
    
    try:
        # PostgreSQL requires INTERVAL as a string literal, not a parameter
        # Use make_interval function instead
        cursor.execute("""
            SELECT 
                session_id,
                user_id,
                username,
                user_email,
                room,
                MAX(timestamp) as last_message_time,
                SUM(CASE WHEN admin_read = 0 AND sender_type != 'admin' THEN 1 ELSE 0 END) as unread_count
            FROM chat_messages
            WHERE timestamp >= NOW() - make_interval(hours => %s)
            GROUP BY session_id, user_id, username, user_email, room
            ORDER BY last_message_time DESC
        """, (hours,))
        
        return cursor.fetchall()
    except Exception as e:
        print(f"Error getting chat stats: {e}")
        return []


def mark_messages_as_read(session_id=None, room=None):
    """Mark messages as read by admin"""
    db = get_db()
    cursor = db.cursor()
    
    query = "UPDATE chat_messages SET admin_read = 1 WHERE admin_read = 0"
    params = []
    
    if session_id:
        query += " AND session_id = %s"
        params.append(session_id)
    
    if room:
        query += " AND room = %s"
        params.append(room)
    
    cursor.execute(query, params)
    print(f"Messages marked as read for session: {session_id}, room: {room}")


def get_all_chat_sessions():
    """Get all unique chat sessions for admin dashboard"""
    db = get_db()
    cursor = db.cursor()
    
    try:
        # First check if table has any data
        cursor.execute("SELECT COUNT(*) as count FROM chat_messages")
        count_result = cursor.fetchone()
        total_count = count_result['count'] if count_result else 0
        print(f"DEBUG get_all_chat_sessions: Total messages in chat_messages table: {total_count}")
        
        # Get unique session IDs
        cursor.execute("""
            SELECT DISTINCT session_id FROM chat_messages 
            WHERE room = 'customer_service'
        """)
        
        session_ids = cursor.fetchall()
        
        result = []
        for row in session_ids:
            sid = row['session_id']
            
            # Get the FIRST user message to identify who opened the chat
            cursor.execute("""
                SELECT session_id, username, user_email
                FROM chat_messages 
                WHERE session_id = %s AND room = 'customer_service' AND sender_type = 'user'
                ORDER BY timestamp ASC
                LIMIT 1
            """, (sid,))
            
            first_user = cursor.fetchone()
            
            # Get the LATEST message for timestamp and preview
            cursor.execute("""
                SELECT message, sender_type, timestamp
                FROM chat_messages 
                WHERE session_id = %s AND room = 'customer_service'
                ORDER BY timestamp DESC
                LIMIT 1
            """, (sid,))
            
            latest = cursor.fetchone()
            
            if first_user and latest:
                result.append({
                    'session_id': sid,
                    'username': first_user['username'],  # User who opened the chat
                    'user_email': first_user['user_email'],
                    'last_message': latest['message'],
                    'sender_type': latest['sender_type'],
                    'timestamp': latest['timestamp']
                })
            elif latest:
                # Fallback if no user message found (shouldn't happen)
                result.append({
                    'session_id': sid,
                    'username': 'Unknown',
                    'user_email': None,
                    'last_message': latest['message'],
                    'sender_type': latest['sender_type'],
                    'timestamp': latest['timestamp']
                })
        
        return result
    except Exception as e:
        print(f"Error getting chat sessions: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return []


# =========================
# Diffie-Hellman Key Exchange Functions
# =========================

def store_dh_public_key(session_id, public_key):
    """Store a client's Diffie-Hellman public key"""
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO dh_keys (session_id, public_key)
            VALUES (%s, %s)
            ON CONFLICT (session_id) 
            DO UPDATE SET public_key = EXCLUDED.public_key, 
                         created_at = NOW(),
                         expires_at = NOW() + INTERVAL '24 hours'
        """, (session_id, public_key))
        
        print(f"DH public key stored for session: {session_id}")
        return True
    except Exception as e:
        print(f"Error storing DH public key: {e}")
        return False


def get_dh_public_key(session_id):
    """Get a client's Diffie-Hellman public key"""
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            SELECT public_key FROM dh_keys 
            WHERE session_id = %s AND expires_at > NOW()
        """, (session_id,))
        
        result = cursor.fetchone()
        if result:
            return result['public_key']
        return None
    except Exception as e:
        print(f"Error retrieving DH public key: {e}")
        return None


def cleanup_expired_dh_keys():
    """Remove expired Diffie-Hellman keys"""
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("DELETE FROM dh_keys WHERE expires_at < NOW()")
        print("Expired DH keys cleaned up")
        return True
    except Exception as e:
        print(f"Error cleaning up expired DH keys: {e}")
        return False


def seed_admin(app):
    username = "Admin1!"
    password = "MGMAdmin1234!"
    email = app.config.get("ADMIN_EMAIL", "admin@example.com")

    # Check if DATABASE_URL is provided (Render PostgreSQL)
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        conn = psycopg.connect(database_url, row_factory=dict_row)
        conn.autocommit = True
    else:
        conn = psycopg.connect(
            host=app.config["MYSQL_HOST"],
            port=app.config["MYSQL_PORT"],
            user=app.config["MYSQL_USER"],
            password=app.config["MYSQL_PASSWORD"],
            dbname=app.config["MYSQL_DATABASE"],
            row_factory=dict_row
        )
        conn.autocommit = True
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) as count FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'users'"
        )
        if cursor.fetchone()["count"] == 0:
            return
        
        cursor.execute(
            "SELECT id FROM users WHERE username = %s", (username,)
        )
        existing = cursor.fetchone()
        if existing is None:
            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, is_admin, created_at)
                VALUES (%s, %s, %s, 1, %s)
                """,
                (
                    username,
                    email,
                    generate_password_hash(password),
                    datetime.utcnow(),
                ),
            )
        else:
            # Update existing master admin: set new password and ensure role is NULL for full permissions
            cursor.execute(
                """
                UPDATE users 
                SET password_hash = %s, role = NULL, permissions = NULL 
                WHERE username = %s
                """,
                (generate_password_hash(password), username)
            )
            print(f"Updated master admin password and ensured full permissions (role=NULL)")
    finally:
        conn.close()


def seed_rooms(app):
    """Populate rooms table with available room types from the website"""
    # Check if DATABASE_URL is provided (Render PostgreSQL)
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        conn = psycopg.connect(database_url, row_factory=dict_row)
        conn.autocommit = True
    else:
        conn = psycopg.connect(
            host=app.config["MYSQL_HOST"],
            port=app.config["MYSQL_PORT"],
            user=app.config["MYSQL_USER"],
            password=app.config["MYSQL_PASSWORD"],
            dbname=app.config["MYSQL_DATABASE"],
            row_factory=dict_row
        )
        conn.autocommit = True
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) as count FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'rooms'"
        )
        if cursor.fetchone()["count"] == 0:
            return
        
        # Room types from the website
        rooms = [
            {"room_type": "Luxury Suite", "total_count": 10, "price": 299.00},
            {"room_type": "Deluxe Room", "total_count": 10, "price": 229.00},
            {"room_type": "Executive Suite", "total_count": 10, "price": 399.00}
        ]
        
        for room in rooms:
            cursor.execute(
                "SELECT id FROM rooms WHERE room_type = %s", (room["room_type"],)
            )
            existing = cursor.fetchone()
            if existing is None:
                cursor.execute(
                    """
                    INSERT INTO rooms (room_type, total_count, available_count, occupied_count, cleaning_count, maintenance_count, price_per_night, updated_at)
                    VALUES (%s, %s, %s, 0, 0, 0, %s, %s)
                    """,
                    (room["room_type"], room["total_count"], room["total_count"], room["price"], datetime.utcnow())
                )
                print(f"Seeded room: {room['room_type']} with {room['total_count']} available")
    finally:
        conn.close()


def get_user_by_username(username: str):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    return cursor.fetchone()


def get_user_by_id(user_id: int):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    return cursor.fetchone()


def create_user(username: str, email: str, password_hash: str, is_admin: int = 0):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        """
        INSERT INTO users (username, email, password_hash, is_admin, created_at)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (username, email, password_hash, int(is_admin), datetime.utcnow()),
    )


def create_otp_challenge(
    token: str,
    user_id: int,
    otp_hash: str,
    expires_at: str,
):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        """
        INSERT INTO otp_challenges (token, user_id, otp_hash, expires_at, attempts, created_at)
        VALUES (%s, %s, %s, %s, 0, %s)
        """,
        (token, int(user_id), otp_hash, expires_at, datetime.utcnow()),
    )


def get_otp_challenge(token: str):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "SELECT * FROM otp_challenges WHERE token = %s", (token,)
    )
    return cursor.fetchone()


def increment_otp_attempts(token: str):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "UPDATE otp_challenges SET attempts = attempts + 1 WHERE token = %s", (token,)
    )


def delete_otp_challenge(token: str):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM otp_challenges WHERE token = %s", (token,))


def get_user_by_email(email: str):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    return cursor.fetchone()


def create_password_reset_token(token: str, user_id: int, expires_at: str):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        """
        INSERT INTO password_reset_tokens (token, user_id, expires_at, created_at)
        VALUES (%s, %s, %s, %s)
        """,
        (token, int(user_id), expires_at, datetime.utcnow()),
    )


def get_password_reset_token(token: str):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "SELECT * FROM password_reset_tokens WHERE token = %s", (token,)
    )
    return cursor.fetchone()


def delete_password_reset_token(token: str):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM password_reset_tokens WHERE token = %s", (token,))


def update_user_password(user_id: int, password_hash: str):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "UPDATE users SET password_hash = %s WHERE id = %s", (password_hash, user_id)
    )


def create_passkey_credential(user_id: int, credential_id: str, public_key: str):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        """
        INSERT INTO passkey_credentials (user_id, credential_id, public_key, sign_count, created_at)
        VALUES (%s, %s, %s, 0, %s)
        """,
        (int(user_id), credential_id, public_key, datetime.utcnow()),
    )


def get_passkey_credentials(user_id: int):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "SELECT * FROM passkey_credentials WHERE user_id = %s", (int(user_id),)
    )
    return cursor.fetchall()


def get_passkey_by_credential_id(credential_id: str):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "SELECT * FROM passkey_credentials WHERE credential_id = %s", (credential_id,)
    )
    return cursor.fetchone()


def update_passkey_sign_count(credential_id: str, sign_count: int):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "UPDATE passkey_credentials SET sign_count = %s WHERE credential_id = %s",
        (int(sign_count), credential_id)
    )


def delete_passkey_credential(credential_id: str):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "DELETE FROM passkey_credentials WHERE credential_id = %s", (credential_id,)
    )


def remove_master_admin_passkeys():
    """Remove all passkey credentials for Master admin account (Admin1!)"""
    db = get_db()
    cursor = db.cursor()
    
    try:
        # Get Admin1! user ID
        cursor.execute("SELECT id FROM users WHERE username = %s", ("Admin1!",))
        admin_user = cursor.fetchone()
        
        if admin_user:
            admin_id = admin_user['id']
            # Delete all passkey credentials for Admin1!
            cursor.execute(
                "DELETE FROM passkey_credentials WHERE user_id = %s", (admin_id,)
            )
            print(f"Removed all passkey credentials for Master admin account (Admin1!)")
            return True
        else:
            print("Master admin account (Admin1!) not found")
            return False
    except Exception as e:
        print(f"Error removing master admin passkeys: {e}")
        return False


def log_security_event(user_id, username, event_type, details=None, risk_score=None):
    db = get_db()
    cursor = db.cursor()
    ip_address = request.remote_addr if request else None
    user_agent = request.headers.get('User-Agent') if request else None
    
    # Include risk score in details if provided
    if risk_score is not None:
        details = f"{details} | Risk Score: {risk_score}" if details else f"Risk Score: {risk_score}"
    
    cursor.execute(
        """
        INSERT INTO security_logs (user_id, username, event_type, ip_address, user_agent, details, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (user_id, username, event_type, ip_address, user_agent, details, datetime.utcnow())
    )


def get_security_logs(limit=100):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "SELECT * FROM security_logs ORDER BY created_at DESC LIMIT %s",
        (limit,)
    )
    return cursor.fetchall()


def get_login_stats():
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute(
        "SELECT COUNT(*) as count FROM security_logs WHERE event_type = 'login_success'"
    )
    successful_logins = cursor.fetchone()['count']
    
    cursor.execute(
        "SELECT COUNT(*) as count FROM security_logs WHERE event_type = 'login_failed'"
    )
    failed_logins = cursor.fetchone()['count']
    
    cursor.execute(
        "SELECT COUNT(*) as count FROM security_logs WHERE event_type = 'account_locked'"
    )
    account_lockouts = cursor.fetchone()['count']
    
    cursor.execute(
        "SELECT COUNT(*) as count FROM users"
    )
    total_users = cursor.fetchone()['count']
    
    return {
        'successful_logins': successful_logins,
        'failed_logins': failed_logins,
        'account_lockouts': account_lockouts,
        'total_users': total_users
    }


def get_all_users():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, username, email, is_admin, role, permissions, created_at, last_login FROM users ORDER BY created_at DESC")
    users = cursor.fetchall()
    import json
    for user in users:
        if user.get('permissions'):
            try:
                user['permissions'] = json.loads(user['permissions'])
            except:
                user['permissions'] = {}
        else:
            user['permissions'] = {}
    return users


def delete_user(user_id: int):
    db = get_db()
    cursor = db.cursor()
    
    try:
        print(f"\n{'='*80}")
        print(f"DEBUG: delete_user called for user_id: {user_id}")
        
        # Delete from all related tables first to avoid foreign key constraint errors
        cursor.execute("DELETE FROM passkey_credentials WHERE user_id = %s", (user_id,))
        print(f"DEBUG: Deleted {cursor.rowcount} passkey_credentials")
        
        cursor.execute("DELETE FROM otp_challenges WHERE user_id = %s", (user_id,))
        print(f"DEBUG: Deleted {cursor.rowcount} otp_challenges")
        
        cursor.execute("DELETE FROM password_reset_tokens WHERE user_id = %s", (user_id,))
        print(f"DEBUG: Deleted {cursor.rowcount} password_reset_tokens")
        
        cursor.execute("DELETE FROM active_sessions WHERE user_id = %s", (user_id,))
        print(f"DEBUG: Deleted {cursor.rowcount} active_sessions")
        
        cursor.execute("DELETE FROM chat_messages WHERE user_id = %s", (user_id,))
        print(f"DEBUG: Deleted {cursor.rowcount} chat_messages")
        
        # Note: We keep security_logs for audit trail - just set user_id to NULL
        cursor.execute("UPDATE security_logs SET user_id = NULL WHERE user_id = %s", (user_id,))
        print(f"DEBUG: Updated {cursor.rowcount} security_logs")
        
        # Finally delete the user
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        print(f"DEBUG: Deleted {cursor.rowcount} users")
        
        db.commit()
        print(f"DEBUG: Database commit successful")
        print(f"{'='*80}\n")
        
    except Exception as e:
        print(f"ERROR: Exception in delete_user: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"ERROR: Traceback: {traceback.format_exc()}")
        print(f"{'='*80}\n")
        db.rollback()
        raise


def create_sub_admin(username: str, email: str, password_hash: str, role: str, permissions: dict):
    db = get_db()
    cursor = db.cursor()
    import json
    
    # Check if username or email already exists
    cursor.execute("SELECT id FROM users WHERE username = %s OR email = %s", (username, email))
    existing = cursor.fetchone()
    if existing:
        raise ValueError("Username or email already exists")
    
    cursor.execute(
        """
        INSERT INTO users (username, email, password_hash, is_admin, role, permissions, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (username, email, password_hash, 1, role, json.dumps(permissions), datetime.utcnow())
    )
    result = cursor.fetchone()
    db.commit()
    return result['id'] if result else None


def update_user_role(user_id: int, role: str, permissions: dict):
    db = get_db()
    cursor = db.cursor()
    import json
    cursor.execute(
        "UPDATE users SET role = %s, permissions = %s WHERE id = %s",
        (role, json.dumps(permissions), user_id)
    )


def get_user_permissions(user_id: int):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT role, permissions FROM users WHERE id = %s", (user_id,))
        result = cursor.fetchone()
        if result:
            import json
            if result.get('permissions'):
                try:
                    result['permissions'] = json.loads(result['permissions'])
                except:
                    result['permissions'] = {}
            else:
                result['permissions'] = {}
            return result
        else:
            # User not found, return None
            return None
    except Exception:
        # Columns don't exist yet - return default for master admin
        cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
        if cursor.fetchone():
            return {'role': None, 'permissions': {}}
        return None


def set_totp_secret(user_id: int, totp_secret: str):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE users SET totp_secret = %s WHERE id = %s", (totp_secret, user_id))


def get_totp_secret(user_id: int):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT totp_secret FROM users WHERE id = %s", (user_id,))
    result = cursor.fetchone()
    return result['totp_secret'] if result else None


def update_last_login(user_id: int):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE users SET last_login = %s WHERE id = %s", (datetime.utcnow(), user_id))


def get_country_from_ip(ip_address: str) -> str:
    """Get country from IP address using ip-api.com (free, no key required)"""
    if not ip_address or ip_address == '127.0.0.1' or ip_address.startswith('192.168.') or ip_address.startswith('10.'):
        return 'Local'
    
    try:
        import requests
        response = requests.get(f'http://ip-api.com/json/{ip_address}?fields=country', timeout=2)
        if response.status_code == 200:
            data = response.json()
            return data.get('country', 'Unknown')
    except:
        pass
    return 'Unknown'


def create_or_update_session(user_id: int, session_token: str, ip_address: str, user_agent: str, country: str = None):
    """Create or update a session with risk scoring based on device and country"""
    print("\n" + "="*80)
    print("DEBUG: create_or_update_session called")
    print(f"DEBUG: user_id={user_id}, session_token={session_token}, ip_address={ip_address}")
    print(f"DEBUG: user_agent={user_agent[:50] if user_agent else None}...")
    print("="*80)
    
    try:
        db = get_db()
        cursor = db.cursor()
        print("DEBUG: Database connection established")
        
        # Get country from IP if not provided
        if not country:
            print("DEBUG: Getting country from IP...")
            country = get_country_from_ip(ip_address)
            print(f"DEBUG: Country resolved: {country}")
        
        # Generate device fingerprint from user agent
        import hashlib
        device_fingerprint = hashlib.md5(user_agent.encode()).hexdigest() if user_agent else None
        print(f"DEBUG: Device fingerprint: {device_fingerprint}")
        
        # Check if session already exists first
        print("DEBUG: Checking for existing session...")
        cursor.execute("SELECT id, failed_attempts, device_fingerprint, country FROM active_sessions WHERE session_token = %s", (session_token,))
        existing = cursor.fetchone()
        print(f"DEBUG: Existing session: {existing}")
        
        # Get failed attempts from any session with same device/IP (regardless of user)
        print("DEBUG: Checking for previous failed attempts...")
        cursor.execute(
            "SELECT failed_attempts FROM active_sessions WHERE device_fingerprint = %s AND ip_address = %s ORDER BY last_activity DESC LIMIT 1",
            (device_fingerprint, ip_address)
        )
        device_session = cursor.fetchone()
        previous_failed = device_session['failed_attempts'] if device_session else 0
        print(f"DEBUG: Previous failed attempts: {previous_failed}")
        
        # Check if this is a new device for this user (exclude current session)
        is_new_device = False
        if not existing or existing['device_fingerprint'] != device_fingerprint:
            cursor.execute(
                "SELECT COUNT(*) as count FROM active_sessions WHERE user_id = %s AND device_fingerprint = %s AND session_token != %s",
                (user_id, device_fingerprint, session_token)
            )
            is_new_device = cursor.fetchone()['count'] == 0
        print(f"DEBUG: Is new device: {is_new_device}")
        
        # Check if this is a new country for this user (exclude current session)
        is_new_country = False
        if country and (not existing or existing['country'] != country):
            cursor.execute(
                "SELECT COUNT(*) as count FROM active_sessions WHERE user_id = %s AND country = %s AND session_token != %s",
                (user_id, country, session_token)
            )
            is_new_country = cursor.fetchone()['count'] == 0
        print(f"DEBUG: Is new country: {is_new_country}")
        
        # Calculate risk score for new device/country only
        risk_score = 0
        if is_new_device:
            risk_score += 2
        if is_new_country:
            risk_score += 2
        
        # Add failed attempts to risk score (each failed attempt = +2)
        total_risk_score = risk_score + (previous_failed * 2)
        print(f"DEBUG: Total risk score: {total_risk_score}")
        
        if existing:
            print("DEBUG: Updating existing session...")
            # Update existing session and reset failed_attempts on successful login
            cursor.execute(
                """UPDATE active_sessions 
                   SET last_activity = %s, risk_score = %s, ip_address = %s, 
                       previous_failed_attempts = %s, failed_attempts = 0
                   WHERE session_token = %s""",
                (datetime.utcnow(), total_risk_score, ip_address, previous_failed, session_token)
            )
        else:
            print("DEBUG: Creating new session...")
            # Create new session - convert booleans to int for SMALLINT columns
            cursor.execute(
                """INSERT INTO active_sessions 
                   (user_id, session_token, ip_address, user_agent, device_fingerprint, country, 
                    risk_score, is_new_device, is_new_country, previous_failed_attempts, last_activity, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (user_id, session_token, ip_address, user_agent, device_fingerprint, country,
                 total_risk_score, int(is_new_device), int(is_new_country), previous_failed, datetime.utcnow(), datetime.utcnow())
            )
        
        print("DEBUG: Committing transaction...")
        db.commit()
        print("DEBUG: Session created/updated successfully")
        print("="*80 + "\n")
        return total_risk_score
    except Exception as e:
        print(f"DEBUG: EXCEPTION in create_or_update_session: {type(e).__name__}")
        print(f"DEBUG: Exception message: {str(e)}")
        import traceback
        print("DEBUG: Full traceback:")
        traceback.print_exc()
        print("="*80 + "\n")
        # Return 0 risk score on error to allow login to continue
        return 0


def increment_session_failed_attempts(session_token: str):
    """Increment failed attempts and update risk score (+2 per failed attempt)"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        """UPDATE active_sessions 
           SET failed_attempts = failed_attempts + 1, 
               risk_score = risk_score + 2,
               last_activity = %s
           WHERE session_token = %s""",
        (datetime.utcnow(), session_token)
    )
    db.commit()


def increment_failed_attempts_by_user(user_id: int, ip_address: str, user_agent: str):
    """Increment failed attempts by IP and device (regardless of username)"""
    db = get_db()
    cursor = db.cursor()
    
    import hashlib
    device_fingerprint = hashlib.md5(user_agent.encode()).hexdigest() if user_agent else None
    
    # Find existing session for this device/IP (regardless of user_id)
    cursor.execute(
        """SELECT id, risk_score FROM active_sessions 
           WHERE device_fingerprint = %s AND ip_address = %s
           ORDER BY last_activity DESC LIMIT 1""",
        (device_fingerprint, ip_address)
    )
    session = cursor.fetchone()
    
    if session:
        # Update existing session
        new_risk_score = session['risk_score'] + 2
        cursor.execute(
            """UPDATE active_sessions 
               SET failed_attempts = failed_attempts + 1, 
                   risk_score = %s,
                   last_activity = %s
               WHERE id = %s""",
            (new_risk_score, datetime.utcnow(), session['id'])
        )
        db.commit()
        return new_risk_score
    return 0


def send_high_risk_alert(username: str, risk_score: int):
    """Send email alert to master admin when risk score >= 8"""
    from flask_mail import Message
    from app import mail
    
    try:
        msg = Message(
            subject=f"High Risk Alert: {username}",
            sender="noreply@ispjhotel.com",
            recipients=["ngisaac15@gmail.com"]
        )
        msg.body = f"""
High Risk Security Alert

Username: {username}
Risk Score: {risk_score}
Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC

This user account has reached a risk score of {risk_score}, indicating multiple failed login attempts or suspicious activity.

Please review the active sessions in the admin portal for more details.
"""
        mail.send(msg)
    except Exception as e:
        # Log error but don't fail the login process
        print(f"Failed to send high risk alert email: {e}")


def check_account_lockout(user_id: int, ip_address: str, user_agent: str, role: str = None):
    """Check if account is locked out due to failed attempts (5 attempts for all users)"""
    db = get_db()
    cursor = db.cursor()
    
    # Lockout threshold is 5 for all users
    threshold = 5
    
    import hashlib
    device_fingerprint = hashlib.md5(user_agent.encode()).hexdigest() if user_agent else None
    
    # Find existing session for this device/IP (regardless of user_id)
    cursor.execute(
        """SELECT failed_attempts, last_activity FROM active_sessions 
           WHERE device_fingerprint = %s AND ip_address = %s
           ORDER BY last_activity DESC LIMIT 1""",
        (device_fingerprint, ip_address)
    )
    session = cursor.fetchone()
    
    if session and session['failed_attempts'] >= threshold:
        # Check if 5 minutes have passed since last failed attempt
        last_activity = session['last_activity']
        if isinstance(last_activity, str):
            last_activity = datetime.fromisoformat(last_activity)
        
        time_diff = datetime.utcnow() - last_activity
        if time_diff.total_seconds() < 300:  # 5 minutes = 300 seconds
            remaining_seconds = 300 - int(time_diff.total_seconds())
            remaining_minutes = remaining_seconds // 60
            remaining_secs = remaining_seconds % 60
            return True, f"{remaining_minutes}:{remaining_secs:02d}"
    
    return False, None


def get_active_sessions():
    """Get all active sessions with user information"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        """SELECT s.*, u.username, u.email 
           FROM active_sessions s
           JOIN users u ON s.user_id = u.id
           ORDER BY s.risk_score DESC, s.last_activity DESC"""
    )
    return cursor.fetchall()


def cleanup_old_sessions(hours: int = 24):
    """Remove sessions older than specified hours"""
    db = get_db()
    cursor = db.cursor()
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    cursor.execute("DELETE FROM active_sessions WHERE last_activity < %s", (cutoff,))
    db.commit()


def delete_session(session_id: int):
    """Delete a specific session by ID and log admin-forced logout"""
    db = get_db()
    cursor = db.cursor()
    
    # Get session info before deleting for logging
    cursor.execute(
        "SELECT user_id, risk_score FROM active_sessions WHERE id = %s",
        (session_id,)
    )
    session_info = cursor.fetchone()
    
    if session_info:
        # Get username for logging
        cursor.execute("SELECT username FROM users WHERE id = %s", (session_info['user_id'],))
        user_info = cursor.fetchone()
        
        if user_info:
            # Log admin-forced logout with risk score
            log_security_event(
                session_info['user_id'],
                user_info['username'],
                'logout',
                'Admin forced logout',
                risk_score=session_info['risk_score']
            )
    
    cursor.execute("DELETE FROM active_sessions WHERE id = %s", (session_id,))
    db.commit()


# =========================
# Casino Balance Functions
# =========================

def get_user_casino_balance(user_id: int) -> int:
    """Get user's casino balance, create with default 1000 if not exists"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # First ensure the table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS casino_balances (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                balance INTEGER NOT NULL DEFAULT 1000,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        cursor.execute("SELECT balance FROM casino_balances WHERE user_id = %s", (user_id,))
        result = cursor.fetchone()
        
        if result:
            return result['balance']
        else:
            # Create new balance record with default 1000 chips
            cursor.execute(
                "INSERT INTO casino_balances (user_id, balance) VALUES (%s, %s)",
                (user_id, 1000)
            )
            return 1000
    except Exception as e:
        print(f"Error getting casino balance: {e}")
        return 1000


# =========================
# Booking Management Functions
# =========================

def get_all_bookings(limit: int = 100):
    """Get all bookings from database"""
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            SELECT b.*, u.username as created_by_name 
            FROM bookings b
            LEFT JOIN users u ON b.created_by = u.id
            ORDER BY b.created_at DESC
            LIMIT %s
        """, (limit,))
        bookings = cursor.fetchall()
        return bookings
    except Exception as e:
        print(f"Error getting bookings: {e}")
        return []


def get_booking_by_id(booking_id: int):
    """Get specific booking by ID"""
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            SELECT b.*, u.username as created_by_name 
            FROM bookings b
            LEFT JOIN users u ON b.created_by = u.id
            WHERE b.id = %s
        """, (booking_id,))
        return cursor.fetchone()
    except Exception as e:
        print(f"Error getting booking: {e}")
        return None


def get_room_availability():
    """Get room availability status"""
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT * FROM rooms ORDER BY room_type")
        return cursor.fetchall()
    except Exception as e:
        print(f"Error getting room availability: {e}")
        # Create table if it doesn't exist
        try:
            cursor.execute("""
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
                )
            """)
            db.commit()
            return []
        except:
            return []


def create_booking(user_id: int, booking_data: dict) -> int:
    """Create a new booking and return booking ID"""
    print("\n" + "="*80)
    print(f"DEBUG: Creating booking for user_id: {user_id}")
    print(f"DEBUG: Booking data: {booking_data}")
    
    db = get_db()
    cursor = db.cursor()
    
    # First check if the bookings table exists
    try:
        cursor.execute("""SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name = 'bookings'
        )""")
        table_exists = cursor.fetchone().get('exists', False)
        print(f"DEBUG: Bookings table exists: {table_exists}")
        
        if not table_exists:
            print("DEBUG: Creating bookings table...")
            cursor.execute("""
                CREATE TABLE bookings (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER,
                    guest_name VARCHAR(255) NOT NULL,
                    guest_email VARCHAR(255) NOT NULL,
                    guest_phone VARCHAR(50),
                    room_type VARCHAR(100) NOT NULL,
                    check_in_date DATE NOT NULL,
                    check_out_date DATE NOT NULL,
                    num_guests INTEGER DEFAULT 1,
                    total_price NUMERIC(10, 2) NOT NULL,
                    status VARCHAR(50) DEFAULT 'pending',
                    special_requests TEXT,
                    notes TEXT,
                    passport_file VARCHAR(255),
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            # Note: db.commit() not needed since autocommit is enabled
            print("DEBUG: Bookings table created successfully")
            
        # Prepare booking data
        from datetime import datetime
        
        # Get and validate data fields
        # Ensure required fields have fallbacks for database constraints
        guest_name = booking_data.get('guest_name') or 'Guest'
        guest_email = booking_data.get('email') or f'guest{user_id}@example.com'
        guest_phone = booking_data.get('phone') or ''
        room_type = booking_data.get('room_type') or 'Standard Room'
        
        # Log validation
        print(f"DEBUG: Validating guest_name: '{guest_name}'")
        print(f"DEBUG: Validating guest_email: '{guest_email}'")
        
        # Ensure total_price is a valid Numeric value
        try:
            raw_price = booking_data.get('total_price')
            if raw_price is None or raw_price == '':
                total_price = 0.0
                print("DEBUG: total_price is None or empty, using 0.0")
            else:
                total_price = float(raw_price)
                print(f"DEBUG: Converted total_price '{raw_price}' to {total_price}")
        except (ValueError, TypeError) as e:
            print(f"DEBUG: Error converting total_price to float: {e}, using 0.0")
            total_price = 0.0
            
        special_requests = booking_data.get('special_requests', '')
        # Handle passport file (make sure we have a default value)
        passport_file = booking_data.get('passport_file')
        if passport_file is None:
            passport_file = ''
        print(f"DEBUG: Passport file: '{passport_file}'")
        
        # Check if the file exists and is accessible
        if passport_file:
            file_path = os.path.join('app', 'static', 'uploads', 'passports', passport_file)
            if os.path.exists(file_path):
                print(f"DEBUG: Passport file exists at {file_path}")
            else:
                print(f"DEBUG: Passport file not found at {file_path}, but will save reference anyway")
        
        # Convert date strings to proper date objects
        check_in = datetime.now().date()  # Default
        check_out = datetime.now().date() + timedelta(days=1)  # Default
        
        try:
            if booking_data.get('check_in'):
                check_in = datetime.strptime(booking_data['check_in'], '%Y-%m-%d').date()
        except Exception as e:
            print(f"DEBUG: Error parsing check_in date: {e}, using default")
            
        try:
            if booking_data.get('check_out'):
                check_out = datetime.strptime(booking_data['check_out'], '%Y-%m-%d').date()
        except Exception as e:
            print(f"DEBUG: Error parsing check_out date: {e}, using default")
        
        # Use nights as num_guests if num_guests not provided
        try:
            num_guests = int(booking_data.get('nights', 1))
        except (ValueError, TypeError):
            print(f"DEBUG: Error converting nights {booking_data.get('nights')} to int, using 1")
            num_guests = 1
        
        # Print prepared values
        print(f"DEBUG: Prepared data for insertion:")
        print(f"  user_id: {user_id}")
        print(f"  guest_name: {guest_name}")
        print(f"  guest_email: {guest_email}")
        print(f"  room_type: {room_type}")
        print(f"  check_in: {check_in}")
        print(f"  check_out: {check_out}")
        print(f"  num_guests: {num_guests}")
        print(f"  total_price: {total_price}")
        
        # Insert booking
        print(f"DEBUG: Executing INSERT query...")
        cursor.execute("""
            INSERT INTO bookings 
            (user_id, guest_name, guest_email, guest_phone, room_type, 
             check_in_date, check_out_date, num_guests, total_price, 
             status, special_requests, notes, passport_file)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            user_id,
            guest_name,
            guest_email,
            guest_phone,
            room_type,
            check_in,
            check_out,
            num_guests,
            total_price,
            'confirmed',  # Payment confirmed via Stripe
            special_requests,
            '',
            passport_file
        ))
        
        print(f"DEBUG: INSERT executed, fetching result...")
        result = cursor.fetchone()
        
        if result is None:
            print(f"ERROR: INSERT did not return a result")
            return -1
            
        booking_id = result['id']
        print(f"DEBUG: Successfully created booking {booking_id} for user {user_id}")
        print("="*80 + "\n")
        return booking_id
        
    except Exception as e:
        import traceback
        print(f"ERROR: Exception in create_booking: {type(e).__name__}: {str(e)}")
        print(f"ERROR: Traceback:\n{traceback.format_exc()}")
        print("="*80 + "\n")
        # Note: db.rollback() not needed since autocommit is enabled
        return -1  # Return -1 instead of raising to prevent crashing the app


def update_booking(booking_id: int, data: dict) -> bool:
    """Update booking information"""
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            UPDATE bookings 
            SET guest_name = %s, 
                guest_email = %s, 
                guest_phone = %s,
                room_type = %s,
                check_in_date = %s,
                check_out_date = %s,
                num_guests = %s,
                total_price = %s,
                status = %s,
                special_requests = %s,
                notes = %s,
                updated_at = %s
            WHERE id = %s
        """, (
            data.get('guest_name'),
            data.get('guest_email'),
            data.get('guest_phone'),
            data.get('room_type'),
            data.get('check_in_date'),
            data.get('check_out_date'),
            data.get('num_guests'),
            data.get('total_price'),
            data.get('status'),
            data.get('special_requests'),
            data.get('notes'),
            datetime.utcnow(),
            booking_id
        ))
        db.commit()
        return True
    except Exception as e:
        print(f"Error updating booking: {e}")
        return False


def update_room_status(room_type: str, available: int, occupied: int, cleaning: int, maintenance: int) -> bool:
    """Update room availability counts"""
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            UPDATE rooms 
            SET available_count = %s,
                occupied_count = %s,
                cleaning_count = %s,
                maintenance_count = %s,
                updated_at = %s
            WHERE room_type = %s
        """, (available, occupied, cleaning, maintenance, datetime.utcnow(), room_type))
        db.commit()
        return True
    except Exception as e:
        print(f"Error updating room status: {e}")
        return False


# =========================
# IP-Based Login Lockout Functions
# =========================

def check_ip_lockout(ip_address: str) -> tuple:
    """Check if IP is locked out. Returns (is_locked, remaining_seconds, attempts)"""
    db = get_db()
    cursor = db.cursor()
    
    try:
        # Create table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS login_attempts (
                ip_address VARCHAR(50) PRIMARY KEY,
                failed_attempts INT NOT NULL DEFAULT 0,
                lockout_until DATETIME,
                last_attempt DATETIME NOT NULL
            )
        """)
        db.commit()
        
        cursor.execute("""
            SELECT failed_attempts, lockout_until 
            FROM login_attempts 
            WHERE ip_address = %s
        """, (ip_address,))
        
        result = cursor.fetchone()
        
        if not result:
            return (False, 0, 0)
        
        failed_attempts = result['failed_attempts']
        lockout_until = result['lockout_until']
        
        # Check if currently locked out
        if lockout_until and datetime.utcnow() < lockout_until:
            remaining_seconds = int((lockout_until - datetime.utcnow()).total_seconds())
            return (True, remaining_seconds, failed_attempts)
        
        return (False, 0, failed_attempts)
        
    except Exception as e:
        print(f"Error checking IP lockout: {e}")
        return (False, 0, 0)


def record_failed_login(ip_address: str):
    """Record a failed login attempt and apply lockout if needed"""
    db = get_db()
    cursor = db.cursor()
    
    try:
        # Get current attempts
        cursor.execute("""
            SELECT failed_attempts, lockout_until 
            FROM login_attempts 
            WHERE ip_address = %s
        """, (ip_address,))
        
        result = cursor.fetchone()
        
        if result:
            failed_attempts = result['failed_attempts']
            lockout_until = result['lockout_until']
            
            # If lockout expired, reset counter
            if lockout_until and datetime.utcnow() >= lockout_until:
                failed_attempts = 0
            
            failed_attempts += 1
            
            # Apply 2-minute lockout after 5 failed attempts
            if failed_attempts >= 5:
                lockout_until = datetime.utcnow() + timedelta(minutes=2)
                cursor.execute("""
                    UPDATE login_attempts 
                    SET failed_attempts = %s, lockout_until = %s, last_attempt = %s
                    WHERE ip_address = %s
                """, (failed_attempts, lockout_until, datetime.utcnow(), ip_address))
            else:
                cursor.execute("""
                    UPDATE login_attempts 
                    SET failed_attempts = %s, last_attempt = %s
                    WHERE ip_address = %s
                """, (failed_attempts, datetime.utcnow(), ip_address))
        else:
            # First failed attempt for this IP
            cursor.execute("""
                INSERT INTO login_attempts (ip_address, failed_attempts, last_attempt)
                VALUES (%s, 1, %s)
            """, (ip_address, datetime.utcnow()))
        
        db.commit()
        
    except Exception as e:
        print(f"Error recording failed login: {e}")


def clear_failed_login_attempts(ip_address: str):
    """Clear failed login attempts after successful login"""
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            DELETE FROM login_attempts WHERE ip_address = %s
        """, (ip_address,))
        db.commit()
        
    except Exception as e:
        print(f"Error clearing login attempts: {e}")


# =========================
# Username-Based Login Lockout Functions
# =========================

def check_username_lockout(username: str) -> tuple:
    """Check if username is locked out. Returns (is_locked, remaining_seconds, attempts)"""
    db = get_db()
    cursor = db.cursor()
    
    try:
        # Create table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS username_login_attempts (
                username VARCHAR(255) PRIMARY KEY,
                failed_attempts INT NOT NULL DEFAULT 0,
                lockout_until TIMESTAMP,
                last_attempt TIMESTAMP NOT NULL
            )
        """)
        db.commit()
        
        cursor.execute("""
            SELECT failed_attempts, lockout_until 
            FROM username_login_attempts 
            WHERE username = %s
        """, (username,))
        
        result = cursor.fetchone()
        
        if not result:
            print(f"DEBUG: No lockout record found for username '{username}'")
            return (False, 0, 0)
        
        failed_attempts = result['failed_attempts']
        lockout_until = result['lockout_until']
        
        print(f"DEBUG: Username '{username}' - attempts: {failed_attempts}, lockout_until: {lockout_until}, current_time: {datetime.utcnow()}")
        
        # Check if currently locked out
        if lockout_until and datetime.utcnow() < lockout_until:
            remaining_seconds = int((lockout_until - datetime.utcnow()).total_seconds())
            print(f"DEBUG: Username '{username}' IS LOCKED - remaining: {remaining_seconds}s")
            return (True, remaining_seconds, failed_attempts)
        
        print(f"DEBUG: Username '{username}' NOT LOCKED")
        return (False, 0, failed_attempts)
        
    except Exception as e:
        print(f"Error checking username lockout: {e}")
        return (False, 0, 0)


def record_failed_login_by_username(username: str):
    """Record a failed login attempt by username and apply lockout if needed"""
    db = get_db()
    cursor = db.cursor()
    
    try:
        # Get current attempts
        cursor.execute("""
            SELECT failed_attempts, lockout_until 
            FROM username_login_attempts 
            WHERE username = %s
        """, (username,))
        
        result = cursor.fetchone()
        
        if result:
            failed_attempts = result['failed_attempts']
            lockout_until = result['lockout_until']
            
            print(f"DEBUG: Recording failed login for '{username}' - current attempts: {failed_attempts}")
            
            # If lockout expired, reset counter
            if lockout_until and datetime.utcnow() >= lockout_until:
                print(f"DEBUG: Lockout expired for '{username}', resetting counter")
                failed_attempts = 0
            
            failed_attempts += 1
            print(f"DEBUG: Incremented attempts for '{username}' to {failed_attempts}")
            
            # Apply 2-minute lockout after 5 failed attempts
            if failed_attempts >= 5:
                lockout_until = datetime.utcnow() + timedelta(minutes=2)
                print(f"DEBUG: APPLYING LOCKOUT for '{username}' until {lockout_until}")
                cursor.execute("""
                    UPDATE username_login_attempts 
                    SET failed_attempts = %s, lockout_until = %s, last_attempt = %s
                    WHERE username = %s
                """, (failed_attempts, lockout_until, datetime.utcnow(), username))
            else:
                cursor.execute("""
                    UPDATE username_login_attempts 
                    SET failed_attempts = %s, last_attempt = %s
                    WHERE username = %s
                """, (failed_attempts, datetime.utcnow(), username))
        else:
            # First failed attempt for this username
            print(f"DEBUG: First failed login for '{username}'")
            cursor.execute("""
                INSERT INTO username_login_attempts (username, failed_attempts, last_attempt)
                VALUES (%s, 1, %s)
            """, (username, datetime.utcnow()))
        
        db.commit()
        print(f"DEBUG: Successfully committed failed login record for '{username}'")
        
    except Exception as e:
        print(f"Error recording failed login by username: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")


def clear_username_login_attempts(username: str):
    """Clear failed login attempts for username after successful login"""
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            DELETE FROM username_login_attempts WHERE username = %s
        """, (username,))
        db.commit()
        
    except Exception as e:
        print(f"Error clearing username login attempts: {e}")


def update_user_casino_balance(user_id: int, new_balance: int) -> bool:
    """Update user's casino balance"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Ensure balance doesn't go negative
        if new_balance < 0:
            new_balance = 0
        
        # First ensure the table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS casino_balances (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                balance INTEGER NOT NULL DEFAULT 1000,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        cursor.execute(
            """INSERT INTO casino_balances (user_id, balance) 
               VALUES (%s, %s) 
               ON CONFLICT (user_id) DO UPDATE SET balance = %s""",
            (user_id, new_balance, new_balance)
        )
        return True
    except Exception as e:
        print(f"Error updating casino balance: {e}")
        return False
