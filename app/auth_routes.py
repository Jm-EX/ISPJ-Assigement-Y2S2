import re
import secrets
from datetime import datetime, timedelta, timezone

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_mail import Message
from werkzeug.security import check_password_hash, generate_password_hash

from app import mail
from app.auth_db import (
    create_otp_challenge,
    create_password_reset_token,
    create_user,
    delete_otp_challenge,
    delete_password_reset_token,
    get_otp_challenge,
    get_password_reset_token,
    get_user_by_email,
    get_user_by_id,
    get_user_by_username,
    increment_otp_attempts,
    update_user_password,
)


auth = Blueprint("auth", __name__)


def _password_errors(password: str, username: str):
    errors = []

    if len(password) < 12:
        errors.append("Password must be at least 12 characters long.")
    if " " in password:
        errors.append("Password must not contain spaces.")
    if not re.search(r"[a-z]", password):
        errors.append("Password must include a lowercase letter.")
    if not re.search(r"[A-Z]", password):
        errors.append("Password must include an uppercase letter.")
    if not re.search(r"\d", password):
        errors.append("Password must include a number.")
    if not re.search(r"[^A-Za-z0-9]", password):
        errors.append("Password must include a special character.")
    if username and username.lower() in password.lower():
        errors.append("Password must not contain your username.")

    return errors


def _send_otp_email(to_email: str, otp_code: str):
    mail_server = current_app.config.get("MAIL_SERVER")
    mail_username = current_app.config.get("MAIL_USERNAME")
    mail_password = current_app.config.get("MAIL_PASSWORD")

    current_app.logger.info(f"Attempting to send OTP to {to_email}")
    current_app.logger.info(f"Mail config - Server: {mail_server}, Username: {mail_username}, Password: {'***' if mail_password else None}")

    if not (mail_server and mail_username and mail_password):
        current_app.logger.warning(
            "SMTP not configured. OTP for %s is %s (dev fallback)", to_email, otp_code
        )
        return False

    try:
        current_app.logger.info("Creating email message...")
        msg = Message(
            subject="Your One-Time Password (OTP)",
            recipients=[to_email],
            body=f"Your OTP is: {otp_code}\n\nThis code will expire in 5 minutes."
        )
        current_app.logger.info("Sending email via Flask-Mail...")
        mail.send(msg)
        current_app.logger.info("Email sent successfully!")
        return True
    except Exception as e:
        current_app.logger.error("Failed to send OTP email: %s", str(e))
        current_app.logger.exception("Full traceback:")
        return False


def _send_password_reset_email(to_email: str, reset_link: str):
    mail_server = current_app.config.get("MAIL_SERVER")
    mail_username = current_app.config.get("MAIL_USERNAME")
    mail_password = current_app.config.get("MAIL_PASSWORD")

    if not (mail_server and mail_username and mail_password):
        current_app.logger.warning(
            "SMTP not configured. Password reset link for %s: %s", to_email, reset_link
        )
        return False

    try:
        msg = Message(
            subject="Password Reset Request",
            recipients=[to_email],
            body=f"Click the link below to reset your password:\n\n{reset_link}\n\nThis link will expire in 1 hour.\n\nIf you did not request a password reset, please ignore this email."
        )
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error("Failed to send password reset email: %s", str(e))
        return False


def _login_required():
    return bool(session.get("user_id"))


def _admin_required():
    return bool(session.get("user_id")) and bool(session.get("is_admin"))


@auth.get("/register")
def register_get():
    return render_template("register.html")


@auth.post("/register")
def register_post():
    username = (request.form.get("username") or "").strip()
    email = (request.form.get("email") or "").strip()
    password = request.form.get("password") or ""
    confirm = request.form.get("confirm_password") or ""

    if not username:
        flash("Username is required.", "error")
        return redirect(url_for("auth.register_get"))
    if not email:
        flash("Email is required.", "error")
        return redirect(url_for("auth.register_get"))
    if password != confirm:
        flash("Passwords do not match.", "error")
        return redirect(url_for("auth.register_get"))

    errors = _password_errors(password, username)
    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("auth.register_get"))

    if get_user_by_username(username) is not None:
        flash("Username is already taken.", "error")
        return redirect(url_for("auth.register_get"))

    try:
        create_user(username, email, generate_password_hash(password), is_admin=0)
    except Exception:
        current_app.logger.exception("Failed to create user")
        flash("Failed to create account. Email or username may already exist.", "error")
        return redirect(url_for("auth.register_get"))

    flash("Account created. Please log in.", "success")
    return redirect(url_for("auth.login_get"))


@auth.get("/login")
def login_get():
    return render_template("login.html")


@auth.post("/login")
def login_post():
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""

    user = get_user_by_username(username)
    if user is None or not check_password_hash(user["password_hash"], password):
        flash("Invalid username or password.", "error")
        return redirect(url_for("auth.login_get"))

    otp_code = f"{secrets.randbelow(1_000_000):06d}"
    otp_expires = datetime.now(timezone.utc) + timedelta(minutes=5)

    otp_token = secrets.token_urlsafe(32)
    create_otp_challenge(
        token=otp_token,
        user_id=int(user["id"]),
        otp_hash=generate_password_hash(otp_code),
        expires_at=otp_expires.isoformat(),
    )

    session["otp_token"] = otp_token

    sent = _send_otp_email(user["email"], otp_code)
    if sent:
        flash("OTP sent to your email.", "success")
    else:
        flash(
            "OTP email sending is not configured yet; check server logs for the OTP (dev mode).",
            "error",
        )

    return redirect(url_for("auth.verify_otp_get"))


