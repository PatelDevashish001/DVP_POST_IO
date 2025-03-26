from backend.app import app
import os  # Import the 'os' module

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Get PORT from environment, default to 5000
    app.run(host="0.0.0.0", port=port, debug=False)
