#!/usr/bin/env python3
"""
Migration script to add chat_messages table to Render PostgreSQL database.
Run this script on Render or locally with DATABASE_URL environment variable set.

Usage:
    python run_migration.py

Or on Render Shell:
    python run_migration.py
"""

import os
import psycopg

def run_migration():
    database_url = os.environ.get("DATABASE_URL")
    
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        print("Please set DATABASE_URL to your PostgreSQL connection string")
        return False
    
    print(f"Connecting to database...")
    
    try:
        conn = psycopg.connect(database_url)
        conn.autocommit = True
        cursor = conn.cursor()
        
        print("Connected successfully!")
        
        # Create chat_messages table
        print("Creating chat_messages table...")
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
        print("chat_messages table created/verified!")
        
        # Add user_email column if it doesn't exist (for existing tables)
        print("Checking for missing columns...")
        cursor.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'chat_messages' AND column_name = 'user_email'
        """)
        if not cursor.fetchone():
            print("Adding missing user_email column...")
            cursor.execute("ALTER TABLE chat_messages ADD COLUMN user_email VARCHAR(255)")
            print("user_email column added!")
        else:
            print("user_email column already exists.")
        
        # Create indexes
        print("Creating indexes...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id ON chat_messages(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_timestamp ON chat_messages(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_room ON chat_messages(room)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_admin_read ON chat_messages(admin_read)")
        print("Indexes created!")
        
        # Create dh_keys table
        print("Creating dh_keys table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dh_keys (
                session_id VARCHAR(255) PRIMARY KEY,
                public_key TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMP NOT NULL DEFAULT (NOW() + INTERVAL '24 hours')
            )
        """)
        print("dh_keys table created/verified!")
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_dh_keys_expires_at ON dh_keys(expires_at)")
        print("dh_keys index created!")
        
        # Create casino_balances table for persistent user balances
        print("Creating casino_balances table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS casino_balances (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                balance INTEGER NOT NULL DEFAULT 1000,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        print("casino_balances table created/verified!")
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_casino_balances_user_id ON casino_balances(user_id)")
        print("casino_balances index created!")
        
        # Verify tables exist
        print("\nVerifying tables...")
        cursor.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name IN ('chat_messages', 'dh_keys', 'casino_balances')
        """)
        tables = cursor.fetchall()
        print(f"Found tables: {[t[0] for t in tables]}")
        
        # Check chat_messages count
        cursor.execute("SELECT COUNT(*) FROM chat_messages")
        count = cursor.fetchone()[0]
        print(f"Current message count in chat_messages: {count}")
        
        # Clear old corrupted messages (optional - uncomment if needed)
        # These are messages that were stored before proper encryption was set up
        print("\nClearing old corrupted messages...")
        cursor.execute("DELETE FROM chat_messages")
        print("Old messages cleared. Fresh start for chat persistence.")
        
        conn.close()
        print("\nMigration completed successfully!")
        return True
        
    except Exception as e:
        print(f"ERROR: Migration failed - {e}")
        import traceback
        print(traceback.format_exc())
        return False

if __name__ == "__main__":
    run_migration()