@auth.get("/verify-otp")
def verify_otp_get():
    if not session.get("otp_token"):
        return redirect(url_for("auth.login_get"))
    return render_template("verify_otp.html")


@auth.post("/verify-otp")
def verify_otp_post():
    otp_token = session.get("otp_token")
    if not otp_token:
        return redirect(url_for("auth.login_get"))

    otp_input = (request.form.get("otp") or "").strip()

    challenge = get_otp_challenge(otp_token)
    if challenge is None:
        flash("OTP session not found. Please log in again.", "error")
        session.pop("otp_token", None)
        return redirect(url_for("auth.login_get"))

    try:
        expires = datetime.fromisoformat(challenge["expires_at"])
    except Exception:
        expires = datetime.now(timezone.utc) - timedelta(seconds=1)

    attempts = int(challenge["attempts"] or 0)
    if attempts >= 5:
        flash("Too many attempts. Please log in again.", "error")
        delete_otp_challenge(otp_token)
        session.pop("otp_token", None)
        return redirect(url_for("auth.login_get"))

    if datetime.now(timezone.utc) > expires:
        flash("OTP expired. Please log in again.", "error")
        delete_otp_challenge(otp_token)
        session.pop("otp_token", None)
        return redirect(url_for("auth.login_get"))

    if not check_password_hash(challenge["otp_hash"], otp_input):
        increment_otp_attempts(otp_token)
        flash("Invalid OTP.", "error")
        return redirect(url_for("auth.verify_otp_get"))

    user = get_user_by_id(int(challenge["user_id"]))
    if user is None:
        flash("User not found. Please log in again.", "error")
        delete_otp_challenge(otp_token)
        session.pop("otp_token", None)
        return redirect(url_for("auth.login_get"))

    delete_otp_challenge(otp_token)
    session.pop("otp_token", None)

    session["user_id"] = int(user["id"])
    session["username"] = user["username"]
    session["is_admin"] = bool(user["is_admin"])

    if session.get("is_admin"):
        return redirect(url_for("admin.portal"))
    return redirect(url_for("main.index"))


@auth.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.index"))


@auth.get("/forgot-password")
def forgot_password_get():
    return render_template("forgot_password.html")


@auth.post("/forgot-password")
def forgot_password_post():
    email = (request.form.get("email") or "").strip()

    if not email:
        flash("Email is required.", "error")
        return redirect(url_for("auth.forgot_password_get"))

    user = get_user_by_email(email)
    if user is None:
        flash("If that email exists in our system, a password reset link has been sent.", "success")
        return redirect(url_for("auth.login_get"))

    reset_token = secrets.token_urlsafe(32)
    reset_expires = datetime.now(timezone.utc) + timedelta(hours=1)

    create_password_reset_token(
        token=reset_token,
        user_id=int(user["id"]),
        expires_at=reset_expires.isoformat(),
    )

    reset_link = url_for("auth.reset_password_get", token=reset_token, _external=True)
    sent = _send_password_reset_email(email, reset_link)

    if sent:
        flash("If that email exists in our system, a password reset link has been sent.", "success")
    else:
        flash("Failed to send password reset email. Please try again later.", "error")

    return redirect(url_for("auth.login_get"))


@auth.get("/reset-password/<token>")
def reset_password_get(token):
    reset_token = get_password_reset_token(token)
    if reset_token is None:
        flash("Invalid or expired password reset link.", "error")
        return redirect(url_for("auth.login_get"))

    try:
        expires = datetime.fromisoformat(reset_token["expires_at"])
    except Exception:
        expires = datetime.now(timezone.utc) - timedelta(seconds=1)

    if datetime.now(timezone.utc) > expires:
        flash("Password reset link has expired.", "error")
        delete_password_reset_token(token)
        return redirect(url_for("auth.login_get"))

    return render_template("reset_password.html", token=token)


@auth.post("/reset-password/<token>")
def reset_password_post(token):
    reset_token = get_password_reset_token(token)
    if reset_token is None:
        flash("Invalid or expired password reset link.", "error")
        return redirect(url_for("auth.login_get"))

    try:
        expires = datetime.fromisoformat(reset_token["expires_at"])
    except Exception:
        expires = datetime.now(timezone.utc) - timedelta(seconds=1)

    if datetime.now(timezone.utc) > expires:
        flash("Password reset link has expired.", "error")
        delete_password_reset_token(token)
        return redirect(url_for("auth.login_get"))

    password = request.form.get("password") or ""
    confirm = request.form.get("confirm_password") or ""

    if password != confirm:
        flash("Passwords do not match.", "error")
        return redirect(url_for("auth.reset_password_get", token=token))

    user = get_user_by_id(int(reset_token["user_id"]))
    if user is None:
        flash("User not found.", "error")
        delete_password_reset_token(token)
        return redirect(url_for("auth.login_get"))

    if user["is_admin"]:
        flash("Admin account password cannot be changed.", "error")
        delete_password_reset_token(token)
        return redirect(url_for("auth.login_get"))

    errors = _password_errors(password, user["username"])
    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("auth.reset_password_get", token=token))

    update_user_password(int(user["id"]), generate_password_hash(password))
    delete_password_reset_token(token)

    flash("Password has been reset successfully. Please log in.", "success")
    return redirect(url_for("auth.login_get"))
