from flask import Blueprint, request, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from datetime import datetime
import logging
from app.chat_db import (
    save_chat_message, get_chat_history, get_recent_messages, 
    get_active_chat_sessions, mark_messages_as_read, cleanup_old_messages
)
from app.routes import generate_ai_response

# Initialize SocketIO
socketio = SocketIO()

# Track user modes (AI vs Human)
user_modes = {}

@socketio.on('connect')
def on_connect():
    """Handle client connection"""
    print(f"Client connected: {request.sid}")
    emit('status', {'msg': 'Connected to chat service'})

@socketio.on('disconnect')
def on_disconnect():
    """Handle client disconnection"""
    session_id = request.sid
    if session_id in user_modes:
        del user_modes[session_id]
    print(f"Client disconnected: {session_id}")

@socketio.on('join_chat')
def on_join_chat(data):
    """Handle user joining chat"""
    room = data.get('room', 'customer_service')
    session_id = request.sid
    user_id = session.get('user_id')
    username = session.get('username', 'Guest')
    user_email = session.get('email')
    
    print(f"User {username} joining chat room: {room}")
    
    # Join room
    join_room(room)
    
    # Set default mode to AI
    user_modes[session_id] = 'ai'
    
    # Load and send chat history
    try:
        chat_history = get_chat_history(
            session_id=session_id,
            user_id=user_id,
            room=room,
            limit=50
        )
        
        for msg in chat_history:
            emit('chat_message', {
                'id': msg['id'],
                'sender': msg['username'],
                'message': msg['message'],
                'sender_type': msg['sender_type'],
                'timestamp': msg['timestamp'].strftime('%H:%M'),
                'user_email': msg['user_email']
            })
            
        print(f"Loaded {len(chat_history)} messages from history")
        
    except Exception as e:
        print(f"Error loading chat history: {e}")
        logging.error(f"Error loading chat history for {session_id}: {e}")
    
    emit('status', {'msg': f'Joined {room} chat'})
    logging.info(f"User {username} ({session_id}) joined {room}")

@socketio.on('send_message')
def on_send_message(data):
    """Handle incoming chat messages"""
    room = data.get('room', 'customer_service')
    message = data.get('message', '').strip()
    session_id = request.sid
    user_id = session.get('user_id')
    username = session.get('username', 'Guest')
    user_email = session.get('email')
    
    if not message:
        return
    
    print(f"Message from {username}: {message}")
    
    # Save message to database
    save_chat_message(
        session_id=session_id,
        user_id=user_id,
        username=username,
        user_email=user_email,
        message=message,
        sender_type='user',
        room=room
    )
    
    # Broadcast message to room
    message_data = {
        'id': None,
        'sender': username,
        'message': message,
        'sender_type': 'user',
        'timestamp': datetime.now().strftime('%H:%M'),
        'user_email': user_email,
        'session_id': session_id
    }
    
    emit('chat_message', message_data, room=room, include_self=False)
    
    # Handle different modes
    if user_modes.get(session_id) == 'ai':
        # AI Mode: Generate AI response
        try:
            ai_response = generate_ai_response(message)
            
            # Save AI response to database
            save_chat_message(
                session_id=session_id,
                user_id=None,
                username='AI Support',
                user_email=None,
                message=ai_response,
                sender_type='ai',
                room=room
            )
            
            # Send AI response
            ai_message_data = {
                'id': None,
                'sender': 'AI Support',
                'message': ai_response,
                'sender_type': 'ai',
                'timestamp': datetime.now().strftime('%H:%M'),
                'user_email': None
            }
            
            emit('chat_message', ai_message_data, room=room)
            print(f"AI response sent: {ai_response[:50]}...")
            
        except Exception as e:
            print(f"Error generating AI response: {e}")
            logging.error(f"AI response error: {e}")
            
            # Send error message
            error_data = {
                'id': None,
                'sender': 'System',
                'message': "I'm having trouble processing your request. Please try again.",
                'sender_type': 'system',
                'timestamp': datetime.now().strftime('%H:%M'),
                'user_email': None
            }
            emit('chat_message', error_data, room=room)
    
    elif user_modes.get(session_id) == 'human':
        # Concierge Mode: Send to admin room
        admin_message_data = {
            'id': None,
            'sender': username,
            'message': message,
            'sender_type': 'user',
            'timestamp': datetime.now().strftime('%H:%M'),
            'user_email': user_email,
            'session_id': session_id,
            'room': room
        }
        
        # Send to admin monitoring room
        emit('admin_chat_notification', admin_message_data, room='admin_monitor')
        print(f"Concierge message sent to admin: {message[:50]}...")

