"""
DVP POST IO Configuration
------------------------
This module loads configuration values from environment variables.
Sensitive information is stored in environment variables.
"""

import os
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

# Mastodon API Configuration
MASTODON_BASE_URL = os.getenv("MASTODON_BASE_URL")
if not MASTODON_BASE_URL:
    logger.error("MASTODON_BASE_URL not found in environment variables.")

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
    logger.error("REDIRECT_URI not found in environment variables.")

# Application Security
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    logger.error("SECRET_KEY not found in environment variables.")

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
required_vars = ["CLIENT_ID", "CLIENT_SECRET", "REDIRECT_URI", "SECRET_KEY"]
missing_vars = [var for var in required_vars if not globals().get(var)]
if missing_vars:
    error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
    logger.error(error_msg)
    logger.error("Please check your environment variables.")
    print(f"\nERROR: {error_msg}")
    print("Please check your environment variables.")
    sys.exit(1)
