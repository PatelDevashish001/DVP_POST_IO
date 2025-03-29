from flask import Flask, render_template, request, redirect, session, url_for, jsonify
# import sqlite3  # Remove SQLite3
import psycopg2 # Import PostgreSQL driver
import psycopg2.extras # Import DictCursor
from mastodon import Mastodon
import config
import logging
import datetime
# --- Import functions EXACTLY as named in your database.py ---
from database import get_connection, create_databases, migrate_data, check_database_integrity, repair_database

# Configure logging (remains the same)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("mastodon_scheduler")

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config['APP_NAME'] = "DVP POST IO"

# Mastodon client setup (remains the same)
mastodon = Mastodon(
    client_id=config.CLIENT_ID,
    client_secret=config.CLIENT_SECRET,
    api_base_url=config.MASTODON_BASE_URL
)

# --- User Session Helper ---
def get_user():
    """Gets the Mastodon user ID from the session."""
    return session.get("user_id", None)

# --- User Info Helper (Converted to PostgreSQL) ---
def get_user_info():
    """Get additional user information from the PostgreSQL database."""
    user_id = get_user()
    if not user_id:
        return None

    conn = None
    try:
        # Use the get_connection function from database.py
        conn = get_connection()
        # Use DictCursor for dictionary-like row access
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("""
                SELECT mastodon_id, username, display_name, profile_url
                FROM users
                WHERE mastodon_id = %s
            """, (user_id,)) # Use %s placeholder
            result = cur.fetchone()
            # Return a dictionary if found, otherwise None
            return dict(result) if result else None
    except (Exception, psycopg2.Error) as e:
        logger.error(f"Error fetching user info for {user_id}: {e}")
        return None
    finally:
        if conn:
            conn.close() # Ensure connection is always closed

# --- Database Initialization Wrapper (Uses imported functions) ---
def init_databases():
    """Check integrity, repair if needed, create/update tables, migrate data."""
    # This function now orchestrates the calls to the functions imported from database.py
    try:
        logger.info("Checking database integrity...")
        if not check_database_integrity():
            logger.warning("Database integrity check failed, attempting repair...")
            # repair_database() calls create_databases internally if check fails
            if not repair_database():
                 logger.error("Database repair attempt failed.")
                 return False # Indicate failure
            else:
                logger.info("Database repair attempt completed (tables possibly created).")
        else:
            logger.info("Database integrity check passed. Ensuring schema is up-to-date...")
            # Still call create_databases to handle potential schema updates (IF NOT EXISTS)
            if not create_databases():
                logger.error("Failed to verify/update database schema.")
                return False # Indicate failure
            else:
                 logger.info("Schema verified/updated.")

        logger.info("Applying data migrations...")
        if not migrate_data():
            logger.warning("Data migration step failed or encountered an issue.")
            # Decide if this is critical - for now, we continue
        else:
            logger.info("Data migration step completed.")

        logger.info("Database initialization sequence complete.")
        return True
    except Exception as e:
        logger.error(f"Error during database initialization sequence: {e}")
        return False


# --- Routes (Converted to PostgreSQL) ---

@app.route("/")
def index():
    user_id = get_user()
    if not user_id:
        return redirect(url_for("login"))

    scheduled_tweets = []
    user_info = get_user_info() # Fetch user info for display
    conn = None

    try:
        conn = get_connection() # Use imported connection function
        # Use DictCursor for easier access in template
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # Fetch pending tweets for the logged-in user
            # Removed the PRAGMA check, assume schema managed by database.py
            # Use COALESCE and NOW() for PostgreSQL defaults
            cur.execute("""
                SELECT id, message, schedule_time,
                       COALESCE(visibility, 'public') as visibility,
                       COALESCE(status, 'pending') as status,
                       COALESCE(created_at, NOW()) as created_at
                FROM tweets
                WHERE user_id = %s AND COALESCE(status, 'pending') = 'pending'
                ORDER BY schedule_time
            """, (user_id,))
            # Convert rows to simple dictionaries for the template
            scheduled_tweets = cur.fetchall()

    except (Exception, psycopg2.Error) as e:
        logger.error(f"Database error fetching tweets for user {user_id}: {e}")
        # scheduled_tweets remains empty list
        # flash("Could not load scheduled posts.", "error") # Optional feedback
    finally:
        if conn:
            conn.close()

    return render_template("index.html",
                          scheduled_tweets=scheduled_tweets,
                          user_info=user_info,
                          app_name=app.config['APP_NAME'])

