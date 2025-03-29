import psycopg2
import logging
import config

logger = logging.getLogger("mastodon_scheduler")

def get_connection():
    """Establish connection to PostgreSQL database."""
    return psycopg2.connect(
        dbname="mastodon_scheduler",  # Change this to your actual DB name
        user="postgres",  # Default PostgreSQL user
        password=config.POSTGRES_PASSWORD,  # Your actual password
        host="localhost",  # Default host
        port="5432"
    )


def check_database_integrity():
    """Check if required tables exist."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        required_tables = ["users", "tweets", "post_stats"]
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'""")
        existing_tables = {row[0] for row in cur.fetchall()}
        
        missing_tables = [table for table in required_tables if table not in existing_tables]
        if missing_tables:
            logger.warning(f"Missing tables: {', '.join(missing_tables)}")
            return False
        
        cur.close()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Database integrity check failed: {e}")
        return False

def create_databases():
    """Create tables with enhanced schema."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # Users table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                mastodon_id TEXT PRIMARY KEY,
                access_token TEXT NOT NULL,
                username TEXT,
                display_name TEXT,
                profile_url TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )''')
        
        # Tweets table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS tweets (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(mastodon_id),
                message TEXT NOT NULL,
                schedule_time TIMESTAMPTZ NOT NULL,
                visibility TEXT DEFAULT 'public',
                media_urls TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                posted_at TIMESTAMPTZ,
                retry_count INTEGER DEFAULT 0
            )''')
        
        # Post Stats table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS post_stats (
                id SERIAL PRIMARY KEY,
                tweet_id INTEGER REFERENCES tweets(id),
                user_id TEXT NOT NULL REFERENCES users(mastodon_id),
                post_time TIMESTAMPTZ,
                status TEXT,
                error_message TEXT
            )''')
        
        conn.commit()
        cur.close()
        conn.close()
        logger.info("Databases initialized successfully with enhanced schema")
        return True
    except Exception as e:
        logger.error(f"Error initializing databases: {e}")
        return False

def migrate_data():
    """Migrate existing data if needed."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='tweets'")
        columns = {row[0] for row in cur.fetchall()}
        
        if "status" in columns:
            cur.execute("UPDATE tweets SET status = 'pending' WHERE status IS NULL")
            conn.commit()
        
        cur.close()
        conn.close()
        logger.info("Data migration completed successfully")
        return True
    except Exception as e:
        logger.error(f"Error migrating data: {e}")
        return False

def repair_database():
    """Attempt to repair database."""
    if not check_database_integrity():
        logger.info("Attempting to repair database")
        create_databases()
        return True
    return False

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("database.log"),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger("mastodon_scheduler")
    
    if not check_database_integrity():
        logger.warning("Database integrity check failed, attempting repair")
        repair_database()
    
    create_databases()
    migrate_data()
    print("Databases initialized and migrated successfully.")
