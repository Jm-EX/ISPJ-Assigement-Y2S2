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
from flask_socketio import SocketIO

app = create_app()
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Import and register socketio events
from app.routes import socketio as routes_socketio
routes_socketio.init_app(app)

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5001))
    host = "127.0.0.1"
    print(f"Running on http://{host}:{port}")
    socketio.run(app, debug=True, host=host, port=port)