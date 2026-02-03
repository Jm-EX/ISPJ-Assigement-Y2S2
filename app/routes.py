from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
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

# =========================
# Setup
# =========================

os.makedirs('logs', exist_ok=True)

logging.basicConfig(
    filename='logs/bookings.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

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
            
            # Try to find the best model
            if 'models/gemini-1.5-flash' in available_models:
                gemini_model = genai.GenerativeModel('gemini-1.5-flash')
                print("DEBUG: Using gemini-1.5-flash")
            elif 'models/gemini-pro' in available_models:
                gemini_model = genai.GenerativeModel('gemini-pro')
                print("DEBUG: Using gemini-pro")
            elif 'models/gemini-1.0-pro' in available_models:
                gemini_model = genai.GenerativeModel('gemini-1.0-pro')
                print("DEBUG: Using gemini-1.0-pro")
            else:
                # Use the first available model
                first_model = available_models[0].replace('models/', '')
                gemini_model = genai.GenerativeModel(first_model)
                print(f"DEBUG: Using first available model: {first_model}")
                logging.info(f"Using first available model: {first_model}")
            
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
    """Get response from Gemini AI with fallback to multiple models and retry logic"""
    
    print("\n" + "="*80)
    print("DEBUG: get_gemini_response called")
    print(f"DEBUG: Message: {message[:100]}...")
    print(f"DEBUG: gemini_model exists: {gemini_model is not None}")
    print(f"DEBUG: GEMINI_API_KEY present: {bool(os.environ.get('GEMINI_API_KEY'))}")
    print("="*80)
    
    # Try multiple models in order of preference (only use models available in v1beta)
    models_to_try = [
        'gemini-1.5-flash',  # Best for free tier - higher limits
        'gemini-pro'
    ]
    
    for model_name in models_to_try:
        # Retry logic for rate limits
        max_retries = 2
        retry_delay = 2  # Start with 2 seconds
        
        for attempt in range(max_retries):
            try:
                print(f"DEBUG: Trying model: {model_name} (attempt {attempt + 1}/{max_retries})")
                logging.info(f"Trying model: {model_name} (attempt {attempt + 1}/{max_retries})")
                temp_model = genai.GenerativeModel(model_name)
                
                print(f"DEBUG: Getting Gemini response for: {message[:50]}...")
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

Refusal: If a user asks about politics, coding, or unrelated topics, say: \"I'm here to assist with your stay at MGM Resorts. I'm afraid I can't help with that topic.\"

Tone: Professional, welcoming, and luxury-oriented."""
                
                full_prompt = f"{hotel_context}\n\nCustomer question: {message}"
                print(f"DEBUG: Generating content with {model_name}...")
                response = temp_model.generate_content(full_prompt)
                
                print(f"DEBUG: Gemini response received from {model_name}: {response.text[:100]}...")
                logging.info(f"Gemini response received from {model_name}: {response.text[:100]}...")
                print("="*80 + "\n")
                return response.text
                
            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)
                print(f"DEBUG: Model {model_name} attempt {attempt + 1} failed: {error_type}: {error_msg}")
                logging.warning(f"Model {model_name} attempt {attempt + 1} failed: {error_msg}")
                
                # Check if it's a rate limit error
                if "429" in error_msg or "quota" in error_msg.lower() or "rate" in error_msg.lower():
                    if attempt < max_retries - 1:
                        print(f"DEBUG: Rate limit hit, waiting {retry_delay} seconds before retry...")
                        import time
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                        continue
                    else:
                        print(f"DEBUG: Max retries reached for {model_name}, trying next model")
                        break
                else:
                    # Non-rate-limit error, try next model immediately
                    print(f"DEBUG: Non-rate-limit error, trying next model")
                    break
    
    # All models failed
    print("DEBUG: All Gemini models failed")
    print("="*80 + "\n")
    logging.error("All Gemini models failed")
    return "I'm sorry, I'm having trouble connecting right now. Please try again later or contact us through concierge support."


# =========================
# Chat Events
# =========================

# Initialize SocketIO (this will be imported in run.py)
socketio = SocketIO()

# Track user modes
user_modes = {}  # {session_id: 'ai' or 'human'}

@socketio.on('join_chat')
def on_join(data):
    room = data['room']
    session_id = request.sid
    user_modes[session_id] = 'ai'  # Default to AI mode
    join_room(room)
    emit('status', {'msg': 'Connected to customer support'}, room=room)
    logging.info(f"User {session_id} joined chat in AI mode")

@socketio.on('switch_to_human_mode')
def on_switch_to_human():
    session_id = request.sid
    user_modes[session_id] = 'human'

@socketio.on('switch_to_ai_mode')
def on_switch_to_ai():
    session_id = request.sid
    user_modes[session_id] = 'ai'

@socketio.on('send_message')
def on_message(data):
    room = data['room']
    sender = data['sender']
    message = data['msg']
    session_id = request.sid
    
    # Log message
    logging.info(f"Chat message from {sender}: {message}")
    
    # Broadcast customer message to everyone (including admin/staff)
    message_data = {
        'msg': message,
        'sender': sender,
        'timestamp': datetime.now().strftime('%H:%M')
    }
    emit('receive_message', message_data, room=room, include_self=False)
    
    # If it's a customer message and user is in AI mode, generate AI response
    if sender == 'customer' and user_modes.get(session_id) == 'ai':
        try:
            # Get AI response
            ai_response = get_gemini_response(message)
            
            # Send AI response as "AI Support"
            ai_message_data = {
                'msg': ai_response,
                'sender': 'AI Support',
                'timestamp': datetime.now().strftime('%H:%M')
            }
            
            # Small delay to make it feel natural
            import time
            time.sleep(1)
            
            emit('receive_message', ai_message_data, room=room)
            
            # Log AI response
            logging.info(f"AI response: {ai_response}")
            
        except Exception as e:
            logging.error(f"Error generating AI response: {str(e)}")
            error_message = {
                'msg': "I'm sorry, I'm having trouble processing your request right now. Please try again.",
                'sender': 'AI Support',
                'timestamp': datetime.now().strftime('%H:%M')
            }
            emit('receive_message', error_message, room=room)
    elif sender == 'customer' and user_modes.get(session_id) == 'human':
        # In human mode, don't generate AI responses
        logging.info(f"User {session_id} is in Human mode - no AI response generated")
    else:
        # Handle admin/staff messages (forward to room)
        pass