@socketio.on('switch_mode')
def on_switch_mode(data):
    """Handle switching between AI and Human support modes"""
    mode = data.get('mode', 'ai')  # 'ai' or 'human'
    session_id = request.sid
    username = session.get('username', 'Guest')
    
    user_modes[session_id] = mode
    
    mode_text = "AI Support" if mode == 'ai' else "Concierge Support"
    system_message = f"Switched to {mode_text}"
    
    # Save system message
    save_chat_message(
        session_id=session_id,
        user_id=None,
        username='System',
        user_email=None,
        message=system_message,
        sender_type='system',
        room='customer_service'
    )
    
    # Send system message to user
    emit('chat_message', {
        'id': None,
        'sender': 'System',
        'message': system_message,
        'sender_type': 'system',
        'timestamp': datetime.now().strftime('%H:%M'),
        'user_email': None
    }, room='customer_service')
    
    # Notify admin if switching to concierge mode
    if mode == 'human':
        admin_notification = {
            'id': None,
            'sender': 'System',
            'message': f"User {username} switched to Concierge Support",
            'sender_type': 'system',
            'timestamp': datetime.now().strftime('%H:%M'),
            'user_email': None,
            'session_id': session_id,
            'username': username
        }
        emit('admin_chat_notification', admin_notification, room='admin_monitor')
        print(f"Admin notified: {username} switched to concierge mode")
    
    print(f"User {username} switched to {mode_text} mode")
    logging.info(f"User {username} switched to {mode} mode")

# Admin functions
@socketio.on('admin_join')
def on_admin_join(data):
    """Handle admin joining to monitor chats"""
    room = data.get('room', 'admin_monitor')
    admin_id = request.sid
    
    join_room(room)
    emit('status', {'msg': f'Admin joined monitoring room'})
    print(f"Admin {admin_id} joined monitoring room: {room}")

@socketio.on('admin_send_message')
def on_admin_send_message(data):
    """Handle admin sending messages to users"""
    target_room = data.get('room', 'customer_service')
    message = data.get('message', '').strip()
    admin_name = data.get('admin_name', 'Admin')
    target_session_id = data.get('session_id')
    
    if not message:
        return
    
    print(f"Admin message to {target_room}: {message}")
    
    # Save admin message to database
    save_chat_message(
        session_id='admin_panel',
        user_id=session.get('user_id'),
        username=admin_name,
        user_email=session.get('email'),
        message=message,
        sender_type='admin',
        room=target_room
    )
    
    # Send admin message
    admin_message_data = {
        'id': None,
        'sender': admin_name,
        'message': message,
        'sender_type': 'admin',
        'timestamp': datetime.now().strftime('%H:%M'),
        'user_email': session.get('email')
    }
    
    emit('chat_message', admin_message_data, room=target_room)
    print(f"Admin message sent to room: {target_room}")

@socketio.on('mark_read')
def on_mark_read(data):
    """Handle admin marking messages as read"""
    session_id = data.get('session_id')
    room = data.get('room', 'customer_service')
    
    mark_messages_as_read(session_id=session_id, room=room)
    emit('status', {'msg': 'Messages marked as read'})
    print(f"Messages marked as read for session: {session_id}")

# Initialize chat database
def init_chat():
    """Initialize chat system"""
    try:
        from app.chat_db import init_chat_db
        from app import create_app
        app = create_app()
        init_chat_db(app)
        print("Chat system initialized successfully")
    except Exception as e:
        print(f"Error initializing chat system: {e}")
        logging.error(f"Chat init error: {e}")

# Schedule cleanup
import threading
import time

def cleanup_scheduler():
    """Run cleanup of old messages periodically"""
    while True:
        try:
            cleanup_old_messages(hours=48)  # Delete messages older than 48 hours
        except Exception as e:
            print(f"Error in cleanup: {e}")
            logging.error(f"Cleanup error: {e}")
        
        time.sleep(3600)  # Run every hour

# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_scheduler, daemon=True)
cleanup_thread.start()
