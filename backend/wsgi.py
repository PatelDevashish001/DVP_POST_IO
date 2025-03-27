from backend.app import app
import os  # Import the 'os' module

if __name__ == "__main__":
    app.run(host='127.0.0.1', port=5001, debug=True)
