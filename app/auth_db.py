import pymysql
from datetime import datetime
from flask import current_app, g, request
from werkzeug.security import generate_password_hash


def get_db():
    if "db" not in g:
        g.db = pymysql.connect(
            host=current_app.config["MYSQL_HOST"],
            port=current_app.config["MYSQL_PORT"],
            user=current_app.config["MYSQL_USER"],
            password=current_app.config["MYSQL_PASSWORD"],
            database=current_app.config["MYSQL_DATABASE"],
            autocommit=True,
            cursorclass=pymysql.cursors.DictCursor
        )
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app):
    conn = pymysql.connect(
        host=app.config["MYSQL_HOST"],
        port=app.config["MYSQL_PORT"],
        user=app.config["MYSQL_USER"],
        password=app.config["MYSQL_PASSWORD"],
        autocommit=True
    )
    try:
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {app.config['MYSQL_DATABASE']}")
        cursor.execute(f"USE {app.config['MYSQL_DATABASE']}")
        
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(255) NOT NULL UNIQUE,
                email VARCHAR(255) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                is_admin TINYINT NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS otp_challenges (
                token VARCHAR(255) PRIMARY KEY,
                user_id INT NOT NULL,
                otp_hash VARCHAR(255) NOT NULL,
                expires_at DATETIME NOT NULL,
                attempts INT NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                token VARCHAR(255) PRIMARY KEY,
                user_id INT NOT NULL,
                expires_at DATETIME NOT NULL,
                created_at DATETIME NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS passkey_credentials (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                credential_id TEXT NOT NULL,
                public_key TEXT NOT NULL,
                sign_count INT NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS security_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT,
                username VARCHAR(255),
                event_type VARCHAR(255) NOT NULL,
                ip_address VARCHAR(255),
                user_agent TEXT,
                details TEXT,
                created_at DATETIME NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
    finally:
        conn.close()


def seed_admin(app):
    username = "Admin1!"
    password = "Admin1!"
    email = app.config.get("ADMIN_EMAIL", "admin@example.com")

    conn = pymysql.connect(
        host=app.config["MYSQL_HOST"],
        port=app.config["MYSQL_PORT"],
        user=app.config["MYSQL_USER"],
        password=app.config["MYSQL_PASSWORD"],
        database=app.config["MYSQL_DATABASE"],
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor
    )
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) as count FROM information_schema.tables WHERE table_schema = %s AND table_name = 'users'",
            (app.config["MYSQL_DATABASE"],)
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


def log_security_event(user_id, username, event_type, details=None):
    db = get_db()
    cursor = db.cursor()
    ip_address = request.remote_addr if request else None
    user_agent = request.headers.get('User-Agent') if request else None
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
    cursor.execute("SELECT id, username, email, is_admin, role, permissions, created_at FROM users ORDER BY created_at DESC")
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
    cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))


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
    cursor.execute("SELECT role, permissions FROM users WHERE id = %s", (user_id,))
    result = cursor.fetchone()
    if result and result.get('permissions'):
        import json
        try:
            result['permissions'] = json.loads(result['permissions'])
        except:
            result['permissions'] = {}
    return result


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