@app.route("/login")
def login():
    if get_user():
        return redirect(url_for("index"))
    auth_url = mastodon.auth_request_url(
        scopes=["read", "write"],
        redirect_uris=config.REDIRECT_URI
    )
    return redirect(auth_url)

@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        logger.error("Callback received without authorization code.")
        return "Error: No authorization code provided.", 400

    access_token = None
    user = None
    try:
        access_token = mastodon.log_in(
            code=code,
            redirect_uri=config.REDIRECT_URI,
            scopes=["read", "write"]
        )
        mastodon_client = Mastodon(access_token=access_token, api_base_url=config.MASTODON_BASE_URL)
        user = mastodon_client.me()
        logger.info(f"Successfully authenticated Mastodon user: {user.get('username')}")

    except Exception as e:
        logger.error(f"Mastodon authentication or API error during callback: {e}")
        return "Error: Could not authenticate with Mastodon.", 500

    # --- Store/Update User in PostgreSQL Database ---
    conn = None
    try:
        mastodon_id = str(user["id"])
        username = user.get("username", "")
        # Use acct (like username@instance) as fallback display name if actual display name is empty
        display_name = user.get("display_name", user.get("acct", ""))
        profile_url = user.get("url", "")

        conn = get_connection() # Use imported function
        with conn.cursor() as cur:
            # PostgreSQL UPSERT: INSERT...ON CONFLICT...DO UPDATE
            # Assumes mastodon_id is the PRIMARY KEY in your users table
            # Note: created_at is handled by DEFAULT NOW() in the table definition
            # We update username, display_name, profile_url, and crucially access_token
            cur.execute("""
                INSERT INTO users (mastodon_id, access_token, username, display_name, profile_url)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (mastodon_id) DO UPDATE SET
                    access_token = EXCLUDED.access_token,
                    username = EXCLUDED.username,
                    display_name = EXCLUDED.display_name,
                    profile_url = EXCLUDED.profile_url;
            """, (mastodon_id, access_token, username, display_name, profile_url))
        conn.commit() # Commit the transaction for INSERT/UPDATE
        logger.info(f"User {mastodon_id} ({username}) data stored/updated in database.")

        session["user_id"] = mastodon_id
        return redirect(url_for("index"))

    except (Exception, psycopg2.Error) as e:
        logger.error(f"Database error storing user {user.get('id') if user else 'unknown'}: {e}")
        if conn:
            conn.rollback() # Rollback transaction on database error
        return "Error: Could not save user information after login.", 500
    finally:
        if conn:
            conn.close()


@app.route("/add_tweet", methods=["POST"])
def add_tweet():
    user_id = get_user()
    if not user_id:
        return redirect(url_for("login"))

    # Use .get() for safer access to form data
    message = request.form.get("message")
    schedule_time_str = request.form.get("schedule_time")
    visibility = request.form.get("visibility", "public")

    if not message or not schedule_time_str:
        # Consider flashing an error message
        logger.warning(f"Add tweet attempt failed for user {user_id}: Missing message or schedule time.")
        return "Error: Message and schedule time are required.", 400

    # Basic validation/parsing could happen here if needed
    # e.g., try: datetime.datetime.fromisoformat(schedule_time_str) except ValueError: ...

    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            # Removed complex column checking - assume schema from database.py
            # Use NOW() for created_at. status defaults to 'pending' in schema.
            cur.execute("""
                INSERT INTO tweets
                (user_id, message, schedule_time, visibility)
                VALUES (%s, %s, %s, %s)
            """, (user_id, message, schedule_time_str, visibility))
            # Note: Assuming 'status', 'created_at', 'retry_count' have defaults in DB schema
        conn.commit() # Commit the INSERT
        logger.info(f"Tweet scheduled for user {user_id} at {schedule_time_str}")
        # flash("Post scheduled successfully!", "success") # Optional feedback
    except (Exception, psycopg2.Error) as e:
        logger.error(f"Database error scheduling tweet for user {user_id}: {e}")
        if conn:
            conn.rollback() # Rollback on error
        # flash("Error scheduling post.", "error") # Optional feedback
        return "Error: Could not schedule tweet due to a database issue.", 500
    finally:
        if conn:
            conn.close()

    return redirect(url_for("index"))

