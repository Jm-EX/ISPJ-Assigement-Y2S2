from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, jsonify
from werkzeug.utils import secure_filename
from PIL import Image
import logging
import os
from datetime import datetime
import random
import stripe
import requests
from flask_socketio import SocketIO, emit, join_room, leave_room
import google.generativeai as genai
import base64
import json
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from app.auth_db import save_chat_message, get_chat_history, mark_messages_as_read, store_dh_public_key, get_dh_public_key, get_db, get_all_chat_sessions

# =========================
# Setup
# =========================

os.makedirs('logs', exist_ok=True)

logging.basicConfig(
    filename='logs/bookings.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# =========================
# Encryption Utilities
# =========================

import os
import base64
import json
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

def generate_encryption_key(password: str, salt: bytes = None) -> bytes:
    """Generate encryption key from password using simple SHA-256 (matches client)"""
    import hashlib
    # Use simple SHA-256 hash to match client-side
    return hashlib.sha256(password.encode()).digest()

def encrypt_message(message: dict, key: bytes) -> str:
    """Encrypt a message using AES-GCM (matches client-side)"""
    try:
        # Generate random IV (12 bytes for GCM)
        iv = os.urandom(12)
        
        # Convert message to JSON then bytes
        json_message = json.dumps(message)
        message_bytes = json_message.encode('utf-8')
        
        # Create AES-GCM cipher
        cipher = Cipher(
            algorithms.AES(key),
            modes.GCM(iv),
            backend=default_backend()
        )
        encryptor = cipher.encryptor()
        
        # Encrypt the message
        encrypted_message = encryptor.update(message_bytes) + encryptor.finalize()
        
        # Get authentication tag
        tag = encryptor.tag
        
        # Combine IV + tag + encrypted message
        combined = iv + tag + encrypted_message
        
        # Convert to base64
        return base64.b64encode(combined).decode('utf-8')
    except Exception as e:
        print(f"DEBUG: Encryption error: {e}")
        return None

def decrypt_message(encrypted_message: str, key: bytes) -> dict:
    """Decrypt a message using AES-GCM (matches client-side)"""
    try:
        # Decode from base64
        combined = base64.b64decode(encrypted_message.encode('utf-8'))
        
        # Extract IV (first 12 bytes), tag (next 16 bytes), and encrypted data
        iv = combined[:12]
        tag = combined[12:28]
        encrypted_data = combined[28:]
        
        # Create AES-GCM cipher
        cipher = Cipher(
            algorithms.AES(key),
            modes.GCM(iv, tag),
            backend=default_backend()
        )
        decryptor = cipher.decryptor()
        
        # Decrypt the message
        decrypted_bytes = decryptor.update(encrypted_data) + decryptor.finalize()
        
        # Convert back to JSON
        decrypted_message = decrypted_bytes.decode('utf-8')
        return json.loads(decrypted_message)
    except Exception as e:
        print(f"DEBUG: Decryption error: {e}")
        return None

# Store encryption keys for active sessions (in production, use a more secure method)
session_keys = {}  # {session_id: encryption_key}

def get_session_key(session_id: str) -> bytes:
    """Get or create encryption key for a session"""
    if session_id not in session_keys:
        # Generate a unique key for this session
        # In production, you might want to use a more sophisticated key exchange
        password = f"session_{session_id}_{datetime.now().strftime('%Y%m%d')}"
        session_keys[session_id] = generate_encryption_key(password)
    return session_keys[session_id]

main = Blueprint('main', __name__)

# Stripe test secret key
stripe.api_key = 'sk_test_51SeUJR2OsU80dT1Yw27XKOVnYeA8JgICdgfkNgRo5wZ2n5TuEXi3IFLffC1bsSm8UAgchYJFvkrAw8BF72rWxtyE00MY1LodZ7'

# Configure Gemini AI
gemini_api_key = os.environ.get('GEMINI_API_KEY')
print("\n" + "="*80)
print("DEBUG: Gemini AI Initialization")
print(f"DEBUG: API Key present: {bool(gemini_api_key)}")
if gemini_api_key:
    print(f"DEBUG: API Key length: {len(gemini_api_key)}")
    print(f"DEBUG: API Key starts with: {gemini_api_key[:10]}...")
print("="*80 + "\n")
logging.info(f"Gemini API Key loaded: {bool(gemini_api_key)}")

# Global list to store working models
working_models = []

if gemini_api_key:
    try:
        genai.configure(api_key=gemini_api_key)
        print("DEBUG: Gemini API configured successfully")
        
        # List available models to debug
        try:
            print("DEBUG: Listing available models...")
            models = genai.list_models()
            available_models = [model.name for model in models if 'generateContent' in model.supported_generation_methods]
            print(f"DEBUG: Available models: {available_models}")
            logging.info(f"Available models: {available_models}")
            
            # Test all desired models
            models_to_test = [
                'gemini-2.5-flash',
                'gemini-2.5-flash-lite',
                'gemini-2.5-flash-preview-tts',
                'gemini-3-flash-preview',
                'gemini-robotics-er-1.5-preview',
                'gemini-2.0-flash', 
                'gemini-1.5-flash',
                'gemini-pro-latest'
            ]
            
            print("DEBUG: Testing all desired models...")
            for model_name in models_to_test:
                try:
                    test_model = genai.GenerativeModel(model_name)
                    # Try a simple test request
                    test_response = test_model.generate_content("Hello")
                    if test_response.text:
                        working_models.append(model_name)
                        print(f"DEBUG: ✓ {model_name} - WORKING")
                    else:
                        print(f"DEBUG: ✗ {model_name} - No response")
                except Exception as e:
                    print(f"DEBUG: ✗ {model_name} - FAILED: {str(e)}")
            
            if working_models:
                print(f"DEBUG: Found {len(working_models)} working models: {working_models}")
                logging.info(f"Working models: {working_models}")
                # Set primary model to first working one
                gemini_model = genai.GenerativeModel(working_models[0])
                print(f"DEBUG: Primary model set to: {working_models[0]}")
            else:
                print("DEBUG: No working models found, using fallback")
                # Fallback to first available model
                if available_models:
                    first_model = available_models[0].replace('models/', '')
                    gemini_model = genai.GenerativeModel(first_model)
                    print(f"DEBUG: Using fallback model: {first_model}")
                    logging.info(f"Using fallback model: {first_model}")
                else:
                    gemini_model = None
            
            print("DEBUG: Gemini AI configured successfully")
            logging.info("Gemini AI configured successfully")
        except Exception as e:
            print(f"DEBUG: Error listing models: {type(e).__name__}: {str(e)}")
            logging.error(f"Error listing models: {str(e)}")
            # Fallback to gemini-pro
            gemini_model = genai.GenerativeModel('gemini-pro')
            print("DEBUG: Using fallback model: gemini-pro")
            logging.info("Using fallback model: gemini-pro")
    except Exception as e:
        print(f"DEBUG: Error configuring Gemini API: {type(e).__name__}: {str(e)}")
        logging.error(f"Error configuring Gemini API: {str(e)}")
        gemini_model = None
else:
    print("DEBUG: Gemini API Key not found in environment variables")
    logging.error("Gemini API Key not found in environment variables")
    gemini_model = None

# =========================
# Resort locaiton
# =========================
resorts = [
    {"name": "Pulau Tekong Resort", "lat": 1.40412, "lng": 104.05001},
    {"name": "Toa Payoh Resort", "lat": 1.3325, "lng": 103.8500},
    {"name": "Upper Thomson Resort", "lat": 1.3636, "lng": 103.8143},
]


# =========================
# Pages
# =========================

@main.route("/")
def index():
    return render_template("home.html", resorts=resorts)

@main.route("/book")
def book_room():
    return render_template("book_room.html")

@main.route("/other")
def others():
    return render_template("other.html")

# =========================
# Helpers
# =========================

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "pdf"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# =========================
# Booking Form
# =========================

@main.route("/book/<room_type>", methods=["GET", "POST"])
def book_room_confirm(room_type):
    if request.method == "POST":
        check_in = request.form.get("check_in")
        check_out = request.form.get("check_out")

        check_in_date = datetime.strptime(check_in, "%Y-%m-%d")
        check_out_date = datetime.strptime(check_out, "%Y-%m-%d")
        nights = (check_out_date - check_in_date).days

        # Store booking data in session
        room_prices = {
            "Deluxe Room": 229,
            "Luxury Suite": 299,
            "Executive Suite": 399,
        }

        booking_data = {
            "room_type": room_type,
            "check_in": check_in,
            "check_out": check_out,
            "nights": nights,
            "guest_name": request.form.get("full_name"),
            "email": request.form.get("email"),
            "phone": request.form.get("phone"),
            "total_price": room_prices.get(room_type, 0) * nights,
        }

        # Handle passport upload
        passport = request.files.get("passport")
        if passport and allowed_file(passport.filename):
            # Create uploads directory if it doesn't exist
            upload_folder = os.path.join('app', 'static', 'uploads', 'passports')
            os.makedirs(upload_folder, exist_ok=True)
            
            # Generate secure filename
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            filename = f"{timestamp}_{secure_filename(passport.filename)}"
            filepath = os.path.join(upload_folder, filename)
            
            file_ext = passport.filename.rsplit('.', 1)[1].lower()
            
            # Validate image files with Pillow
            if file_ext in ['jpg', 'jpeg', 'png']:
                try:
                    img = Image.open(passport)
                    img.verify()  # Verify image integrity
                    passport.seek(0)  # Reset pointer for saving
                except Exception:
                    flash('Uploaded file is not a valid image', 'error')
                    logging.warning(f"Invalid file upload attempt by {request.form.get('full_name')} ({request.form.get('email')})")
                    return redirect(request.url)
            
            # Save the file
            passport.save(filepath)
            booking_data["passport_file"] = filename
        elif passport:
            flash('Invalid file type. Only PDF, JPG, JPEG, PNG allowed.', 'error')
            logging.warning(f"Invalid file upload attempt by {request.form.get('full_name')} ({request.form.get('email')})")
            return redirect(request.url)

        session["booking_data"] = booking_data

        # reCAPTCHA verification
        recaptcha_response = request.form.get('g-recaptcha-response')
        print("\n" + "="*80)
        print("DEBUG: reCAPTCHA Verification")
        print(f"DEBUG: recaptcha_response present: {bool(recaptcha_response)}")
        
        if not recaptcha_response:
            print("DEBUG: reCAPTCHA response missing from form")
            print("="*80 + "\n")
            flash('Please complete the reCAPTCHA', 'error')
            return redirect(request.url)

        secret_key = os.environ.get('RECAPTCHA_SECRET_KEY')
        print(f"DEBUG: RECAPTCHA_SECRET_KEY present: {bool(secret_key)}")
        
        verify_response = requests.post(
            'https://www.google.com/recaptcha/api/siteverify',
            data={'secret': secret_key, 'response': recaptcha_response}
        )
        
        verification_result = verify_response.json()
        print(f"DEBUG: Google verification result: {verification_result}")
        print("="*80 + "\n")

        if not verification_result.get('success'):
            flash('reCAPTCHA verification failed', 'error')
            return redirect(request.url)

        # CREATE STRIPE CHECKOUT SESSION
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": int(booking_data["total_price"] * 100),
                        "product_data": {
                            "name": f"{room_type} Booking",
                        },
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=url_for("main.booking_confirmation", _external=True),
            cancel_url=url_for("main.book_room_confirm", room_type=room_type, _external=True),
        )

        return redirect(checkout_session.url, code=303)

    return render_template("booking_confirm.html", room_type=room_type, config=current_app.config)


