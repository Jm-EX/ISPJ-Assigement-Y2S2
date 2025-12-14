from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
import os
from datetime import datetime
import random

# Create the blueprint
main = Blueprint('main', __name__)

# Home page
@main.route("/")
def index():
    return render_template("home.html")

# Book room page
@main.route("/book")
def book_room():
    return render_template("book_room.html")

@main.route("/book/<room_type>", methods=['GET', 'POST'])
def book_room_confirm(room_type):
    if request.method == 'POST':
        # Process form data
        check_in = request.form.get('check_in')
        check_out = request.form.get('check_out')
        
        # Calculate nights
        check_in_date = datetime.strptime(check_in, '%Y-%m-%d')
        check_out_date = datetime.strptime(check_out, '%Y-%m-%d')
        nights = (check_out_date - check_in_date).days
        
        # Handle file upload
        if 'passport' not in request.files:
            flash('No passport file uploaded', 'error')
            return redirect(request.url)
            
        passport = request.files['passport']
        if passport.filename == '':
            flash('No selected file', 'error')
            return redirect(request.url)
            
        if passport:
            # Create uploads directory if it doesn't exist
            upload_folder = os.path.join('app', 'static', 'uploads', 'passports')
            os.makedirs(upload_folder, exist_ok=True)
            
            # Generate secure filename
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            filename = f"{timestamp}_{secure_filename(passport.filename)}"
            filepath = os.path.join(upload_folder, filename)
            passport.save(filepath)
            
            # Store booking data in session
            booking_data = {
                'room_type': room_type,
                'check_in': check_in,
                'check_out': check_out,
                'nights': nights,
                'guest_name': request.form.get('full_name'),
                'email': request.form.get('email'),
                'phone': request.form.get('phone'),
                'special_requests': request.form.get('special_requests', ''),
                'passport_filename': filename,
                'booking_reference': f"{random.randint(100000, 999999)}"
            }
            
            # Calculate price
            room_prices = {
                'Deluxe Room': 229,
                'Luxury Suite': 299,
                'Executive Suite': 399
            }
            booking_data['price_per_night'] = room_prices.get(room_type, 0)
            booking_data['total_price'] = booking_data['price_per_night'] * nights
            
            # Store in session for confirmation page
            session['booking_data'] = booking_data
            
            # In a real app, you would save this to a database here
            # For now, we'll just redirect to the confirmation page
            return redirect(url_for('main.booking_confirmation'))
    
    # For GET request, show the booking form
    return render_template('booking_confirm.html', room_type=room_type)
@main.route('/booking/confirmation')
def booking_confirmation():
    booking_data = session.get('booking_data')
    if not booking_data:
        flash('No booking found. Please make a booking first.', 'error')
        return redirect(url_for('main.book_room'))
    return render_template('booking_confirmation.html', booking=booking_data)