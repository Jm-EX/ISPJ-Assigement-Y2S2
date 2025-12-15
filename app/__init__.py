from flask import Flask
from flask_mail import Mail
import os

mail = Mail()

def create_app():
    app = Flask(__name__)

    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
    
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

    return app
