import os
import sqlite3
from datetime import datetime

from flask import current_app, g
from werkzeug.security import generate_password_hash


def get_db():
    if "db" not in g:
        db_path = current_app.config["AUTH_DB_PATH"]
        g.db = sqlite3.connect(db_path, isolation_level=None)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app):
    os.makedirs(app.instance_path, exist_ok=True)
    db_path = app.config["AUTH_DB_PATH"]

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS otp_challenges (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                otp_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def seed_admin(app):
    username = "Admin1!"
    password = "Admin1!"
    email = app.config.get("ADMIN_EMAIL", "admin@example.com")

    conn = sqlite3.connect(app.config["AUTH_DB_PATH"])
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        )
        if cursor.fetchone() is None:
            return
        
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO users (username, email, password_hash, is_admin, created_at)
                VALUES (?, ?, ?, 1, ?)
                """,
                (
                    username,
                    email,
                    generate_password_hash(password),
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()
    finally:
        conn.close()


def get_user_by_username(username: str):
    db = get_db()
    return db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def get_user_by_id(user_id: int):
    db = get_db()
    return db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def create_user(username: str, email: str, password_hash: str, is_admin: int = 0):
    db = get_db()
    db.execute(
        """
        INSERT INTO users (username, email, password_hash, is_admin, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (username, email, password_hash, int(is_admin), datetime.utcnow().isoformat()),
    )
    db.commit()


def create_otp_challenge(
    token: str,
    user_id: int,
    otp_hash: str,
    expires_at: str,
):
    db = get_db()
    db.execute(
        """
        INSERT INTO otp_challenges (token, user_id, otp_hash, expires_at, attempts, created_at)
        VALUES (?, ?, ?, ?, 0, ?)
        """,
        (token, int(user_id), otp_hash, expires_at, datetime.utcnow().isoformat()),
    )
    db.commit()


def get_otp_challenge(token: str):
    db = get_db()
    return db.execute(
        "SELECT * FROM otp_challenges WHERE token = ?", (token,)
    ).fetchone()


def increment_otp_attempts(token: str):
    db = get_db()
    db.execute(
        "UPDATE otp_challenges SET attempts = attempts + 1 WHERE token = ?", (token,)
    )
    db.commit()


def delete_otp_challenge(token: str):
    db = get_db()
    db.execute("DELETE FROM otp_challenges WHERE token = ?", (token,))
    db.commit()


def get_user_by_email(email: str):
    db = get_db()
    return db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()


def create_password_reset_token(token: str, user_id: int, expires_at: str):
    db = get_db()
    db.execute(
        """
        INSERT INTO password_reset_tokens (token, user_id, expires_at, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (token, int(user_id), expires_at, datetime.utcnow().isoformat()),
    )
    db.commit()


def get_password_reset_token(token: str):
    db = get_db()
    return db.execute(
        "SELECT * FROM password_reset_tokens WHERE token = ?", (token,)
    ).fetchone()


def delete_password_reset_token(token: str):
    db = get_db()
    db.execute("DELETE FROM password_reset_tokens WHERE token = ?", (token,))
    db.commit()


def update_user_password(user_id: int, password_hash: str):
    db = get_db()
    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, int(user_id))
    )
    db.commit()
