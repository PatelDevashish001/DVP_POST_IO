import sqlite3
import logging
import os

logger = logging.getLogger("mastodon_scheduler")

DATABASE_PATH = os.environ.get("DATABASE_PATH", "/tmp")  # Default to /tmp if not set

def check_database_integrity():
    """Check if databases exist and are accessible."""
    try:
        # Check if database files exist
        db_files = [os.path.join(DATABASE_PATH, "users.db"),
                    os.path.join(DATABASE_PATH, "tweets.db"),
                    os.path.join(DATABASE_PATH, "stats.db")]
        missing_files = [file for file in db_files if not os.path.exists(file)]

        if missing_files:
            logger.warning(f"Missing database files: {', '.join(missing_files)}")
            return False

        # Try to open each database
        for db_file in db_files:
            if os.path.exists(db_file):
                conn = sqlite3.connect(db_file)
                conn.close()

        return True
    except Exception as e:
        logger.error(f"Database integrity check failed: {e}")
        return False

def create_databases():
    """Create or update database tables with enhanced schema."""
    try:
        # Users database
        users_db_path = os.path.join(DATABASE_PATH, "users.db")
        conn_users = sqlite3.connect(users_db_path)
        c_users = conn_users.cursor()

        # Create users table if it doesn't exist
        c_users.execute('''CREATE TABLE IF NOT EXISTS users (
                            mastodon_id TEXT PRIMARY KEY,
                            access_token TEXT NOT NULL,
                            username TEXT,
                            display_name TEXT,
                            profile_url TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        # Check if we need to add new columns to existing table
        c_users.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in c_users.fetchall()]

        # Add new columns if they don't exist
        try:
            if "username" not in columns:
                c_users.execute("ALTER TABLE users ADD COLUMN username TEXT")
            if "display_name" not in columns:
                c_users.execute("ALTER TABLE users ADD COLUMN display_name TEXT")
            if "profile_url" not in columns:
                c_users.execute("ALTER TABLE users ADD COLUMN profile_url TEXT")
            if "created_at" not in columns:
                c_users.execute("ALTER TABLE users ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        except sqlite3.OperationalError as e:
            logger.warning(f"Error adding columns to users table: {e}")

        conn_users.commit()
        conn_users.close()

        # Tweets database
        tweets_db_path = os.path.join(DATABASE_PATH, "tweets.db")
        conn_tweets = sqlite3.connect(tweets_db_path)
        c_tweets = conn_tweets.cursor()

        # Create tweets table if it doesn't exist
        c_tweets.execute('''CREATE TABLE IF NOT EXISTS tweets (
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
                            FOREIGN KEY (user_id) REFERENCES users(mastodon_id))''')

        # Check if we need to add new columns to existing table
        c_tweets.execute("PRAGMA table_info(tweets)")
        columns = [column[1] for column in c_tweets.fetchall()]

        # Add new columns if they don't exist
        try:
            if "visibility" not in columns:
                c_tweets.execute("ALTER TABLE tweets ADD COLUMN visibility TEXT DEFAULT 'public'")
            if "media_urls" not in columns:
                c_tweets.execute("ALTER TABLE tweets ADD COLUMN media_urls TEXT")
            if "status" not in columns:
                c_tweets.execute("ALTER TABLE tweets ADD COLUMN status TEXT DEFAULT 'pending'")
            if "created_at" not in columns:
                c_tweets.execute("ALTER TABLE tweets ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            if "posted_at" not in columns:
                c_tweets.execute("ALTER TABLE tweets ADD COLUMN posted_at TIMESTAMP")
            if "retry_count" not in columns:
                c_tweets.execute("ALTER TABLE tweets ADD COLUMN retry_count INTEGER DEFAULT 0")
        except sqlite3.OperationalError as e:
            logger.warning(f"Error adding columns to tweets table: {e}")

        conn_tweets.commit()
        conn_tweets.close()

        # Create stats database for analytics
        try:
            stats_db_path = os.path.join(DATABASE_PATH, "stats.db")
            conn_stats = sqlite3.connect(stats_db_path)
            c_stats = conn_stats.cursor()

            c_stats.execute('''CREATE TABLE IF NOT EXISTS post_stats (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                tweet_id INTEGER,
                                user_id TEXT NOT NULL,
                                post_time TIMESTAMP,
                                status TEXT,
                                error_message TEXT,
                                FOREIGN KEY (user_id) REFERENCES users(mastodon_id),
                                FOREIGN KEY (tweet_id) REFERENCES tweets(id))''')

            conn_stats.commit()
            conn_stats.close()
        except Exception as e:
            logger.warning(f"Error creating stats database: {e}")

        logger.info("Databases initialized successfully with enhanced schema")
        return True

    except Exception as e:
        logger.error(f"Error initializing databases: {e}")
        return False

def migrate_data():
    """Migrate existing data to new schema if needed."""
    try:
        # Check if tweets table exists
        tweets_db_path = os.path.join(DATABASE_PATH, "tweets.db")
        if not os.path.exists(tweets_db_path):
            logger.info("No tweets database found, skipping migration")
            return True

        # Update existing tweets to have status='pending'
        conn_tweets = sqlite3.connect(tweets_db_path)
        c_tweets = conn_tweets.cursor()

        # Check if status column exists
        c_tweets.execute("PRAGMA table_info(tweets)")
        columns = [column[1] for column in c_tweets.fetchall()]

        if "status" in columns:
            try:
                c_tweets.execute("UPDATE tweets SET status = 'pending' WHERE status IS NULL")
                conn_tweets.commit()
            except sqlite3.OperationalError as e:
                logger.warning(f"Error updating status column: {e}")

        conn_tweets.close()

        logger.info("Data migration completed successfully")
        return True
    except Exception as e:
        logger.error(f"Error migrating data: {e}")
        return False

def repair_database():
    """Attempt to repair database if corrupted."""
    try:
        # Check if databases exist
        if not check_database_integrity():
            # Try to create new databases
            logger.info("Attempting to repair databases")
            create_databases()
            return True
    except Exception as e:
        logger.error(f"Error repairing database: {e}")
        return False

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("database.log"),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger("mastodon_scheduler")

    # Check database integrity
    if not check_database_integrity():
        logger.warning("Database integrity check failed, attempting repair")
        repair_database()

    create_databases()
    migrate_data()
    print("Databases initialized and migrated successfully.")