# =========================
# Payment
# =========================

@main.route("/payment")
def payment_page():
    booking_data = session.get("booking_data")
    if not booking_data:
        flash("No booking found", "error")
        return redirect(url_for("main.book_room"))
    return render_template("payment.html", booking=booking_data)

@main.route("/create-checkout-session", methods=["POST"])
def create_checkout_session():
    booking_data = session.get("booking_data")
    if not booking_data:
        flash("No booking found", "error")
        return redirect(url_for("main.book_room"))

    checkout_session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "usd",
                "unit_amount": int(booking_data["total_price"] * 100),
                "product_data": {
                    "name": f"{booking_data['room_type']} Booking"
                }
            },
            "quantity": 1
        }],
        mode="payment",
        success_url=url_for("main.booking_confirmation", _external=True),
        cancel_url=url_for("main.payment_page", _external=True),
    )

    return redirect(checkout_session.url, code=303)

# =========================
# Confirmation
# =========================

@main.route("/booking/confirmation")
def booking_confirmation():
    booking_data = session.get("booking_data")
    if not booking_data:
        flash("No booking found", "error")
        return redirect(url_for("main.book_room"))
    return render_template("booking_confirmation.html", booking=booking_data)


def get_gemini_response(message):
    """Get AI response for hotel-related questions"""
    # Use pre-tested working models from initialization
    models_to_try = working_models if working_models else [
        'gemini-2.5-flash',
        'gemini-2.5-flash-lite',
        'gemini-2.5-flash-preview-tts',
        'gemini-3-flash-preview',
        'gemini-robotics-er-1.5-preview',
        'gemini-2.0-flash', 
        'gemini-1.5-flash',
        'gemini-pro-latest'
    ]
    
    for model_name in models_to_try:
        try:
            logging.info(f"Trying model: {model_name}")
            temp_model = genai.GenerativeModel(model_name)
            
            logging.info(f"Getting Gemini response for: {message}")
            
            # Hotel-specific prompt
            hotel_context = """Knowledge Base:

Check-in: 3:00 PM | Check-out: 11:00 AM.

Amenities: Free Wi-Fi, Rooftop Pool (6 AM - 10 PM), Gym (24/7), Dining, Spa.

Breakfast time: Served in the lobby from 7 AM to 11 AM.

Luxury Suite: Elegant suite with panoramic city views, separate living area, and premium amenities.
2 Guests, 1 King Bed, 55 m², From $299 / night

Deluxe Room: Spacious room with modern amenities and stunning city or garden views.
2 Guests, 1 King or 2 Queens, 42 m², From $229 / night

Executive Suite: Luxurious suite with separate living area, work desk, and premium amenities.
2-4 Guests, 1 King Bed + Sofa Bed, 65 m², From $399 / night

Resort locations: Pulau Tekong, Toa Payoh, Upper Thomson

Strict Rules:

Focus: Only answer questions about the hotel or the local area.

If you are unsure about the answer to the question, but the question is related to hotels, refer the customer to concierge support. 

Refusal: If a user asks about politics, coding, or unrelated topics, say: \"I'm here to assist with your stay at MGM Resorts. I'm afraid I can't help with that topic.\"

Tone: Professional, welcoming, and luxury-oriented."""
            
            full_prompt = f"{hotel_context}\n\nCustomer question: {message}"
            response = temp_model.generate_content(full_prompt)
            
            logging.info(f"Gemini response received from {model_name}: {response.text[:100]}...")
            return response.text
            
        except Exception as e:
            logging.warning(f"Model {model_name} failed: {str(e)}")
            continue  # Try next model
    
    # All models failed
    logging.error("All Gemini models failed")
    return "I'm sorry, I'm having trouble connecting right now. Please try again later or contact us through concierge support."


