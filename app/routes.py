from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
from PIL import Image
import logging
import os
from datetime import datetime
import random
import stripe

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

# =========================
# Pages
# =========================

@main.route("/")
def index():
    return render_template("home.html")

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

        session["booking_data"] = booking_data

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

    return render_template("booking_confirm.html", room_type=room_type)


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
