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

CLIENT_ID = os.getenv("MASTODON_CLIENT_ID") # Changed from MASTODON_CLIENT_ID for consistency if needed
if not CLIENT_ID:
    logger.error("CLIENT_ID not found in environment variables. Authentication will fail.")

CLIENT_SECRET = os.getenv("MASTODON_CLIENT_SECRET") # Changed from MASTODON_CLIENT_SECRET
if not CLIENT_SECRET:
    logger.error("CLIENT_SECRET not found in environment variables. Authentication will fail.")

REDIRECT_URI = os.getenv("REDIRECT_URI")
if not REDIRECT_URI:
    # Default usually points to the callback route in your Flask app
    # MAKE SURE THIS MATCHES YOUR DEPLOYED URL on Render/Railway
    REDIRECT_URI = "https://dvppostio-production.up.railway.app/callback" # Example - update needed!
    logger.warning(f"REDIRECT_URI not found. Using default: {REDIRECT_URI}")

# --- Database Configuration (Using Single URL) ---
logger.info("Loading Database Configuration...")
# Load the single RENDER_DATABASE_URL variable
RENDER_DATABASE_URL = os.getenv("RENDER_DATABASE_URL")
if not RENDER_DATABASE_URL:
    # This is critical, make it an error or critical log
    logger.critical("CRITICAL: RENDER_DATABASE_URL not found in environment variables! Database connection will fail.")
    # Set to None or raise error if needed elsewhere in the code
    # RENDER_DATABASE_URL = None
else:
    # Log that it's set, but avoid logging the full URL which contains credentials
    logger.info("RENDER_DATABASE_URL: Set (using provided connection string)")

# --- Remove loading of individual POSTGRES_* variables ---
# POSTGRES_DB = os.getenv("POSTGRES_DB")
# POSTGRES_USER = os.getenv("POSTGRES_USER")
# POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
# POSTGRES_HOST = os.getenv("POSTGRES_HOST")
# POSTGRES_PORT = os.getenv("POSTGRES_PORT")


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


# --- Configuration Summary Logging ---
logger.info("--- Configuration Summary ---")
logger.info(f"APP_NAME:         {APP_NAME}")

logger.info(f"SECRET_KEY:       {'Set (from env)' if os.getenv('SECRET_KEY') else 'Generated (temporary!)'}")
logger.info(f"MASTODON_BASE_URL:{MASTODON_BASE_URL}")
logger.info(f"REDIRECT_URI:     {REDIRECT_URI}")
logger.info(f"CLIENT_ID:        {'Set' if CLIENT_ID else '!!! NOT SET !!!'}")
logger.info(f"CLIENT_SECRET:    {'Set' if CLIENT_SECRET else '!!! NOT SET !!!'}")
# Log status of the single DB URL
logger.info(f"RENDER_DATABASE_URL:{'Set' if RENDER_DATABASE_URL else '!!! NOT SET !!!'}")
# Remove logging for individual POSTGRES_* vars
# logger.info(f"POSTGRES_HOST:    {POSTGRES_HOST}")
# ... etc ...
logger.info("--- End Configuration Summary ---")


# --- Final Validation ---
# Update validation to check RENDER_DATABASE_URL
required_env_vars = {
    "Mastodon Client ID": CLIENT_ID,
    "Mastodon Client Secret": CLIENT_SECRET,
    "Render Database URL": RENDER_DATABASE_URL, # Check the single URL
}

missing_vars_details = [name for name, value in required_env_vars.items() if not value]

if missing_vars_details:
    error_msg = f"Missing critical configuration variables: {', '.join(missing_vars_details)}"
    logger.critical(error_msg)
    logger.critical("Please check your .env file or environment variables.")
    print(f"\nCRITICAL ERROR: {error_msg}")
    print("The application cannot start without these settings.")
    print("Ensure your .env file or environment variables are correctly set up.")
    # sys.exit(1) # Uncomment to force exit if critical config is missing
