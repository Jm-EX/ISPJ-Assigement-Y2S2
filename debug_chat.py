#!/usr/bin/env python3
"""
Debug script to test chat functionality
Run this to identify any issues with the chat system
"""

import os
import sys

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

try:
    from app import create_app
    from app.auth_db import get_db, get_chat_stats, save_chat_message, get_chat_messages
    
    print("✅ Successfully imported all modules")
    
    # Create app and test database connection
    app = create_app()
    
    with app.app_context():
        try:
            db = get_db()
            print("✅ Database connection successful")
            
            # Test chat stats
            try:
                stats = get_chat_stats()
                print(f"✅ Chat stats: {stats}")
            except Exception as e:
                print(f"❌ Error getting chat stats: {e}")
            
            # Test saving a message
            try:
                save_chat_message(
                    session_id='debug_session',
                    user_id=None,
                    username='Debug User',
                    message='Test message for debugging',
                    sender_type='customer',
                    room='debug'
                )
                print("✅ Successfully saved test message")
            except Exception as e:
                print(f"❌ Error saving message: {e}")
            
            # Test retrieving messages
            try:
                messages = get_chat_messages(room='debug', limit=5)
                print(f"✅ Retrieved {len(messages)} messages")
                for msg in messages:
                    print(f"   - {msg['username']}: {msg['message'][:50]}...")
            except Exception as e:
                print(f"❌ Error retrieving messages: {e}")
            
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            
except ImportError as e:
    print(f"❌ Import error: {e}")
except Exception as e:
    print(f"❌ General error: {e}")

print("\nDebug complete!")
