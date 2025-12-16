from flask import Blueprint, redirect, render_template, session, url_for, request, jsonify, flash
from app.auth_db import get_login_stats, get_all_users, delete_user, get_security_logs, create_sub_admin, update_user_role, get_user_permissions
from werkzeug.security import generate_password_hash


admin = Blueprint("admin", __name__)


@admin.get("/admin")
def portal():
    if not session.get("user_id"):
        return redirect(url_for("auth.login_get"))
    if not session.get("is_admin"):
        return redirect(url_for("main.index"))
    
    stats = get_login_stats()
    users = get_all_users()
    security_logs = get_security_logs(limit=50)
    
    return render_template("admin_portal.html", stats=stats, users=users, security_logs=security_logs)


@admin.post("/admin/delete-user/<int:user_id>")
def delete_user_route(user_id):
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
    if not session.get("is_admin"):
        return jsonify({"error": "Not authorized"}), 403
    
    if user_id == session.get("user_id"):
        return jsonify({"error": "Cannot delete your own account"}), 400
    
    delete_user(user_id)
    return jsonify({"success": True})


@admin.post("/admin/create-sub-admin")
def create_sub_admin_route():
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
    if not session.get("is_admin"):
        return jsonify({"error": "Not authorized"}), 403
    
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
    
    data = request.get_json()
    role = data.get("role", "sub_admin")
    permissions = data.get("permissions", {})
    
    try:
        update_user_role(user_id, role, permissions)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400
