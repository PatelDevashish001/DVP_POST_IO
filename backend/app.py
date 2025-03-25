from flask import Flask, render_template, request, redirect, session, url_for, jsonify
import sqlite3
from mastodon import Mastodon
import config
import logging
import datetime
from backend.database import create_databases, migrate_data, check_database_integrity, repair_database
import os

# Configure logging
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
app.config['APP_NAME'] = "DVP POST IO"  # Set app name in config

mastodon = Mastodon(
    client_id=config.CLIENT_ID,
    client_secret=config.CLIENT_SECRET,
    api_base_url=config.MASTODON_BASE_URL
)

# Ensure user is logged in
def get_user():
    return session.get("user_id", None)  # Returns None instead of breaking

def get_user_info():
    """Get additional user information from the database."""
    if not get_user():
        return None
        
    try:
        with sqlite3.connect("users.db") as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("""
                SELECT mastodon_id, username, display_name, profile_url 
                FROM users 
                WHERE mastodon_id = ?
            """, (get_user(),))
            result = c.fetchone()
            return dict(result) if result else None
    except Exception as e:
        logger.error(f"Error fetching user info: {e}")
        return None

def create_databases():
    """Create the necessary database files."""
    print_step("3", "Creating database files...")
    
    try:
        # Create users database
        with sqlite3.connect("users.db") as conn:
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS users (
                            mastodon_id TEXT PRIMARY KEY, 
                            access_token TEXT NOT NULL,
                            username TEXT,
                            display_name TEXT,
                            profile_url TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            conn.commit()
        
        # Create tweets database
        with sqlite3.connect("tweets.db") as conn:
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS tweets (
                            id INTEGER PRIMARY KEY AUTOINCREMENT, 
                            user_id TEXT NOT NULL, 
                            message TEXT NOT NULL, 
                            schedule_time TEXT NOT NULL,
                            visibility TEXT DEFAULT 'public',
                            media_urls TEXT,
                            status TEXT DEFAULT 'pending',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            posted_at TIMESTAMP,
                            retry_count INTEGER DEFAULT 0,
                            processing_id TEXT,
                            processing_started TIMESTAMP,
                            FOREIGN KEY (user_id) REFERENCES users(mastodon_id))''')
            conn.commit()
        
        # Create stats database
        with sqlite3.connect("stats.db") as conn:
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS post_stats (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            tweet_id INTEGER,
                            user_id TEXT NOT NULL,
                            post_time TIMESTAMP,
                            status TEXT,
                            error_message TEXT,
                            FOREIGN KEY (user_id) REFERENCES users(mastodon_id),
                            FOREIGN KEY (tweet_id) REFERENCES tweets(id))''')
            conn.commit()
        
        print("✅ Database files created successfully.")
        return True
    
    except Exception as e:
        print(f"❌ Error creating database files: {e}")
        return False
def init_databases():
    """Create tables if they don't exist."""
    # Check database integrity first
    if not check_database_integrity():
        logger.warning("Database integrity check failed, attempting repair")
        repair_database()
    
    # Create or update databases
    result = create_databases()
    
    # Migrate existing data
    if result:
        migrate_data()
        
    return result


@app.route("/")
def index():
    if not get_user():
        return redirect(url_for("login"))
    
    # Fetch scheduled tweets for the logged-in user
    try:
        with sqlite3.connect("tweets.db") as conn:
            c = conn.cursor()
            
            # Check if status column exists
            c.execute("PRAGMA table_info(tweets)")
            columns = [column[1] for column in c.fetchall()]
            
            if "status" in columns:
                c.execute("""
                    SELECT id, message, schedule_time, 
                           COALESCE(visibility, 'public') as visibility, 
                           COALESCE(status, 'pending') as status, 
                           COALESCE(created_at, datetime('now')) as created_at
                    FROM tweets 
                    WHERE user_id = ? AND (status IS NULL OR status = 'pending')
                    ORDER BY schedule_time
                """, (get_user(),))
            else:
                # Fallback for older database schema
                c.execute("""
                    SELECT id, message, schedule_time, 
                           COALESCE(visibility, 'public') as visibility,
                           'pending' as status,
                           datetime('now') as created_at
                    FROM tweets 
                    WHERE user_id = ?
                    ORDER BY schedule_time
                """, (get_user(),))
                
            scheduled_tweets = c.fetchall()
            
            # Get user info
            user_info = get_user_info()
    except Exception as e:
        logger.error(f"Database error: {e}")
        scheduled_tweets = []
        user_info = None

    return render_template("index.html", 
                          scheduled_tweets=scheduled_tweets, 
                          user_info=user_info, 
                          app_name=app.config['APP_NAME'])

@app.route("/login")
def login():
    if get_user():
        return redirect(url_for("index"))  # If already logged in, go home
    
    auth_url = mastodon.auth_request_url(
        scopes=["read", "write"],
        redirect_uris=config.REDIRECT_URI
    )
    return redirect(auth_url)

