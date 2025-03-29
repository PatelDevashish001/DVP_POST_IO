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
load_dotenv(verbose=True) # verbose=True shows which file is loaded

# --- Mastodon API Configuration ---
logger.info("Loading Mastodon Configuration...")
MASTODON_BASE_URL = os.getenv("MASTODON_BASE_URL")
if not MASTODON_BASE_URL:
    MASTODON_BASE_URL = "https://mastodon.social" # Or your preferred default instance
    logger.warning(f"MASTODON_BASE_URL not found. Using default: {MASTODON_BASE_URL}")

CLIENT_ID = os.getenv("MASTODON_CLIENT_ID")
if not CLIENT_ID:
    logger.error("MASTODON_CLIENT_ID not found in environment variables. Authentication will fail.")

CLIENT_SECRET = os.getenv("MASTODON_CLIENT_SECRET")
if not CLIENT_SECRET:
    logger.error("MASTODON_CLIENT_SECRET not found in environment variables. Authentication will fail.")

REDIRECT_URI = os.getenv("REDIRECT_URI")
if not REDIRECT_URI:
    # Default usually points to the callback route in your Flask app
    REDIRECT_URI = "http://127.0.0.1:5001/callback" # Match your Flask app's port
    logger.warning(f"REDIRECT_URI not found. Using default: {REDIRECT_URI}")

# --- Database Configuration (PostgreSQL) ---
logger.info("Loading Database Configuration...")
POSTGRES_DB = os.getenv("POSTGRES_DB")
if not POSTGRES_DB:
    logger.error("POSTGRES_DB not found in environment variables. Database connection will fail.")

POSTGRES_USER = os.getenv("POSTGRES_USER")
if not POSTGRES_USER:
    logger.error("POSTGRES_USER not found in environment variables. Database connection will fail.")

POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
# ***************************************************************
# CHANGE: Log an ERROR instead of WARNING if password is missing
# ***************************************************************
if not POSTGRES_PASSWORD:
    logger.error("POSTGRES_PASSWORD not found in environment variables. Connection will likely fail if password is required.")

POSTGRES_HOST = os.getenv("POSTGRES_HOST")
if not POSTGRES_HOST:
    POSTGRES_HOST = "localhost"
    logger.warning(f"POSTGRES_HOST not found. Using default: {POSTGRES_HOST}")

POSTGRES_PORT = os.getenv("POSTGRES_PORT")
if not POSTGRES_PORT:
    POSTGRES_PORT = "5432" # Default PostgreSQL port
    logger.warning(f"POSTGRES_PORT not found. Using default: {POSTGRES_PORT}")


# --- Application Security ---
logger.info("Loading Application Security Configuration...")
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    logger.critical("CRITICAL: SECRET_KEY not found in environment variables. Generating a temporary key.")
    logger.critical("WARNING: Using a temporary key means sessions will be invalidated on every restart!")
    SECRET_KEY = os.urandom(24).hex()


# --- Application Configuration ---
logger.info("Loading General Application Configuration...")
APP_NAME = "DVP POST IO"
DEBUG = os.getenv("FLASK_DEBUG", "False").lower() in ("true", "1", "t")

# --- Configuration Summary Logging ---
logger.info("--- Configuration Summary ---")
logger.info(f"APP_NAME:         {APP_NAME}")
logger.info(f"DEBUG:            {DEBUG}")
logger.info(f"SECRET_KEY:       {'Set (from env)' if os.getenv('SECRET_KEY') else 'Generated (temporary!)'}")
logger.info(f"MASTODON_BASE_URL:{MASTODON_BASE_URL}")
logger.info(f"REDIRECT_URI:     {REDIRECT_URI}")
logger.info(f"CLIENT_ID:        {'Set' if CLIENT_ID else '!!! NOT SET !!!'}")
logger.info(f"CLIENT_SECRET:    {'Set' if CLIENT_SECRET else '!!! NOT SET !!!'}")
logger.info(f"POSTGRES_HOST:    {POSTGRES_HOST}")
logger.info(f"POSTGRES_PORT:    {POSTGRES_PORT}")
logger.info(f"POSTGRES_DB:      {POSTGRES_DB if POSTGRES_DB else '!!! NOT SET !!!'}")
logger.info(f"POSTGRES_USER:    {POSTGRES_USER if POSTGRES_USER else '!!! NOT SET !!!'}")
# ***************************************************************
# CHANGE: Update summary logging for password
# ***************************************************************
logger.info(f"POSTGRES_PASSWORD:{'Set' if POSTGRES_PASSWORD else '!!! NOT SET (Likely Required) !!!'}")
logger.info("--- End Configuration Summary ---")


# --- Final Validation ---
# List variables absolutely required for the app/scheduler to function
# ***************************************************************
# CHANGE: Add PostgreSQL Password to the required variables list
# ***************************************************************
required_env_vars = {
    "Mastodon Client ID": CLIENT_ID,
    "Mastodon Client Secret": CLIENT_SECRET,
    "PostgreSQL DB Name": POSTGRES_DB,
    "PostgreSQL User": POSTGRES_USER,
    "PostgreSQL Password": POSTGRES_PASSWORD, # Added password here
}

missing_vars_details = [name for name, value in required_env_vars.items() if not value]

if missing_vars_details:
    error_msg = f"Missing critical configuration variables: {', '.join(missing_vars_details)}"
    logger.critical(error_msg)
    logger.critical("Please check your .env file or environment variables.")
    print(f"\nCRITICAL ERROR: {error_msg}")
    print("The application cannot start without these settings.")
    print("Ensure your .env file is correctly set up.")
    # sys.exit(1) # Uncomment to force exit if critical config is missing