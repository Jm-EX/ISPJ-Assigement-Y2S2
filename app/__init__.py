from flask import Flask
from flask_mail import Mail
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
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
    CORS(app, resources={
        r"/*": {
            "origins": "*",
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            "supports_credentials": False
        }
    })

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
    
    # DEBUG: Print SMTP configuration on startup
    print("\n" + "="*80)
    print("DEBUG: SMTP CONFIGURATION ON STARTUP")
    print("="*80)
    print(f"SMTP_SERVER env var: {os.environ.get('SMTP_SERVER')}")
    print(f"SMTP_PORT env var: {os.environ.get('SMTP_PORT')}")
    print(f"SMTP_USERNAME env var: {os.environ.get('SMTP_USERNAME')}")
    print(f"SMTP_PASSWORD env var: {'***' + os.environ.get('SMTP_PASSWORD', '')[-4:] if os.environ.get('SMTP_PASSWORD') else None}")
    print(f"SMTP_USE_TLS env var: {os.environ.get('SMTP_USE_TLS')}")
    print(f"SMTP_FROM env var: {os.environ.get('SMTP_FROM')}")
    print(f"\nApp config MAIL_SERVER: {app.config['MAIL_SERVER']}")
    print(f"App config MAIL_PORT: {app.config['MAIL_PORT']}")
    print(f"App config MAIL_USERNAME: {app.config['MAIL_USERNAME']}")
    print(f"App config MAIL_PASSWORD: {'***' + app.config['MAIL_PASSWORD'][-4:] if app.config.get('MAIL_PASSWORD') else None}")
    print(f"App config MAIL_USE_TLS: {app.config['MAIL_USE_TLS']}")
    print(f"App config MAIL_USE_SSL: {app.config['MAIL_USE_SSL']}")
    print(f"App config MAIL_DEFAULT_SENDER: {app.config['MAIL_DEFAULT_SENDER']}")
    print("="*80 + "\n")
    
    # reCAPTCHA configuration
    app.config["RECAPTCHA_SITE_KEY"] = os.environ.get("RECAPTCHA_SITE_KEY")
    app.config["RECAPTCHA_SECRET_KEY"] = os.environ.get("RECAPTCHA_SECRET_KEY")
    
    print("\n" + "="*80)
    print("DEBUG: reCAPTCHA Configuration")
    print(f"DEBUG: RECAPTCHA_SITE_KEY present: {bool(app.config['RECAPTCHA_SITE_KEY'])}")
    print(f"DEBUG: RECAPTCHA_SECRET_KEY present: {bool(app.config['RECAPTCHA_SECRET_KEY'])}")
    if app.config['RECAPTCHA_SITE_KEY']:
        print(f"DEBUG: RECAPTCHA_SITE_KEY: {app.config['RECAPTCHA_SITE_KEY'][:20]}...")
    print("="*80 + "\n")

    print("DEBUG: Initializing Flask-Mail...")
    mail.init_app(app)
    print("DEBUG: Flask-Mail initialized successfully")
    
    print("DEBUG: Initializing Flask-Limiter...")
    limiter.init_app(app)
    print("DEBUG: Flask-Limiter initialized successfully\n")

    from app.routes import main
    app.register_blueprint(main)

    from app.auth_routes import auth
    app.register_blueprint(auth)

    from app.admin_routes import admin
    app.register_blueprint(admin)

    from app.auth_db import close_db, init_db, seed_admin, remove_master_admin_passkeys
    app.teardown_appcontext(close_db)
    init_db(app)
    seed_admin(app)
    # Remove any existing passkey credentials for Master admin account
    remove_master_admin_passkeys()

    @app.before_request
    def handle_preflight():
        from flask import request
        if request.method == "OPTIONS":
            response = app.make_default_options_response()
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
            return response

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
            print("\n" + "="*80)
            print(f"DEBUG: validate_session - endpoint: {request.endpoint}")
            print(f"DEBUG: validate_session - user_id: {user_id}")
            print(f"DEBUG: validate_session - session keys: {list(session.keys())}")
            print(f"DEBUG: validate_session - session._id: {session.get('_id')}")
            print(f"DEBUG: validate_session - request.sid: {getattr(request, 'sid', 'NOT AVAILABLE')}")
            
            # Check if session exists in active_sessions table
            db = get_db()
            cursor = db.cursor()
            
            # Use request.sid as session token (this is the actual Flask session ID)
            session_token = request.sid if hasattr(request, 'sid') else session.get('_id', str(user_id))
            print(f"DEBUG: validate_session - session_token to check: {session_token}")
            
            cursor.execute(
                "SELECT id, session_token FROM active_sessions WHERE user_id = %s AND session_token = %s",
                (user_id, session_token)
            )
            
            result = cursor.fetchone()
            print(f"DEBUG: validate_session - found session: {result}")
            
            if not result:
                # Debug: Check what sessions exist for this user
                cursor.execute(
                    "SELECT session_token FROM active_sessions WHERE user_id = %s",
                    (user_id,)
                )
                all_sessions = cursor.fetchall()
                print(f"DEBUG: validate_session - all sessions for user {user_id}: {all_sessions}")
                print("="*80 + "\n")
                
                # Session was deleted by admin or expired - force logout with message
                session.clear()
                flash("Your session has expired. Please log in again.", "warning")
                return redirect(url_for('auth.login_get'))
            
            print("DEBUG: validate_session - session valid!")
            print("="*80 + "\n")

    @app.after_request
    def set_security_headers(response):
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.socket.io https://cdnjs.cloudflare.com https://unpkg.com https://cdn.jsdelivr.net https://www.google.com https://www.gstatic.com; style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://unpkg.com https://cdn.jsdelivr.net; img-src 'self' data: https:; font-src 'self' https://cdnjs.cloudflare.com; connect-src 'self' ws: wss: https: http://localhost:5001 http://127.0.0.1:5001 https://ispj-assigement-y2s2.onrender.com; frame-src https://www.google.com; frame-ancestors 'none';"
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response

    return app
