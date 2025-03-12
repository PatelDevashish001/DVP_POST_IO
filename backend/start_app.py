#!/usr/bin/env python
"""
DVP POST IO - Start Web Application
----------------------------------
This script starts the Flask web application on port 5001.
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app_startup.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("app_startup")

def start_app():
    """Start the Flask web application."""
    try:
        # Load environment variables
        load_dotenv()
        
        # Check if the required environment variables are set
        required_vars = ["MASTODON_BASE_URL", "REDIRECT_URI", "MASTODON_CLIENT_ID", "MASTODON_CLIENT_SECRET"]
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if missing_vars:
            logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
            logger.error("Please run setup_mastodon.py first to register a Mastodon client.")
            print(f"\n❌ Error: Missing required environment variables: {', '.join(missing_vars)}")
            print("Please run setup_mastodon.py first to register a Mastodon client.")
            return False
        
        # Import Flask app
        from app import app
        
        # Start the Flask app
        logger.info("Starting Flask app on port 5001")
        print("\n🚀 Starting DVP POST IO web application on port 5001...")
        app.run(host='127.0.0.1', port=5001, debug=True)
        
        return True
    except Exception as e:
        logger.error(f"Error starting app: {e}")
        print(f"\n❌ Error: {e}")
        return False

if __name__ == "__main__":
    start_app() 