# =========================
# Chat Events
# =========================
# Trigger fresh deployment

# Initialize SocketIO (this will be imported in run.py)
socketio = SocketIO()

# Track user modes
user_modes = {}  # {session_id: 'ai' or 'human'}

@socketio.on('join_chat')
def on_join(data):
    print("\n" + "="*80)
    print("CHATBOT DEBUG: join_chat event received")
    print(f"DEBUG: Data received: {data}")
    room = data['room']
    session_id = request.sid
    print(f"DEBUG: Room: {room}")
    print(f"DEBUG: Session ID: {session_id}")
    user_modes[session_id] = 'ai'  # Default to AI mode
    print(f"DEBUG: User mode set to: {user_modes[session_id]}")
    
    # Create user-specific room for private messaging
    user_email = session.get('email') if 'email' in session else None
    if user_email:
        user_room_id = f"user_{user_email}"
    else:
        user_room_id = f"guest_{session_id}"
    
    # Join only user-specific room for admin replies
    join_room(user_room_id)  # User-specific room for admin replies
    
    print(f"DEBUG: User joined private room: {user_room_id}")
    
    # Emit status to user's private room only
    emit('status', {'msg': 'Connected to customer support'}, room=user_room_id)
    try:
        chat_history = get_chat_history(
            session_id=user_email if user_email else session_id,
            room='customer_service',
            limit=50
        )
        
        print(f"DEBUG: Loaded {len(chat_history)} chat history messages")
        
        # Send chat history to user
        for msg in chat_history:
            history_data = {
                'msg': msg['message'],
                'sender': msg['username'] if msg['sender_type'] == 'user' else 'Admin',
                'timestamp': msg['timestamp'].strftime('%H:%M') if msg['timestamp'] else datetime.now().strftime('%H:%M'),
                'sender_type': msg['sender_type']
            }
            emit('receive_message', history_data, room=user_room_id)
            
        print(f"DEBUG: Chat history sent to user")
    except Exception as e:
        print(f"DEBUG: Error loading chat history: {e}")
    
    emit('status', {'msg': 'Connected to customer support'}, room=room)
    print(f"DEBUG: Status emitted to room")
    print("="*80 + "\n")
    logging.info(f"User {session_id} joined chat in AI mode")