@app.route("/delete_tweet/<int:tweet_id>", methods=["POST"])
def delete_tweet(tweet_id):
    user_id = get_user()
    if not user_id:
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    conn = None
    deleted_count = 0
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            # Ensure the tweet belongs to the current user before deleting
            cur.execute("DELETE FROM tweets WHERE id = %s AND user_id = %s", (tweet_id, user_id))
            # Check how many rows were affected
            deleted_count = cur.rowcount
        conn.commit() # Commit the DELETE

        if deleted_count == 0:
            logger.warning(f"Attempted delete tweet {tweet_id} by user {user_id}, but not found or not authorized.")
            return jsonify({"success": False, "message": "Tweet not found or not authorized"}), 404
        else:
            logger.info(f"Tweet {tweet_id} deleted by user {user_id}")
            return jsonify({"success": True})

    except (Exception, psycopg2.Error) as e:
        logger.error(f"Database error deleting tweet {tweet_id} for user {user_id}: {e}")
        if conn:
            conn.rollback() # Rollback on error
        return jsonify({"success": False, "message": "Database error during deletion"}), 500
    finally:
        if conn:
            conn.close()


@app.route("/get_tweets", methods=["GET"])
def get_tweets():
    """API endpoint to get pending tweets for the logged-in user."""
    user_id = get_user()
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # Fetch tweets with pending status
            cur.execute("""
                SELECT id, message, schedule_time, visibility, status, created_at
                FROM tweets
                WHERE user_id = %s AND status = 'pending'
                ORDER BY schedule_time
            """, (user_id,))
            tweets = [dict(row) for row in cur.fetchall()]
        return jsonify({"tweets": tweets})
    except (Exception, psycopg2.Error) as e:
        logger.error(f"Database Error in get_tweets for user {user_id}: {e}")
        return jsonify({"error": "Could not retrieve tweets"}), 500
    finally:
        if conn:
            conn.close()

@app.route("/get_history", methods=["GET"])
def get_history():
    """API endpoint to get history of posted/failed tweets."""
    user_id = get_user()
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # Fetch tweets that are NOT pending, limit results
            # Assumes your schema has 'posted_at' column, uses COALESCE for ordering
            cur.execute("""
                SELECT id, message, schedule_time, visibility, status, posted_at
                FROM tweets
                WHERE user_id = %s AND status != 'pending'
                ORDER BY COALESCE(posted_at, created_at) DESC
                LIMIT 50 -- Limit history size
            """, (user_id,))
            history = [dict(row) for row in cur.fetchall()]
        return jsonify({"history": history})
    except (Exception, psycopg2.Error) as e:
        logger.error(f"Database Error in get_history for user {user_id}: {e}")
        # Add specific check if 'posted_at' is missing
        if "column tweets.posted_at does not exist" in str(e).lower():
             logger.error("History query failed: 'posted_at' column might be missing in the tweets table.")
             return jsonify({"error": "History feature unavailable (schema mismatch)"}), 500
        return jsonify({"error": "Could not retrieve history"}), 500
    finally:
        if conn:
            conn.close()


@app.route("/logout")
def logout():
    user_id = session.pop("user_id", None)
    if user_id:
        logger.info(f"User {user_id} logged out.")
    # flash("You have been logged out.", "info") # Optional feedback
    return redirect(url_for("index"))


# --- Application Entry Point ---
if __name__ == "__main__":
    logger.info("Starting Mastodon Scheduler Application...")
    # Initialize database using the wrapper function which calls
    # functions from the imported database.py
    if not init_databases():
         logger.critical("DATABASE INITIALIZATION FAILED. Check logs. Application might not function correctly.")
         # Consider exiting if DB init is critical
         # import sys
         # sys.exit("Exiting due to database initialization failure.")
    else:
        logger.info("Database initialization checks passed.")

    # Run the Flask development server
    # Set debug=False for production
    app.run(host='127.0.0.1', port=5001, debug=True)