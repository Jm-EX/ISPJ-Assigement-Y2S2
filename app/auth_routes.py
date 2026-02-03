import base64
import json
import re
import secrets
from datetime import datetime, timedelta, timezone

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_mail import Message
from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
    options_to_json,
)
from webauthn.helpers.structs import (
    PublicKeyCredentialDescriptor,
    UserVerificationRequirement,
)
from webauthn.helpers.cose import COSEAlgorithmIdentifier
from werkzeug.security import check_password_hash, generate_password_hash

from app import mail, limiter
from app.auth_db import (
    create_otp_challenge,
    create_passkey_credential,
    create_password_reset_token,
    create_user,
    delete_otp_challenge,
    delete_passkey_credential,
    delete_password_reset_token,
    get_otp_challenge,
    get_passkey_by_credential_id,
    get_passkey_credentials,
    get_password_reset_token,
    get_user_by_email,
    get_user_by_id,
    get_user_by_username,
    increment_otp_attempts,
    update_passkey_sign_count,
    update_user_password,
    log_security_event,
    set_totp_secret,
    get_totp_secret,
)


auth = Blueprint("auth", __name__, url_prefix="/auth")


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
    print("\n" + "="*80)
    print("DEBUG: _send_otp_email function called")
    print(f"DEBUG: Recipient: {to_email}")
    print(f"DEBUG: OTP Code: {otp_code}")
    print("="*80)
    
    mail_server = current_app.config.get("MAIL_SERVER")
    mail_port = current_app.config.get("MAIL_PORT")
    mail_username = current_app.config.get("MAIL_USERNAME")
    mail_password = current_app.config.get("MAIL_PASSWORD")
    mail_use_tls = current_app.config.get("MAIL_USE_TLS")
    mail_use_ssl = current_app.config.get("MAIL_USE_SSL")
    mail_default_sender = current_app.config.get("MAIL_DEFAULT_SENDER")

    print(f"DEBUG: MAIL_SERVER = {mail_server}")
    print(f"DEBUG: MAIL_PORT = {mail_port}")
    print(f"DEBUG: MAIL_USERNAME = {mail_username}")
    print(f"DEBUG: MAIL_PASSWORD = {'***' + mail_password[-4:] if mail_password else None}")
    print(f"DEBUG: MAIL_USE_TLS = {mail_use_tls}")
    print(f"DEBUG: MAIL_USE_SSL = {mail_use_ssl}")
    print(f"DEBUG: MAIL_DEFAULT_SENDER = {mail_default_sender}")

    current_app.logger.info(f"Attempting to send OTP to {to_email}")
    current_app.logger.info(f"Mail config - Server: {mail_server}, Port: {mail_port}, Username: {mail_username}, Password: {'***' if mail_password else None}")

    if not (mail_server and mail_username and mail_password):
        print("DEBUG: SMTP NOT CONFIGURED - Missing required values")
        print(f"DEBUG: mail_server exists: {bool(mail_server)}")
        print(f"DEBUG: mail_username exists: {bool(mail_username)}")
        print(f"DEBUG: mail_password exists: {bool(mail_password)}")
        current_app.logger.warning(
            "SMTP not configured. OTP for %s is %s (dev fallback)", to_email, otp_code
        )
        print("="*80 + "\n")
        return False

    try:
        print("DEBUG: Creating email message...")
        current_app.logger.info("Creating email message...")
        msg = Message(
            subject="Your One-Time Password (OTP)",
            recipients=[to_email],
            body=f"Your OTP is: {otp_code}\n\nThis code will expire in 5 minutes."
        )
        print(f"DEBUG: Message created - Subject: {msg.subject}, Recipients: {msg.recipients}")
        print("DEBUG: Attempting to send email via Flask-Mail...")
        current_app.logger.info("Sending email via Flask-Mail...")
        
        mail.send(msg)
        
        print("DEBUG: Email sent successfully!")
        current_app.logger.info("Email sent successfully!")
        print("="*80 + "\n")
        return True
    except Exception as e:
        print(f"DEBUG: EXCEPTION OCCURRED: {type(e).__name__}")
        print(f"DEBUG: Exception message: {str(e)}")
        current_app.logger.error("Failed to send OTP email: %s", str(e))
        current_app.logger.exception("Full traceback:")
        import traceback
        print("DEBUG: Full traceback:")
        traceback.print_exc()
        print("="*80 + "\n")
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
@limiter.limit("5 per minute")
def login_post():
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""

    user = get_user_by_username(username)
    
    # Check for account lockout if user exists
    if user:
        from app.auth_db import check_account_lockout
        ip_address = request.remote_addr
        user_agent = request.headers.get('User-Agent', '')
        user_role = user.get('role')  # Get user role for threshold determination
        is_locked, remaining_time = check_account_lockout(user["id"], ip_address, user_agent, user_role)
        
        if is_locked:
            flash(f"Account temporarily locked due to multiple failed attempts. Please try again in {remaining_time}.", "error")
            return redirect(url_for("auth.login_get"))
    
    if user is None or not check_password_hash(user["password_hash"], password):
        # Increment failed attempts if user exists
        if user:
            from app.auth_db import increment_failed_attempts_by_user
            ip_address = request.remote_addr
            user_agent = request.headers.get('User-Agent', '')
            increment_failed_attempts_by_user(user["id"], ip_address, user_agent)
        
        log_security_event(None, username, 'login_failed', 'Invalid credentials')
        flash("Invalid username or password.", "error")
        return redirect(url_for("auth.login_get"))

    passkeys = get_passkey_credentials(user["id"])
    
    if passkeys:
        session["pending_login_user_id"] = user["id"]
        session["pending_login_username"] = username
        return redirect(url_for("auth.verify_passkey_get"))

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