@socketio.on('switch_to_human_mode')
def on_switch_to_human():
    print("\n" + "="*80)
    print("CHATBOT DEBUG: switch_to_human_mode event received")
    session_id = request.sid
    print(f"DEBUG: Session ID: {session_id}")
    user_modes[session_id] = 'human'
    print(f"DEBUG: User mode switched to: human")
    print("="*80 + "\n")
    logging.info(f"User {session_id} switched to human mode")

@socketio.on('switch_to_ai_mode')
def on_switch_to_ai():
    print("\n" + "="*80)
    print("CHATBOT DEBUG: switch_to_ai_mode event received")
    session_id = request.sid
    print(f"DEBUG: Session ID: {session_id}")
    user_modes[session_id] = 'ai'
    print(f"DEBUG: User mode switched to: ai")
    print("="*80 + "\n")
    logging.info(f"User {session_id} switched to AI mode")

@socketio.on('send_encrypted_message')
def on_send_encrypted_message(data):
    """Handle encrypted messages from users and admin"""
    print("\n" + "="*80)
    print("CHATBOT DEBUG: send_encrypted_message event received")
    print(f"DEBUG: Raw data: {data}")
    
    session_id = data.get('session_id', '')
    encrypted_data = data.get('encrypted_data', '')
    target_room = data.get('target_room', '')
    
    if not encrypted_data or not session_id:
        print(f"DEBUG: Invalid encrypted message data: {data}")
        return
    
    print(f"DEBUG: Session ID: {session_id}")
    print(f"DEBUG: Encrypted data length: {len(encrypted_data)}")
    print(f"DEBUG: Target room: {target_room}")
    
    # Check if this is from admin (has target_room specified)
    if target_room:
        # Admin sending to user
        print(f"DEBUG: Admin message - forwarding to user room: {target_room}")
        
        # Save encrypted admin message to database
        try:
            save_chat_message(
                session_id=session_id,
                user_id=None,
                username='Admin',
                user_email=None,
                message=encrypted_data,  # Store encrypted message
                sender_type='admin',
                room='customer_service'
            )
            print(f"DEBUG: Admin encrypted message saved to database")
        except Exception as e:
            print(f"DEBUG: Error saving admin message: {e}")
        
        emit('receive_encrypted_message', {
            'encrypted_data': encrypted_data,
            'session_id': session_id,
            'username': 'Admin',
            'user_email': None,
            'user_room': target_room
        }, room=target_room)
        print(f"DEBUG: Admin encrypted message sent to user room: {target_room}")
    else:
        # User sending to admin
        # Get user's private room for responses
        user_email = session.get('email') if 'email' in session else None
        if user_email:
            user_room_id = f"user_{user_email}"
        else:
            user_room_id = f"guest_{session_id}"
        
        # Get user info for admin display
        user_id = session.get('user_id') if 'user_id' in session else None
        username = session.get('username', 'Guest') if 'username' in session else 'Guest'
        user_email = session.get('email') if 'email' in session else None
        
        print(f"DEBUG: User info - username: {username}, email: {user_email}, room: {user_room_id}")
        
        # Save encrypted user message to database
        try:
            save_chat_message(
                session_id=session_id,
                user_id=user_id,
                username=username,
                user_email=user_email,
                message=encrypted_data,  # Store encrypted message
                sender_type='user',
                room='customer_service'
            )
            print(f"DEBUG: User encrypted message saved to database")
        except Exception as e:
            print(f"DEBUG: Error saving user message: {e}")
        
        # Forward encrypted message directly to admin room
        # Admin will decrypt it using the DH shared secret
        emit('receive_encrypted_message', {
            'encrypted_data': encrypted_data,  # Send original encrypted data
            'session_id': session_id,
            'username': username,  # Add actual username here
            'user_email': user_email,
            'user_room': user_room_id
        }, room='customer_service')
        
        print(f"DEBUG: Encrypted user message forwarded to admin room: customer_service")
    
    print("="*80 + "\n")
    
    logging.info(f"Session {session_id} encrypted message processed")


