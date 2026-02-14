from flask import Blueprint, redirect, render_template, session, url_for, request, jsonify, flash
from app.auth_db import get_login_stats, get_all_users, delete_user, get_security_logs, create_sub_admin, update_user_role, get_user_permissions, get_active_sessions, delete_session, save_chat_message, get_chat_messages, mark_chat_messages_as_read, get_chat_stats
from werkzeug.security import generate_password_hash
from datetime import datetime
import json


admin = Blueprint("admin", __name__)


def check_permission(user_id, permission_name):
    """Check if user has a specific permission. Super admins always have all permissions."""
    user_perms = get_user_permissions(user_id)
    if not user_perms:
        return False
    
    role = user_perms.get('role')
    # Super admin or master admin (no role set) has all permissions
    if role is None or role == 'super_admin' or role == 'master_admin':
        return True
    
    # Sub-admins need specific permissions
    permissions = user_perms.get('permissions', {})
    if isinstance(permissions, str):
        try:
            permissions = json.loads(permissions)
        except:
            permissions = {}
    
    return permissions.get(permission_name, False)


@admin.get("/admin")
def portal():
    if not session.get("user_id"):
        return redirect(url_for("auth.login_get"))
    if not session.get("is_admin"):
        return redirect(url_for("main.index"))
    
    stats = get_login_stats()
    users = get_all_users()
    security_logs = get_security_logs(limit=50)
    chat_stats = get_chat_stats()
    
    # Get active sessions - master admin always has access, sub-admins need permission
    active_sessions = []
    current_user_id = session.get("user_id")
    user_perms = get_user_permissions(current_user_id)
    role = user_perms.get('role') if user_perms else None
    
    # Master admin (role=None) or users with view_active_sessions permission can see sessions
    if role is None or role == 'super_admin' or role == 'master_admin' or check_permission(current_user_id, 'view_active_sessions'):
        active_sessions = get_active_sessions()
    
    return render_template("admin_portal.html", stats=stats, users=users, security_logs=security_logs, active_sessions=active_sessions, chat_stats=chat_stats)