@auth.get("/verify-passkey")
def verify_passkey_get():
    if not session.get("pending_login_user_id"):
        return redirect(url_for("auth.login_get"))
    return render_template("verify_passkey.html", username=session.get("pending_login_username"))


@auth.get("/passkey/login-complete")
def passkey_login_complete():
    if not session.get("pending_login_user_id"):
        flash("Invalid session.", "error")
        return redirect(url_for("auth.login_get"))
    
    user_id = session.pop("pending_login_user_id")
    session.pop("pending_login_username", None)
    
    user = get_user_by_id(user_id)
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("auth.login_get"))
    
    session["user_id"] = int(user["id"])
    session["username"] = user["username"]
    session["is_admin"] = bool(user["is_admin"])
    
    if session.get("is_admin"):
        return redirect(url_for("admin.portal"))
    return redirect(url_for("main.index"))


@auth.get("/use-otp-instead")
def use_otp_instead():
    if not session.get("pending_login_user_id"):
        return redirect(url_for("auth.login_get"))
    
    user_id = session.pop("pending_login_user_id")
    username = session.pop("pending_login_username")
    
    user = get_user_by_id(user_id)
    if not user:
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
    
    msg = Message(
        subject="Your OTP Code",
        sender=current_app.config["SMTP_FROM"],
        recipients=[user["email"]],
    )
    msg.body = f"Your OTP code is: {otp_code}\n\nThis code will expire in 5 minutes."
    mail.send(msg)
    
    flash("OTP sent to your email.", "success")
    return redirect(url_for("auth.verify_otp_get"))