@socketio.on('send_message')
def on_message(data):
    print("\n" + "="*80)
    print("CHATBOT DEBUG: send_message event received")
    print(f"DEBUG: Raw data: {data}")
    room = data['room']
    sender = data['sender']
    message = data['msg']
    session_id = request.sid
    print(f"DEBUG: Room: {room}")
    print(f"DEBUG: Sender: {sender}")
    print(f"DEBUG: Message: {message}")
    print(f"DEBUG: Session ID: {session_id}")
    print(f"DEBUG: Current user mode: {user_modes.get(session_id, 'NOT SET')}")
    
    # Get user's private room for AI responses
    user_email = session.get('email') if 'email' in session else None
    if user_email:
        user_room_id = f"user_{user_email}"
    else:
        user_room_id = f"guest_{session_id}"
    
    print(f"DEBUG: User's private room: {user_room_id}")
    
    # Log message
    logging.info(f"Chat message from {sender}: {message}")
    
    # Broadcast customer message to everyone (including admin/staff)
    message_data = {
        'msg': message,
        'sender': sender,
        'timestamp': datetime.now().strftime('%H:%M')
    }
    print(f"DEBUG: Broadcasting message to room: {message_data}")
    emit('receive_message', message_data, room=room, include_self=False)
    print(f"DEBUG: Message broadcasted")
    
    # If it's a customer message and user is in AI mode, generate AI response
    print(f"DEBUG: Checking if AI response needed...")
    print(f"DEBUG: sender == 'customer': {sender == 'customer'}")
    print(f"DEBUG: user_modes.get(session_id): {user_modes.get(session_id)}")
    if sender == 'customer' and user_modes.get(session_id) == 'ai':
        print(f"DEBUG: AI response will be generated")
        try:
            # Get AI response
            print(f"DEBUG: Calling get_gemini_response with message: {message[:50]}...")
            ai_response = get_gemini_response(message)
            print(f"DEBUG: AI response received: {ai_response[:100]}...")
            
            # Send AI response as "AI Support" to user's private room
            ai_message_data = {
                'msg': ai_response,
                'sender': 'AI Support',
                'timestamp': datetime.now().strftime('%H:%M')
            }
            
            # Small delay to make it feel natural
            import time
            print(f"DEBUG: Waiting 1 second before sending AI response...")
            time.sleep(1)
            
            print(f"DEBUG: Emitting AI response to user's private room: {user_room_id}")
            emit('receive_message', ai_message_data, room=user_room_id)
            print(f"DEBUG: AI response emitted successfully")
            print("="*80 + "\n")
            
            # Log AI response
            logging.info(f"AI response: {ai_response}")
            
        except Exception as e:
            print(f"ERROR: Exception in AI response generation: {type(e).__name__}: {str(e)}")
            import traceback
            print(f"ERROR: Traceback: {traceback.format_exc()}")
            print("="*80 + "\n")
            logging.error(f"Error generating AI response: {str(e)}")
            error_message = {
                'msg': "I'm sorry, I'm having trouble processing your request right now. Please try again.",
                'sender': 'AI Support',
                'timestamp': datetime.now().strftime('%H:%M')
            }
            emit('receive_message', error_message, room=user_room_id)
    elif sender == 'customer' and user_modes.get(session_id) == 'human':
        # In human mode, user messages are now handled by on_send_encrypted_message
        # This section is no longer needed - encrypted messages are handled separately
        print(f"DEBUG: User is in Human mode - message should be handled by encrypted handler")
        print(f"DEBUG: This section should not be reached in proper E2E encryption")
        print("="*80 + "\n")
    else:
        # Handle admin/staff messages (forward to room)
        print(f"DEBUG: Message from non-customer sender or no mode set - no AI response")
        print("="*80 + "\n")
        pass