@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        logger.error("No authorization code provided")
        return "Error: No authorization code provided.", 400

    try:
        access_token = mastodon.log_in(
            code=code,
            redirect_uri=config.REDIRECT_URI,
            scopes=["read", "write"]
        )
    except Exception as e:
        logger.error(f"Login Error: {e}")
        return "Error: Could not authenticate.", 500

    # Get user info from Mastodon
    try:
        mastodon_client = Mastodon(access_token=access_token, api_base_url=config.MASTODON_BASE_URL)
        user = mastodon_client.me()
        mastodon_id = str(user["id"])  # Unique user ID from Mastodon
        username = user.get("username", "")
        display_name = user.get("display_name", "")
        profile_url = user.get("url", "")
    except Exception as e:
        logger.error(f"Error fetching user data: {e}")
        return "Error: Could not fetch user data.", 500

    # Store user in `users.db`
    try:
        with sqlite3.connect("users.db") as conn:
            c = conn.cursor()
            c.execute("""
                INSERT OR REPLACE INTO users 
                (mastodon_id, access_token, username, display_name, profile_url) 
                VALUES (?, ?, ?, ?, ?)
            """, (mastodon_id, access_token, username, display_name, profile_url))
            conn.commit()
    except Exception as e:
        logger.error(f"Database Error: {e}")
        return "Error: Could not store user.", 500

    session["user_id"] = mastodon_id
    return redirect(url_for("index"))

@app.route("/add_tweet", methods=["POST"])
def add_tweet():
    if not get_user():
        return redirect(url_for("login"))

    message = request.form["message"]
    schedule_time = request.form["schedule_time"]
    visibility = request.form.get("visibility", "public")  # Default to public if not specified
    
    # Validate inputs
    if not message or not schedule_time:
        return "Error: Message and schedule time are required.", 400
        
    try:
        # Format current time
        created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        with sqlite3.connect("tweets.db") as conn:
            c = conn.cursor()
            
            # Check if status column exists
            c.execute("PRAGMA table_info(tweets)")
            columns = [column[1] for column in c.fetchall()]
            
            if all(col in columns for col in ["status", "created_at"]):
                c.execute("""
                    INSERT INTO tweets 
                    (user_id, message, schedule_time, visibility, status, created_at) 
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (get_user(), message, schedule_time, visibility, "pending", created_at))
            elif "visibility" in columns:
                c.execute("""
                    INSERT INTO tweets 
                    (user_id, message, schedule_time, visibility) 
                    VALUES (?, ?, ?, ?)
                """, (get_user(), message, schedule_time, visibility))
            else:
                # Fallback for very old schema
                c.execute("""
                    INSERT INTO tweets 
                    (user_id, message, schedule_time) 
                    VALUES (?, ?, ?)
                """, (get_user(), message, schedule_time))
                
            conn.commit()
            
        logger.info(f"Tweet scheduled for user {get_user()} at {schedule_time}")
    except Exception as e:
        logger.error(f"Database Error: {e}")
        return "Error: Could not schedule tweet.", 500

    return redirect(url_for("index"))

@app.route("/delete_tweet/<int:tweet_id>", methods=["POST"])
def delete_tweet(tweet_id):
    if not get_user():
        return redirect(url_for("login"))
    
    try:
        with sqlite3.connect("tweets.db") as conn:
            c = conn.cursor()
            # Verify the tweet belongs to the current user before deleting
            c.execute("DELETE FROM tweets WHERE id = ? AND user_id = ?", (tweet_id, get_user()))
            conn.commit()
            if c.rowcount == 0:
                logger.warning(f"Attempted to delete tweet {tweet_id} but not found or not authorized")
                return jsonify({"success": False, "message": "Tweet not found or not authorized"}), 404
                
        logger.info(f"Tweet {tweet_id} deleted by user {get_user()}")
    except Exception as e:
        logger.error(f"Database Error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    
    return jsonify({"success": True})

@app.route("/get_tweets", methods=["GET"])
def get_tweets():
    if not get_user():
        return jsonify({"error": "Not authenticated"}), 401
    
    try:
        with sqlite3.connect("tweets.db") as conn:
            conn.row_factory = sqlite3.Row  # This enables column access by name
            c = conn.cursor()
            c.execute("""
                SELECT id, message, schedule_time, visibility, status, created_at
                FROM tweets 
                WHERE user_id = ? AND status = 'pending'
                ORDER BY schedule_time
            """, (get_user(),))
            tweets = [dict(row) for row in c.fetchall()]
    except Exception as e:
        logger.error(f"Database Error: {e}")
        return jsonify({"error": str(e)}), 500
    
    return jsonify({"tweets": tweets})

@app.route("/get_history", methods=["GET"])
def get_history():
    """Get history of posted tweets."""
    if not get_user():
        return jsonify({"error": "Not authenticated"}), 401
    
    try:
        with sqlite3.connect("tweets.db") as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("""
                SELECT id, message, schedule_time, visibility, status, posted_at
                FROM tweets 
                WHERE user_id = ? AND status = 'posted'
                ORDER BY posted_at DESC
                LIMIT 20
            """, (get_user(),))
            history = [dict(row) for row in c.fetchall()]
    except Exception as e:
        logger.error(f"Database Error: {e}")
        return jsonify({"error": str(e)}), 500
    
    return jsonify({"history": history})

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("index"))

if __name__ == "__main__":
    create_databases()
    init_databases()# Ensure tables exist before running
    app.run(debug=False)