@auth.get("/setup-totp")
def setup_totp_get():
    if not session.get("pending_totp_user_id"):
        return redirect(url_for("auth.login_get"))
    
    user_id = session["pending_totp_user_id"]
    user = get_user_by_id(user_id)
    
    import pyotp
    totp_secret = pyotp.random_base32()
    set_totp_secret(user_id, totp_secret)
    
    totp_uri = pyotp.totp.TOTP(totp_secret).provisioning_uri(
        name=user["username"],
        issuer_name="ISPJ Hotel"
    )
    
    import qrcode
    import io
    import base64
    
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(totp_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    qr_code_base64 = base64.b64encode(buffer.getvalue()).decode()
    
    return render_template("setup_totp.html", qr_code=qr_code_base64, secret=totp_secret)


@auth.post("/setup-totp")
def setup_totp_post():
    if not session.get("pending_totp_user_id"):
        return redirect(url_for("auth.login_get"))
    
    user_id = session["pending_totp_user_id"]
    totp_code = request.form.get("totp_code", "").strip()
    
    totp_secret = get_totp_secret(user_id)
    if not totp_secret:
        flash("TOTP setup error. Please try again.", "error")
        return redirect(url_for("auth.login_get"))
    
    import pyotp
    totp = pyotp.TOTP(totp_secret)
    
    if not totp.verify(totp_code):
        flash("Invalid TOTP code. Please try again.", "error")
        return render_template("setup_totp.html", qr_code="", secret=totp_secret)
    
    user = get_user_by_id(user_id)
    
    # Set session data FIRST before popping pending_totp_user_id
    session.permanent = True
    session["user_id"] = int(user["id"])
    session["username"] = user["username"]
    session["is_admin"] = bool(user["is_admin"])
    
    # Now pop the pending flag
    session.pop("pending_totp_user_id", None)
    
    from app.auth_db import update_last_login, create_or_update_session, send_high_risk_alert
    update_last_login(user["id"])
    
    # Track session with risk scoring - use request.sid (actual Flask session ID)
    session_token = request.sid if hasattr(request, 'sid') else session.get('_id', str(user["id"]))
    print(f"DEBUG: TOTP setup - session_token = {session_token}")
    print(f"DEBUG: TOTP setup - request.sid = {getattr(request, 'sid', 'NOT AVAILABLE')}")
    print(f"DEBUG: TOTP setup - session._id = {session.get('_id')}")
    
    ip_address = request.remote_addr
    user_agent = request.headers.get('User-Agent', '')
    total_risk_score = create_or_update_session(user["id"], session_token, ip_address, user_agent)
    
    # Send email alert if total risk score >= 6
    if total_risk_score >= 6:
        send_high_risk_alert(user["username"], total_risk_score)
    
    log_security_event(user["id"], user["username"], 'login_success', 'TOTP setup completed')
    
    flash("Microsoft Authenticator setup successful!", "success")
    return redirect(url_for("admin.portal"))


@auth.get("/verify-totp")
def verify_totp_get():
    if not session.get("pending_totp_user_id"):
        return redirect(url_for("auth.login_get"))
    return render_template("verify_totp.html")


@auth.post("/verify-totp")
@limiter.limit("10 per minute")
def verify_totp_post():
    if not session.get("pending_totp_user_id"):
        return redirect(url_for("auth.login_get"))
    
    user_id = session["pending_totp_user_id"]
    totp_code = request.form.get("totp_code", "").strip()
    
    totp_secret = get_totp_secret(user_id)
    if not totp_secret:
        flash("TOTP not set up. Please contact administrator.", "error")
        return redirect(url_for("auth.login_get"))
    
    import pyotp
    totp = pyotp.TOTP(totp_secret)
    
    if not totp.verify(totp_code):
        flash("Invalid TOTP code. Please try again.", "error")
        return redirect(url_for("auth.verify_totp_get"))
    
    user = get_user_by_id(user_id)
    
    # Set session data FIRST before popping pending_totp_user_id
    session.permanent = True
    session["user_id"] = int(user["id"])
    session["username"] = user["username"]
    session["is_admin"] = bool(user["is_admin"])
    
    # Now pop the pending flag
    session.pop("pending_totp_user_id", None)
    
    from app.auth_db import update_last_login, create_or_update_session, send_high_risk_alert
    update_last_login(user["id"])
    
    # Track session with risk scoring - use request.sid (actual Flask session ID)
    session_token = request.sid if hasattr(request, 'sid') else session.get('_id', str(user["id"]))
    print(f"DEBUG: TOTP verify - session_token = {session_token}")
    print(f"DEBUG: TOTP verify - request.sid = {getattr(request, 'sid', 'NOT AVAILABLE')}")
    print(f"DEBUG: TOTP verify - session._id = {session.get('_id')}")
    
    ip_address = request.remote_addr
    user_agent = request.headers.get('User-Agent', '')
    total_risk_score = create_or_update_session(user["id"], session_token, ip_address, user_agent)
    
    # Send email alert if total risk score >= 6
    if total_risk_score >= 6:
        send_high_risk_alert(user["username"], total_risk_score)
    
    log_security_event(user["id"], user["username"], 'login_success', 'TOTP verification successful')
    
    return redirect(url_for("admin.portal"))


@auth.get("/verify-otp")
def verify_otp_get():
    if not session.get("otp_token"):
        return redirect(url_for("auth.login_get"))
    return render_template("verify_otp.html")


@auth.post("/verify-otp")
@limiter.limit("10 per minute")
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

    expires = challenge["expires_at"]
    if isinstance(expires, str):
        try:
            expires = datetime.fromisoformat(expires)
        except Exception:
            expires = datetime.now(timezone.utc) - timedelta(seconds=1)
    
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

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

    # Check if this is Admin1! and requires TOTP
    if user["username"] == "Admin1!":
        totp_secret = get_totp_secret(user["id"])
        if not totp_secret:
            # First time - need to set up TOTP
            session["pending_totp_user_id"] = user["id"]
            return redirect(url_for("auth.setup_totp_get"))
        else:
            # TOTP already set up - verify it
            session["pending_totp_user_id"] = user["id"]
            return redirect(url_for("auth.verify_totp_get"))

    session.permanent = True
    session["user_id"] = int(user["id"])
    session["username"] = user["username"]
    session["is_admin"] = bool(user["is_admin"])
    
    from app.auth_db import update_last_login, create_or_update_session, send_high_risk_alert
    update_last_login(user["id"])
    
    # Track session with risk scoring - use request.sid (actual Flask session ID)
    session_token = request.sid if hasattr(request, 'sid') else session.get('_id', str(user["id"]))
    print(f"DEBUG: Regular login - session_token = {session_token}")
    print(f"DEBUG: Regular login - request.sid = {getattr(request, 'sid', 'NOT AVAILABLE')}")
    print(f"DEBUG: Regular login - session._id = {session.get('_id')}")
    
    ip_address = request.remote_addr
    user_agent = request.headers.get('User-Agent', '')
    total_risk_score = create_or_update_session(user["id"], session_token, ip_address, user_agent)
    
    # Send email alert if total risk score >= 6
    if total_risk_score >= 6:
        send_high_risk_alert(user["username"], total_risk_score)
    
    log_security_event(user["id"], user["username"], 'login_success', 'OTP verification successful')

    if session.get("is_admin"):
        return redirect(url_for("admin.portal"))
    return redirect(url_for("main.index"))


@auth.get("/logout")
def logout():
    from app.auth_db import log_security_event
    
    # Log logout event before clearing session
    user_id = session.get("user_id")
    username = session.get("username")
    
    if user_id and username:
        log_security_event(user_id, username, 'logout', 'User initiated logout')
    
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

    expires = reset_token["expires_at"]
    if isinstance(expires, str):
        try:
            expires = datetime.fromisoformat(expires)
        except Exception:
            expires = datetime.now(timezone.utc) - timedelta(seconds=1)
    
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

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

    expires = reset_token["expires_at"]
    if isinstance(expires, str):
        try:
            expires = datetime.fromisoformat(expires)
        except Exception:
            expires = datetime.now(timezone.utc) - timedelta(seconds=1)
    
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

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


@auth.get("/profile")
def profile_get():
    if not session.get("user_id"):
        flash("Please log in to view your profile.", "error")
        return redirect(url_for("auth.login_get"))
    
    user = get_user_by_id(session["user_id"])
    if not user:
        session.clear()
        return redirect(url_for("auth.login_get"))
    
    passkeys = get_passkey_credentials(session["user_id"])
    
    return render_template("profile.html", 
                         username=user["username"], 
                         email=user["email"],
                         passkeys=passkeys)


@auth.post("/passkey/register/begin")
def passkey_register_begin():
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
    
    user = get_user_by_id(session["user_id"])
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    try:
        user_id_bytes = str(user["id"]).encode('utf-8')
        
        from webauthn.helpers.structs import AttestationConveyancePreference
        
        # Get the hostname without port for rp_id
        hostname = request.host.split(':')[0]
        # WebAuthn requires localhost for local development, not 127.0.0.1
        if hostname == "127.0.0.1":
            rp_id = "localhost"
        else:
            rp_id = hostname
        
        options = generate_registration_options(
            rp_id=rp_id,
            rp_name="ISPJ Hotel",
            user_id=user_id_bytes,
            user_name=user["username"],
            user_display_name=user["username"],
            attestation=AttestationConveyancePreference.NONE,
            supported_pub_key_algs=[
                COSEAlgorithmIdentifier.ECDSA_SHA_256,
                COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
            ],
        )
        
        session["passkey_challenge"] = base64.urlsafe_b64encode(options.challenge).decode('utf-8').rstrip('=')
        
        options_json = options_to_json(options)
        options_dict = json.loads(options_json)
        options_dict["challenge"] = base64.urlsafe_b64encode(options.challenge).decode('utf-8').rstrip('=')
        options_dict["user"]["id"] = base64.urlsafe_b64encode(user_id_bytes).decode('utf-8').rstrip('=')
        
        return jsonify(options_dict)
    except Exception as e:
        current_app.logger.error(f"Passkey registration begin error: {str(e)}")
        import traceback
        current_app.logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@auth.post("/passkey/register/complete")
def passkey_register_complete():
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
    
    if not session.get("passkey_challenge"):
        return jsonify({"error": "No challenge found"}), 400
    
    try:
        credential = request.get_json()
        
        print("=" * 80)
        print("PASSKEY REGISTRATION - Received credential:")
        print(f"Credential: {credential}")
        print(f"Credential keys: {credential.keys() if credential else 'None'}")
        print("=" * 80)
        
        current_app.logger.info(f"Received credential: {credential}")
        current_app.logger.info(f"Credential keys: {credential.keys() if credential else 'None'}")
        
        if not credential:
            print("ERROR: No credential data received")
            return jsonify({"error": "No credential data received"}), 400
        
        if "rawId" not in credential:
            print(f"ERROR: rawId missing. Received keys: {list(credential.keys())}")
            print(f"Full credential: {json.dumps(credential, indent=2)}")
            current_app.logger.error(f"rawId missing. Full credential: {json.dumps(credential, indent=2)}")
            return jsonify({"error": f"Credential missing required rawId. Received keys: {list(credential.keys())}"}), 400
        
        print("Step 1: Getting challenge from session...")
        challenge = session.get("passkey_challenge")
        if not challenge:
            print("ERROR: No challenge in session")
            return jsonify({"error": "Challenge expired or already used"}), 400
        print(f"Challenge retrieved: {challenge[:20]}...")
        
        print("Step 2: Decoding challenge...")
        challenge_bytes = base64.urlsafe_b64decode(challenge + '==')
        print(f"Challenge bytes length: {len(challenge_bytes)}")
        
        print("Step 3: Extracting credential data...")
        credential_id = credential["rawId"]
        client_data = credential["response"]["clientDataJSON"]
        attestation = credential["response"]["attestationObject"]
        print(f"Credential ID: {credential_id[:20]}...")
        
        print("Step 4: Decoding credential data...")
        client_data_bytes = base64.urlsafe_b64decode(client_data + '==')
        attestation_bytes = base64.urlsafe_b64decode(attestation + '==')
        raw_id_bytes = base64.urlsafe_b64decode(credential_id + '==')
        print(f"Raw ID bytes length: {len(raw_id_bytes)}")
        
        print("Step 5: Setting up rp_id...")
        # Get the hostname without port for rp_id
        hostname = request.host.split(':')[0]
        # WebAuthn requires localhost for local development, not 127.0.0.1
        if hostname == "127.0.0.1":
            rp_id = "localhost"
            # Origin must use localhost too when rp_id is localhost
            expected_origin = f"{request.scheme}://localhost:{request.host.split(':')[1]}" if ':' in request.host else f"{request.scheme}://localhost"
        else:
            rp_id = hostname
            expected_origin = f"{request.scheme}://{request.host}"
        print(f"RP ID: {rp_id}")
        print(f"Origin: {expected_origin}")
        
        print("Step 6: Verifying registration response...")
        verification = verify_registration_response(
            credential={
                "id": credential["id"],
                "rawId": credential_id,
                "response": {
                    "clientDataJSON": client_data,
                    "attestationObject": attestation,
                },
                "type": "public-key",
            },
            expected_challenge=challenge_bytes,
            expected_origin=expected_origin,
            expected_rp_id=rp_id,
        )
        print("Verification successful!")
        
        print("Step 7: Extracting public key...")
        public_key_bytes = verification.credential_public_key
        public_key_b64 = base64.b64encode(public_key_bytes).decode('utf-8')
        print(f"Public key length: {len(public_key_b64)}")
        
        print("Step 8: Saving credential to database...")
        create_passkey_credential(
            user_id=session["user_id"],
            credential_id=credential["id"],
            public_key=public_key_b64
        )
        print("Credential saved!")
        
        print("Step 9: Cleaning up session...")
        session.pop("passkey_challenge", None)
        
        print("SUCCESS: Passkey registration complete!")
        print("=" * 80)
        return jsonify({"success": True})
    
    except Exception as e:
        print(f"ERROR OCCURRED: {str(e)}")
        import traceback
        print("FULL TRACEBACK:")
        print(traceback.format_exc())
        print("=" * 80)
        current_app.logger.error(f"Passkey registration error: {str(e)}")
        current_app.logger.error(f"Full traceback: {traceback.format_exc()}")
        return jsonify({"success": False, "error": str(e)}), 400


@auth.post("/passkey/delete")
def passkey_delete():
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
    
    data = request.get_json()
    credential_id = data.get("credential_id")
    
    if not credential_id:
        return jsonify({"error": "No credential ID provided"}), 400
    
    passkey = get_passkey_by_credential_id(credential_id)
    if not passkey or passkey["user_id"] != session["user_id"]:
        return jsonify({"error": "Passkey not found"}), 404
    
    delete_passkey_credential(credential_id)
    
    return jsonify({"success": True})


@auth.post("/passkey/authenticate/begin")
def passkey_authenticate_begin():
    username = request.get_json().get("username")
    
    if not username:
        return jsonify({"error": "Username required"}), 400
    
    user = get_user_by_username(username)
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    passkeys = get_passkey_credentials(user["id"])
    if not passkeys:
        return jsonify({"error": "No passkeys registered"}), 404
    
    # Get the hostname without port for rp_id
    hostname = request.host.split(':')[0]
    # WebAuthn requires localhost for local development, not 127.0.0.1
    if hostname == "127.0.0.1":
        rp_id = "localhost"
    else:
        rp_id = hostname
    
    allow_credentials = [
        PublicKeyCredentialDescriptor(id=base64.urlsafe_b64decode(p["credential_id"] + '=='))
        for p in passkeys
    ]
    
    options = generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=allow_credentials,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    
    session["passkey_auth_challenge"] = base64.urlsafe_b64encode(options.challenge).decode('utf-8').rstrip('=')
    session["passkey_auth_user_id"] = user["id"]
    
    options_dict = json.loads(options_to_json(options))
    options_dict["challenge"] = base64.urlsafe_b64encode(options.challenge).decode('utf-8').rstrip('=')
    
    return jsonify(options_dict)


@auth.post("/passkey/authenticate/complete")
def passkey_authenticate_complete():
    if not session.get("passkey_auth_challenge"):
        return jsonify({"error": "No challenge found"}), 400
    
    try:
        credential = request.get_json()
        
        challenge = session.pop("passkey_auth_challenge")
        user_id = session.pop("passkey_auth_user_id")
        challenge_bytes = base64.urlsafe_b64decode(challenge + '==')
        
        passkey = get_passkey_by_credential_id(credential["id"])
        if not passkey or passkey["user_id"] != user_id:
            return jsonify({"error": "Invalid credential"}), 400
        
        public_key_bytes = base64.b64decode(passkey["public_key"])
        
        credential_id = credential["rawId"]
        client_data = credential["response"]["clientDataJSON"]
        authenticator_data = credential["response"]["authenticatorData"]
        signature = credential["response"]["signature"]
        
        client_data_bytes = base64.urlsafe_b64decode(client_data + '==')
        authenticator_data_bytes = base64.urlsafe_b64decode(authenticator_data + '==')
        signature_bytes = base64.urlsafe_b64decode(signature + '==')
        
        # Get the hostname without port for rp_id
        hostname = request.host.split(':')[0]
        # WebAuthn requires localhost for local development, not 127.0.0.1
        if hostname == "127.0.0.1":
            rp_id = "localhost"
            # Origin must use localhost too when rp_id is localhost
            expected_origin = f"{request.scheme}://localhost:{request.host.split(':')[1]}" if ':' in request.host else f"{request.scheme}://localhost"
        else:
            rp_id = hostname
            expected_origin = f"{request.scheme}://{request.host}"
        
        verification = verify_authentication_response(
            credential={
                "id": credential["id"],
                "rawId": credential_id,
                "response": {
                    "clientDataJSON": client_data,
                    "authenticatorData": authenticator_data,
                    "signature": signature,
                },
                "type": "public-key",
            },
            expected_challenge=challenge_bytes,
            expected_origin=expected_origin,
            expected_rp_id=rp_id,
            credential_public_key=public_key_bytes,
            credential_current_sign_count=passkey["sign_count"],
        )
        
        update_passkey_sign_count(credential["id"], verification.new_sign_count)
        
        return jsonify({"success": True, "user_id": user_id})
    
    except Exception as e:
        current_app.logger.error(f"Passkey authentication error: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 400