# =========================
# Admin Chat Events
# =========================

@socketio.on('admin_join')
def on_admin_join():
    """Admin joins the customer service room"""
    session_id = request.sid
    print(f"DEBUG: Admin {session_id} joining customer_service room")
    join_room('customer_service')
    
    # Check who is in the customer_service room
    print(f"DEBUG: Room 'customer_service' members: {socketio.server.manager.get_participants('customer_service', None)}")
    
    # Send confirmation to admin
    emit('admin_joined', {'status': 'success', 'message': 'Connected to customer service'})
    print(f"DEBUG: Admin joined customer_service room")


@socketio.on('admin_send_encrypted_message')
def on_admin_send_encrypted_message(data):
    """Handle encrypted admin messages"""
    session_id = request.sid
    encrypted_data = data.get('encrypted_data', '')
    user_room = data.get('user_room', '')
    user_email = data.get('user_email', '')
    user_session_id = data.get('session_id', '')
    
    if not encrypted_data or not user_room:
        print(f"DEBUG: Invalid encrypted admin message data: {data}")
        return
    
    print(f"DEBUG: Received encrypted admin message for {user_room}")
    print(f"DEBUG: Admin using session ID: {user_session_id}")
    print(f"DEBUG: User room: {user_room}")
    
    # Get encryption key for this user session
    encryption_key = get_session_key(user_session_id)
    print(f"DEBUG: Generated encryption key for session: {user_session_id}")
    
    try:
        # Decrypt the admin message
        decrypted_message = decrypt_message(encrypted_data, encryption_key)
        
        if decrypted_message:
            print(f"DEBUG: Admin message decrypted successfully: {decrypted_message.get('msg', '')[:50]}...")
            
            # Log the original customer message to database first (for context)
            try:
                # Extract user info from room identifier
                if user_email:
                    target_session_id = user_email
                    target_username = user_email.split('@')[0]  # Extract username from email
                    target_user_email = user_email
                else:
                    target_session_id = user_room.replace('guest_', '')
                    target_username = 'Guest'
                    target_user_email = None
                
                # Save admin message to database
                save_chat_message(
                    session_id=target_session_id,
                    user_id=None,  # Admin messages don't have user_id
                    username='Admin',
                    user_email=None,
                    message=decrypted_message.get('msg', ''),
                    sender_type='admin',
                    room='customer_service'
                )
                print(f"DEBUG: Admin message saved to database")
            except Exception as e:
                print(f"DEBUG: Error saving admin message: {e}")
                import traceback
                print(f"DEBUG: Admin save traceback: {traceback.format_exc()}")
            
            # Send encrypted message to specific user room (for true E2E encryption)
            emit('receive_encrypted_message', {
                'encrypted_data': encrypted_data,  # Send original encrypted data
                'session_id': user_session_id
            }, room=user_room)
            
            print(f"DEBUG: Encrypted admin message sent to {user_room}")
            print(f"DEBUG: Forwarded encrypted data with session_id: {user_session_id}")
        else:
            print(f"DEBUG: Failed to decrypt admin message")
            
    except Exception as e:
        print(f"DEBUG: Error processing encrypted admin message: {e}")
        import traceback
        print(f"DEBUG: Encrypted message traceback: {traceback.format_exc()}")
    
    # Also send confirmation back to admin with decrypted message data
    emit('admin_message_sent', {
        'status': 'success', 
        'message': 'Message sent',
        'user_room': user_room,
        'message_data': decrypted_message,  # Send back the decrypted message
        'encrypted': True
    })
    
    print(f"DEBUG: Encrypted admin message processed")
    print("="*80 + "\n")


