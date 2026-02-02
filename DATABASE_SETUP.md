# Database Setup Instructions

## For Your Friends to Import the Database

### Prerequisites
- MySQL installed on their system
- MySQL server running

### Step 1: Create the Database
```bash
mysql -u root -p -e "CREATE DATABASE ispj_hotel;"
```

### Step 2: Import the Database
```bash
mysql -u root -p ispj_hotel < ispj_hotel_export.sql
```

### Step 3: Configure Environment Variables
Create a `.env` file in the project root with the following content:

```
SECRET_KEY=dev-secret-key-change-me-in-production
PORT=5001
ADMIN_EMAIL=your-email@gmail.com

MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your-mysql-password
MYSQL_DATABASE=ispj_hotel

SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM=your-email@gmail.com
SMTP_USE_TLS=1
```

**Important:** Replace the placeholders with their actual values:
- `your-mysql-password` - Their MySQL root password
- `your-email@gmail.com` - Their email address
- `your-app-password` - Their Gmail app password (for sending OTP emails)

### Step 4: Install Python Dependencies
```bash
pip install -r requirements.txt
```

### Step 5: Run the Application
```bash
python3 run.py
```

The application will be available at `http://localhost:5001`

## Database Contents
The exported database includes:
- User accounts
- Passkey credentials (Touch ID/Face ID)
- Booking data
- Room information
- All necessary tables and data

## Notes
- Make sure MySQL is running before importing
- The database uses UTF-8 encoding
- All passwords in the database are hashed for security
