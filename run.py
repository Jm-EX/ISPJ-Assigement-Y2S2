import os
from dotenv import load_dotenv

load_dotenv()

# Clear bookings.log file on startup
log_file = 'logs/bookings.log'
if os.path.exists(log_file):
    with open(log_file, 'w') as f:
        f.truncate(0)
    print(f"Cleared contents of {log_file}")

from app import create_app

app = create_app()

# Import socketio from routes and initialize it with the app
from app.routes import socketio
socketio.init_app(app, cors_allowed_origins="*", async_mode='threading', engineio_logger=False, logger=False, manage_session=False)

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5001))
    host = "0.0.0.0"
    debug = os.environ.get("FLASK_ENV") == "development"
    print(f"Running on http://{host}:{port}")
    socketio.run(app, debug=debug, host=host, port=port, allow_unsafe_werkzeug=True)