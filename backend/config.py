"""
DVP POST IO Configuration
------------------------
This module loads configuration values from environment variables.
Sensitive information is stored in a .env file which should not be committed to version control.
"""

import os
from dotenv import load_dotenv
import logging
import sys

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("config.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("config")

# Load environment variables from .env file
logger.info("Loading environment variables from .env file")
load_dotenv(verbose=True)

# Mastodon API Configuration
MASTODON_BASE_URL = os.getenv("MASTODON_BASE_URL")
if not MASTODON_BASE_URL:
    MASTODON_BASE_URL = "https://mastodon.social"
    logger.warning(f"MASTODON_BASE_URL not found in environment variables. Using default: {MASTODON_BASE_URL}")

# Use the exact variable names from the .env file
CLIENT_ID = os.getenv("MASTODON_CLIENT_ID")
if not CLIENT_ID:
    logger.error("MASTODON_CLIENT_ID not found in environment variables. Authentication will fail.")

CLIENT_SECRET = os.getenv("MASTODON_CLIENT_SECRET")
if not CLIENT_SECRET:
    logger.error("MASTODON_CLIENT_SECRET not found in environment variables. Authentication will fail.")

ACCESS_TOKEN = os.getenv("MASTODON_ACCESS_TOKEN")
if not ACCESS_TOKEN:
    logger.warning("MASTODON_ACCESS_TOKEN not found in environment variables. Some features may not work.")

REDIRECT_URI = os.getenv("REDIRECT_URI")
if not REDIRECT_URI:
    REDIRECT_URI = "http://127.0.0.1:5000/callback"
    logger.warning(f"REDIRECT_URI not found in environment variables. Using default: {REDIRECT_URI}")

# Application Security
# In production, this should be a strong random key
SECRET_KEY_ENV = os.getenv("SECRET_KEY")
if SECRET_KEY_ENV:
    SECRET_KEY = SECRET_KEY_ENV
    logger.info("Using SECRET_KEY from environment variables.")
else:
    # Generate a random key if not provided in .env
    # Note: This will change on each restart, invalidating sessions
    logger.warning("No SECRET_KEY found in environment variables. Using a random key.")
    SECRET_KEY = os.urandom(24)

# Application Configuration
APP_NAME = "DVP POST IO"
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")

# Print configuration status
logger.info(f"Configuration loaded. APP_NAME: {APP_NAME}, DEBUG: {DEBUG}")
logger.info(f"MASTODON_BASE_URL: {MASTODON_BASE_URL}")
logger.info(f"REDIRECT_URI: {REDIRECT_URI}")
logger.info(f"CLIENT_ID: {'Set' if CLIENT_ID else 'Not set'}")
logger.info(f"CLIENT_SECRET: {'Set' if CLIENT_SECRET else 'Not set'}")
logger.info(f"ACCESS_TOKEN: {'Set' if ACCESS_TOKEN else 'Not set'}")

# Validate required configuration
required_vars = ["CLIENT_ID", "CLIENT_SECRET"]
missing_vars = [var for var in required_vars if not globals().get(var)]
if missing_vars:
    error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
    logger.error(error_msg)
    logger.error("Please check your .env file or environment variables.")
    print(f"\nERROR: {error_msg}")
    print("Please check your .env file or environment variables.")
    print("Make sure you have created a .env file with the required values.")
    print("You can copy .env.example to .env and fill in your Mastodon API credentials.")
    
    # In a production environment, you might want to exit here
    # sys.exit(1)
