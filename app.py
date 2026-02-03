import os
import sys

# Ensure run.py is properly imported
if __name__ == "__main__":
    from run import app, socketio
    
    port = int(os.environ.get("PORT", 5001))
    host = "0.0.0.0"
    debug = os.environ.get("FLASK_ENV") == "development"
    print(f"Running on http://{host}:{port}")
    socketio.run(app, debug=debug, host=host, port=port, allow_unsafe_werkzeug=True)
