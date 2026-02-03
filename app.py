import os
import sys

# Import app and socketio at module level for Render
from run import app, socketio

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    host = "0.0.0.0"
    debug = os.environ.get("FLASK_ENV") == "development"
    print(f"Running on http://{host}:{port}")
    socketio.run(app, debug=debug, host=host, port=port, allow_unsafe_werkzeug=True)
