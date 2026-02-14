from flask import Blueprint, request, session, jsonify
from app.chat_db import get_active_chat_sessions, get_chat_history, mark_messages_as_read

# Create chat API blueprint
chat_api_bp = Blueprint('chat_api', __name__)

@chat_api_bp.get('/admin/api/active-chat-users')
def get_active_chat_users():
    """API endpoint for admin to get active chat users"""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        active_users = get_active_chat_sessions(hours=24)
        
        # Format users for frontend
        formatted_users = []
        for user in active_users:
            formatted_users.append({
                'session_id': user['session_id'],
                'username': user['username'],
                'email': user['user_email'] or 'No email',
                'room': user['room'],
                'last_message_time': user['last_message_time'].isoformat(),
                'unread_count': user['unread_count']
            })
        
        return jsonify({'success': True, 'users': formatted_users})
    except Exception as e:
        print(f"Error getting active users: {e}")
        return jsonify({'error': str(e)}), 500

@chat_api_bp.get('/admin/api/chat-history')
def get_chat_history_api():
    """API endpoint for admin to get chat history for a specific user"""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    session_id = request.args.get('session_id')
    room = request.args.get('room')
    limit = int(request.args.get('limit', 50))
    
    if not session_id or not room:
        return jsonify({'error': 'Missing session_id or room'}), 400
    
    try:
        chat_history = get_chat_history(session_id=session_id, room=room, limit=limit)
        
        # Format messages for frontend
        formatted_messages = []
        for msg in chat_history:
            formatted_messages.append({
                'id': msg['id'],
                'sender': msg['username'],
                'message': msg['message'],
                'sender_type': msg['sender_type'],
                'timestamp': msg['timestamp'].strftime('%H:%M'),
                'user_email': msg['user_email']
            })
        
        return jsonify({'success': True, 'messages': formatted_messages})
    except Exception as e:
        print(f"Error getting chat history: {e}")
        return jsonify({'error': str(e)}), 500

@chat_api_bp.post('/admin/api/mark-read')
def mark_messages_read():
    """API endpoint for admin to mark messages as read"""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    session_id = data.get('session_id')
    room = data.get('room')
    
    if not session_id or not room:
        return jsonify({'error': 'Missing session_id or room'}), 400
    
    try:
        mark_messages_as_read(session_id=session_id, room=room)
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error marking messages as read: {e}")
        return jsonify({'error': str(e)}), 500
