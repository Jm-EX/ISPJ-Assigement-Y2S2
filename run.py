<<<<<<< HEAD
=======
import os
from dotenv import load_dotenv

load_dotenv()

>>>>>>> login
from app import create_app

app = create_app()

if __name__ == "__main__":
<<<<<<< HEAD
    app.run(debug=True)
=======
    app.run(debug=True, port=int(os.environ.get("PORT", "5001")))
>>>>>>> login
