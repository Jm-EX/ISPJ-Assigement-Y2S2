import psycopg
from psycopg.rows import dict_row
from datetime import datetime
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


def seed_admin(app):
    username = "Admin1!"
    password = "Admin1!"
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
    cursor.execute("DELETE FROM passkey_credentials WHERE user_id = %s", (user_id,))
    cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
    db.commit()


def create_sub_admin(username: str, email: str, password_hash: str, role: str, permissions: dict):
    db = get_db()
    cursor = db.cursor()
    import json
    cursor.execute(
        """
        INSERT INTO users (username, email, password_hash, is_admin, role, permissions, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (username, email, password_hash, True, role, json.dumps(permissions), datetime.utcnow())
    )
    return cursor.lastrowid


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
