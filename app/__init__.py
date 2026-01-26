from flask import Flask
from flask_mail import Mail
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from datetime import timedelta
import os

mail = Mail()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

def create_app():
    app = Flask(__name__)

    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=5)
    
    app.config["MYSQL_HOST"] = os.environ.get("MYSQL_HOST", "localhost")
    app.config["MYSQL_PORT"] = int(os.environ.get("MYSQL_PORT", 3306))
    app.config["MYSQL_USER"] = os.environ.get("MYSQL_USER", "root")
    app.config["MYSQL_PASSWORD"] = os.environ.get("MYSQL_PASSWORD", "")
    app.config["MYSQL_DATABASE"] = os.environ.get("MYSQL_DATABASE", "ispj_hotel")

    app.config["MAIL_SERVER"] = os.environ.get("SMTP_SERVER")
    app.config["MAIL_PORT"] = int(os.environ.get("SMTP_PORT", 587))
    app.config["MAIL_USERNAME"] = os.environ.get("SMTP_USERNAME")
    app.config["MAIL_PASSWORD"] = os.environ.get("SMTP_PASSWORD")
    app.config["MAIL_USE_TLS"] = os.environ.get("SMTP_USE_TLS", "1") == "1"
    app.config["MAIL_USE_SSL"] = False
    app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("SMTP_FROM")
    app.config["ADMIN_EMAIL"] = os.environ.get("ADMIN_EMAIL", "admin@example.com")

    mail.init_app(app)
    limiter.init_app(app)

    from app.routes import main
    app.register_blueprint(main)

    from app.auth_routes import auth
    app.register_blueprint(auth)

    from app.admin_routes import admin
    app.register_blueprint(admin)

    from app.auth_db import close_db, init_db, seed_admin
    app.teardown_appcontext(close_db)
    init_db(app)
    seed_admin(app)

    @app.before_request
    def validate_session():
        from flask import session, request, flash, redirect, url_for
        from app.auth_db import get_db
        
        # Skip validation for static files and auth routes
        if request.endpoint and (request.endpoint.startswith('static') or request.endpoint.startswith('auth.')):
            return
        
        # Check if user is logged in
        user_id = session.get('user_id')
        if user_id:
            # Check if session exists in active_sessions table
            db = get_db()
            cursor = db.cursor()
            
            # Use Flask session ID as session token
            session_token = session.get('_id', str(user_id))
            
            cursor.execute(
                "SELECT id FROM active_sessions WHERE user_id = %s AND session_token = %s",
                (user_id, session_token)
            )
            
            if not cursor.fetchone():
                # Session was deleted by admin or expired - force logout with message
                session.clear()
                flash("Your session has expired. Please log in again.", "warning")
                return redirect(url_for('auth.login_get'))

    @app.after_request
    def set_security_headers(response):
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; img-src 'self' data:; font-src 'self' https://cdnjs.cloudflare.com; connect-src 'self'; frame-ancestors 'none';"
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    return app