@socketio.on('admin_mark_read')
def on_admin_mark_read(data):
    """Admin marks messages as read for a user"""
    user_room = data.get('user_room', '')
    user_email = data.get('user_email', '')
    
    print(f"DEBUG: Admin marking messages as read for {user_room}")
    
    try:
        # Extract session_id for marking as read
        if user_email:
            target_session_id = user_email
        else:
            target_session_id = user_room.replace('guest_', '')
        
        mark_messages_as_read(session_id=target_session_id, room='customer_service')
        print(f"DEBUG: Messages marked as read for {target_session_id}")
        
        emit('messages_marked_read', {'status': 'success', 'user_room': user_room})
    except Exception as e:
        print(f"DEBUG: Error marking messages as read: {e}")
        emit('messages_marked_read', {'status': 'error', 'message': str(e)})


@socketio.on('admin_close_chat')
def on_admin_close_chat(data):
    """Admin closes chat with a customer - clears user's chat but keeps admin history"""
    session_id = data.get('session_id', '')
    user_room = data.get('user_room', '')
    
    print(f"DEBUG: Admin closing chat for session: {session_id}, room: {user_room}")
    
    try:
        # Emit chat_closed event to the specific user's room
        emit('chat_closed', {
            'status': 'closed',
            'message': 'The admin has closed this chat. Your issue has been resolved. Thank you!'
        }, room=user_room)
        
        print(f"DEBUG: Chat closed event sent to {user_room}")
        
        # Confirm to admin
        emit('chat_close_confirmed', {
            'status': 'success',
            'session_id': session_id
        })
        
    except Exception as e:
        print(f"DEBUG: Error closing chat: {e}")
        emit('chat_close_confirmed', {
            'status': 'error',
            'message': str(e)
        })


# =========================
# API Routes
# =========================

@main.post('/api/dh-exchange')
def api_dh_exchange():
    """API endpoint for Diffie-Hellman key exchange"""
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        client_public_key = data.get('public_key')
        
        if not session_id or not client_public_key:
            return jsonify({'error': 'Missing session_id or public_key'}), 400
        
        print(f"DEBUG: DH key exchange for session: {session_id}")
        
        # Store the client's public key
        if store_dh_public_key(session_id, client_public_key):
            return jsonify({
                'status': 'success',
                'message': 'Public key stored successfully'
            })
        else:
            return jsonify({'error': 'Failed to store public key'}), 500
            
    except Exception as e:
        print(f"DEBUG: Error in DH key exchange: {e}")
        return jsonify({'error': str(e)}), 500


@main.get('/api/dh-public-key/<session_id>')
def api_get_dh_public_key(session_id):
    """API endpoint to retrieve a session's public key"""
    try:
        public_key = get_dh_public_key(session_id)
        
        if public_key:
            return jsonify({
                'status': 'success',
                'public_key': public_key
            })
        else:
            return jsonify({'error': 'Public key not found'}), 404
            
    except Exception as e:
        print(f"DEBUG: Error retrieving DH public key: {e}")
        return jsonify({'error': str(e)}), 500


