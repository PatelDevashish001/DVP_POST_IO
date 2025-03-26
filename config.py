"""
DVP POST IO Configuration
------------------------
This module loads configuration values from environment variables.
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
    sys.exit(1)  # Exit if essential variable is missing

CLIENT_ID = os.getenv("MASTODON_CLIENT_ID")
if not CLIENT_ID:
    logger.error("MASTODON_CLIENT_ID not found in environment variables.")
    sys.exit(1)

CLIENT_SECRET = os.getenv("MASTODON_CLIENT_SECRET")
if not CLIENT_SECRET:
    logger.error("MASTODON_CLIENT_SECRET not found in environment variables.")
    sys.exit(1)

REDIRECT_URI = os.getenv("REDIRECT_URI")
if not REDIRECT_URI:
    logger.error("REDIRECT_URI not found in environment variables.")
    sys.exit(1)

# Application Security
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    logger.error("SECRET_KEY not found in environment variables.")
    sys.exit(1)

# Application Configuration
APP_NAME = "DVP POST IO"
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")

# Print configuration status (optional, but helpful for debugging)
logger.info(f"Configuration loaded. APP_NAME: {APP_NAME}, DEBUG: {DEBUG}")
logger.info(f"MASTODON_BASE_URL: {MASTODON_BASE_URL}")
logger.info(f"REDIRECT_URI: {REDIRECT_URI}")
logger.info(f"CLIENT_ID: {CLIENT_ID}")
logger.info(f"CLIENT_SECRET: {CLIENT_SECRET}")