@admin.post("/admin/delete-user/<int:user_id>")
def delete_user_route(user_id):
    print(f"\n{'='*80}")
    print(f"ADMIN DEBUG: delete_user_route called for user_id: {user_id}")
    
    if not session.get("user_id"):
        print(f"ADMIN DEBUG: Not authenticated")
        return jsonify({"error": "Not authenticated"}), 401
    if not session.get("is_admin"):
        print(f"ADMIN DEBUG: Not authorized")
        return jsonify({"error": "Not authorized"}), 403
    
    # Check if user has permission to delete users
    current_user_id = session.get("user_id")
    print(f"ADMIN DEBUG: Current user_id: {current_user_id}")
    
    # Master admin (role=None) and super admins always have permission
    # Sub-admins need explicit delete_user permission
    if not check_permission(current_user_id, 'delete_user'):
        print(f"ADMIN DEBUG: No permission to delete users")
        return jsonify({"error": "You do not have permission to delete users"}), 403
    
    if user_id == session.get("user_id"):
        print(f"ADMIN DEBUG: Cannot delete own account")
        return jsonify({"error": "Cannot delete your own account"}), 400
    
    # Prevent deletion of master admin account (Admin1!)
    from app.auth_db import get_user_by_id
    target_user = get_user_by_id(user_id)
    print(f"ADMIN DEBUG: Target user: {target_user.get('username') if target_user else 'None'}")
    if target_user and target_user.get('username') == 'Admin1!':
        print(f"ADMIN DEBUG: Cannot delete master admin")
        return jsonify({"error": "Cannot delete the master admin account"}), 403
    
    try:
        print(f"ADMIN DEBUG: Calling delete_user({user_id})")
        delete_user(user_id)
        print(f"ADMIN DEBUG: delete_user completed successfully")
        print(f"{'='*80}\n")
        return jsonify({"success": True})
    except Exception as e:
        print(f"ADMIN ERROR: Exception in delete_user_route: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"ADMIN ERROR: Traceback: {traceback.format_exc()}")
        print(f"{'='*80}\n")
        return jsonify({"error": str(e)}), 500


@admin.post("/admin/create-sub-admin")
def create_sub_admin_route():
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
    if not session.get("is_admin"):
        return jsonify({"error": "Not authorized"}), 403
    
    # Only super admin can create users (sub-admins cannot)
    current_user_id = session.get("user_id")
    user_perms = get_user_permissions(current_user_id)
    role = user_perms.get('role') if user_perms else None
    
    if role is not None and role != 'super_admin' and role != 'master_admin':
        return jsonify({"error": "Only super admin can create users"}), 403
    
    data = request.get_json()
    username = data.get("username", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "")
    role = data.get("role", "sub_admin")
    permissions = data.get("permissions", {})
    
    if not username or not email or not password:
        return jsonify({"error": "All fields are required"}), 400
    
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    
    try:
        password_hash = generate_password_hash(password)
        user_id = create_sub_admin(username, email, password_hash, role, permissions)
        return jsonify({"success": True, "user_id": user_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@admin.post("/admin/update-permissions/<int:user_id>")
def update_permissions_route(user_id):
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
    if not session.get("is_admin"):
        return jsonify({"error": "Not authorized"}), 403
    
    # Only super admin can update permissions (sub-admins cannot)
    current_user_id = session.get("user_id")
    user_perms = get_user_permissions(current_user_id)
    role = user_perms.get('role') if user_perms else None
    
    if role is not None and role != 'super_admin' and role != 'master_admin':
        return jsonify({"error": "Only super admin can update permissions"}), 403
    
    data = request.get_json()
    role = data.get("role", "sub_admin")
    permissions = data.get("permissions", {})
    
    try:
        update_user_role(user_id, role, permissions)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@admin.post("/admin/logout-session/<int:session_id>")
def logout_session_route(session_id):
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
    if not session.get("is_admin"):
        return jsonify({"error": "Not authorized"}), 403
    
    # Check if user has permission to view active sessions (same permission required to logout)
    current_user_id = session.get("user_id")
    user_perms = get_user_permissions(current_user_id)
    role = user_perms.get('role') if user_perms else None
    
    # Master admin or users with view_active_sessions permission can logout sessions
    if role is None or role == 'super_admin' or role == 'master_admin' or check_permission(current_user_id, 'view_active_sessions'):
        delete_session(session_id)
        return jsonify({"success": True})
    else:
        return jsonify({"error": "You do not have permission to logout sessions"}), 403


# =========================
# Chat Management Routes
# =========================

@admin.get("/admin/chat-messages")
def get_chat_messages_route():
    """Get chat messages for admin dashboard"""
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
    if not session.get("is_admin"):
        return jsonify({"error": "Not authorized"}), 403
    
    room = request.args.get("room")
    limit = int(request.args.get("limit", 50))
    unread_only = request.args.get("unread_only", "false").lower() == "true"
    
    try:
        messages = get_chat_messages(room=room, limit=limit, unread_only=unread_only)
        return jsonify({"success": True, "messages": messages})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin.post("/admin/mark-chat-read")
def mark_chat_read_route():
    """Mark chat messages as read"""
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
    if not session.get("is_admin"):
        return jsonify({"error": "Not authorized"}), 403
    
    room = request.json.get("room") if request.is_json else request.form.get("room")
    
    try:
        mark_chat_messages_as_read(room=room)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin.post("/admin/send-chat")
def send_chat_route():
    """Send chat message as admin"""
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
    if not session.get("is_admin"):
        return jsonify({"error": "Not authorized"}), 403
    
    data = request.get_json()
    message = data.get("message", "").strip()
    room = data.get("room", "default")
    
    if not message:
        return jsonify({"error": "Message cannot be empty"}), 400
    
    try:
        # Save to database
        save_chat_message(
            session_id=request.sid if hasattr(request, 'sid') else 'admin',
            user_id=session.get("user_id"),
            username=session.get("username", "Admin"),
            message=message,
            sender_type="admin",
            room=room
        )
        
        # Note: Socket.IO emission will be handled by the client-side JavaScript
        # that calls this endpoint and then refreshes the chat messages
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
