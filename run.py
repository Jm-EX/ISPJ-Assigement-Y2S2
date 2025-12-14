import os
from dotenv import load_dotenv

load_dotenv()

from app import create_app

app = create_app()

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5001))
    host = "127.0.0.1"
    print(f"Running on http://{host}:{port}")
    app.run(debug=True, host=host, port=port)