@main.post('/api/admin-chat-sessions')
def api_admin_chat_sessions():
    """API endpoint to get all customer chat sessions for admin"""
    print("DEBUG api_admin_chat_sessions: Endpoint called")
    print(f"DEBUG api_admin_chat_sessions: user_id={session.get('user_id')}, is_admin={session.get('is_admin')}")
    
    if not session.get("user_id") or not session.get("is_admin"):
        print("DEBUG api_admin_chat_sessions: Unauthorized - returning 401")
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        print("DEBUG api_admin_chat_sessions: Calling get_all_chat_sessions()")
        sessions = get_all_chat_sessions()
        print(f"DEBUG api_admin_chat_sessions: Got {len(sessions)} sessions")
        
        # Convert timestamps to ISO format
        result = []
        for sess in sessions:
            result.append({
                'session_id': sess['session_id'],
                'username': sess['username'],
                'user_email': sess['user_email'],
                'last_message': sess['last_message'],
                'sender_type': sess['sender_type'],
                'timestamp': sess['timestamp'].isoformat() if sess['timestamp'] else None
            })
        
        return jsonify({
            'status': 'success',
            'sessions': result
        })
        
    except Exception as e:
        print(f"DEBUG: Error getting admin chat sessions: {e}")
        import traceback
        print(f"DEBUG: Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@main.post('/api/user-chat-history')
def api_user_chat_history():
    """API endpoint to get encrypted chat history for user"""
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        
        if not session_id:
            return jsonify({'error': 'Missing session_id'}), 400
        
        print(f"DEBUG: Getting user chat history for session_id={session_id}")
        
        chat_history = get_chat_history(
            session_id=session_id,
            room='customer_service',
            limit=50
        )
        
        # Return encrypted messages for client-side decryption
        messages = []
        for msg in chat_history:
            messages.append({
                'id': msg['id'],
                'session_id': msg['session_id'],
                'username': msg['username'],
                'encrypted_data': msg['message'],  # This is the encrypted message
                'sender_type': msg['sender_type'],
                'timestamp': msg['timestamp'].isoformat() if msg['timestamp'] else None
            })
        
        return jsonify({
            'status': 'success',
            'messages': messages
        })
        
    except Exception as e:
        print(f"DEBUG: Error getting user chat history: {e}")
        return jsonify({'error': str(e)}), 500


@main.post('/api/chat-history')
def api_chat_history():
    """API endpoint to get chat history for admin dashboard"""
    if not session.get("user_id") or not session.get("is_admin"):
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        room = data.get('room')
        
        if not session_id or not room:
            return jsonify({'error': 'Missing session_id or room'}), 400
        
        print(f"DEBUG: Calling get_chat_history with session_id={session_id}, room={room}")
        try:
            chat_history = get_chat_history(
                session_id=session_id,
                room=room,
                limit=50
            )
            print(f"DEBUG: get_chat_history returned {len(chat_history)} items")
            for i, msg in enumerate(chat_history):
                msg_preview = msg['message'][:50] if msg['message'] else 'None'
                print(f"DEBUG: Message {i}: length={len(msg['message']) if msg['message'] else 0}, preview={msg_preview}")
            
        except Exception as db_error:
            print(f"DEBUG: Database error in get_chat_history: {db_error}")
            import traceback
            print(f"DEBUG: Database traceback: {traceback.format_exc()}")
            return jsonify({'error': f'Database error: {str(db_error)}'}), 500
        
        # Convert to JSON-serializable format
        messages = []
        try:
            for msg in chat_history:
                print(f"DEBUG: Processing message: {msg}")
                messages.append({
                    'id': msg['id'],
                    'session_id': msg['session_id'],
                    'username': msg['username'],
                    'user_email': msg['user_email'],
                    'message': msg['message'],
                    'sender_type': msg['sender_type'],
                    'room': msg['room'],
                    'timestamp': msg['timestamp'].isoformat() if msg['timestamp'] else None,
                    'admin_read': msg['admin_read']
                })
        except Exception as json_error:
            print(f"DEBUG: JSON serialization error: {json_error}")
            return jsonify({'error': f'JSON error: {str(json_error)}'}), 500
        
        return jsonify({
            'status': 'success',
            'messages': messages
        })
        
    except Exception as e:
        print(f"DEBUG: Error in chat history API: {e}")
        return jsonify({'error': str(e)}), 500
