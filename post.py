#!/usr/bin/env python3
"""
DVP POST IO - Mastodon Post Scheduler
------------------------------------
This script checks for scheduled posts and publishes them to Mastodon.
It runs continuously, checking for new posts every 10 seconds.
"""

import sqlite3
import time
import sys
import os
import fcntl
from datetime import datetime
from mastodon import Mastodon
import hashlib

# Import config after environment variables are loaded
try:
    import config
except ImportError as e:
    print(f"Error importing config: {e}")
    print("Make sure config.py exists and is properly configured.")
    sys.exit(1)

# Simple console logging
def log(message, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")

def check_databases():
    """Check if required database files exist"""
    required_files = ["users.db", "tweets.db"]
    missing = []
    
    for file in required_files:
        if not os.path.exists(file):
            missing.append(file)
    
    if missing:
        log(f"Missing database files: {', '.join(missing)}", "ERROR")
        return False
    
    return True

def check_config():
    """Check if required configuration is available"""
    required_vars = ["CLIENT_ID", "CLIENT_SECRET", "MASTODON_BASE_URL"]
    missing = []
    
    for var in required_vars:
        if not hasattr(config, var) or getattr(config, var) is None:
            missing.append(var)
    
    if missing:
        log(f"Missing required configuration: {', '.join(missing)}", "ERROR")
        log("Please check your .env file and config.py", "ERROR")
        return False
    
    return True

def acquire_lock(lock_file):
    """Acquire a lock to prevent multiple instances from processing the same posts"""
    try:
        lock_fd = open(lock_file, 'w')
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Write PID to lock file for debugging
        lock_fd.write(str(os.getpid()))
        lock_fd.flush()
        return lock_fd
    except IOError:
        return None

def release_lock(lock_fd):
    """Release the lock"""
    if lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()

def mark_as_processing(conn, tweet_id):
    """Mark a tweet as being processed to prevent duplicate processing"""
    try:
        c = conn.cursor()
        # First check if the tweet is still in pending state
        c.execute("SELECT status FROM tweets WHERE id = ?", (tweet_id,))
        result = c.fetchone()
        if not result or result['status'] != 'pending':
            log(f"Tweet {tweet_id} is no longer pending (status: {result['status'] if result else 'not found'})", "WARNING")
            return False
            
        # Generate a unique processing ID to track this specific processing attempt
        processing_id = hashlib.md5(f"{tweet_id}_{datetime.now().timestamp()}".encode()).hexdigest()
        
        c.execute("""
            UPDATE tweets 
            SET status = 'processing', 
                processing_id = ?,
                processing_started = ?
            WHERE id = ? AND status = 'pending'
        """, (processing_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), tweet_id))
        
        conn.commit()
        
        # Verify the update was successful
        if c.rowcount == 0:
            log(f"Failed to mark tweet {tweet_id} as processing (race condition)", "WARNING")
            return False
            
        return processing_id
    except Exception as e:
        log(f"Error marking tweet {tweet_id} as processing: {e}", "ERROR")
        return False

def verify_processing_id(conn, tweet_id, processing_id):
    """Verify that we still own the processing lock for this tweet"""
    try:
        c = conn.cursor()
        c.execute("SELECT processing_id FROM tweets WHERE id = ? AND status = 'processing'", (tweet_id,))
        result = c.fetchone()
        
        if not result:
            log(f"Tweet {tweet_id} is no longer in processing state", "WARNING")
            return False
            
        if result['processing_id'] != processing_id:
            log(f"Tweet {tweet_id} is being processed by another instance", "WARNING")
            return False
            
        return True
    except Exception as e:
        log(f"Error verifying processing ID for tweet {tweet_id}: {e}", "ERROR")
        return False

def ensure_schema_updated(conn):
    """Ensure the database schema has the necessary columns"""
    try:
        c = conn.cursor()
        
        # Check if processing_id column exists
        c.execute("PRAGMA table_info(tweets)")
        columns = [column[1] for column in c.fetchall()]
        
        schema_updated = True
        
        if "processing_id" not in columns:
            c.execute("ALTER TABLE tweets ADD COLUMN processing_id TEXT")
            schema_updated = False
            
        if "processing_started" not in columns:
            c.execute("ALTER TABLE tweets ADD COLUMN processing_started TIMESTAMP")
            schema_updated = False
        
        if not schema_updated:
            conn.commit()
            log("Updated database schema with processing columns", "INFO")
        
        return True
    except Exception as e:
        log(f"Error updating schema: {e}", "ERROR")
        return False

def post_scheduled_tweets():
    """Main function to check for and post scheduled tweets"""
    log("Starting DVP POST IO Scheduler")
    
    # Check if required configuration is available
    if not check_config():
        log("Cannot start scheduler: missing configuration", "ERROR")
        return
    
    # Check if database files exist
    if not check_databases():
        log("Cannot start scheduler: missing database files", "ERROR")
        return
    
    # Create lock file path
    lock_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scheduler.lock")
    
    log("Scheduler will check for tweets every 10 seconds")
    print("\nPress Ctrl+C to stop the scheduler")
    
    # Initialize database schema if needed
    try:
        with sqlite3.connect("tweets.db") as conn:
            ensure_schema_updated(conn)
    except Exception as e:
        log(f"Error initializing database schema: {e}", "ERROR")
        return
    
    # Reset any tweets stuck in 'processing' state (from previous crashes)
    try:
        with sqlite3.connect("tweets.db") as conn:
            c = conn.cursor()
            c.execute("UPDATE tweets SET status = 'pending' WHERE status = 'processing'")
            if c.rowcount > 0:
                log(f"Reset {c.rowcount} tweets from 'processing' to 'pending' state", "INFO")
            conn.commit()
    except Exception as e:
        log(f"Error resetting processing tweets: {e}", "ERROR")
    
    while True:
        lock_fd = None
        try:
            # Try to acquire lock
            lock_fd = acquire_lock(lock_file)
            if not lock_fd:
                log("Another instance is already running. Waiting...", "WARNING")
                time.sleep(10)
                continue
            
            # Get current time in the format used in the database
            current_time = datetime.now().strftime("%Y-%m-%dT%H:%M")
            
            # Connect to tweets database
            with sqlite3.connect("tweets.db") as conn:
                conn.row_factory = sqlite3.Row  # Return rows as dictionaries
                c = conn.cursor()
                
                # Find tweets that are due to be posted - only get pending ones
                c.execute("""
                    SELECT id, user_id, message, schedule_time, 
                           COALESCE(visibility, 'public') as visibility
                    FROM tweets 
                    WHERE schedule_time <= ? AND status = 'pending'
                    ORDER BY schedule_time
                    LIMIT 5  -- Process in small batches to avoid long locks
                """, (current_time,))
                
                tweets = c.fetchall()
                
                if tweets:
                    log(f"Found {len(tweets)} tweets to post")
                    
                    # Process each tweet
                    for tweet in tweets:
                        tweet_id = tweet['id']
                        user_id = tweet['user_id']
                        message = tweet['message']
                        schedule_time = tweet['schedule_time']
                        visibility = tweet['visibility']
                        
                        log(f"Processing tweet ID {tweet_id}: '{message[:30]}...'")
                        
                        # Mark as processing to prevent duplicate processing
                        processing_id = mark_as_processing(conn, tweet_id)
                        if not processing_id:
                            log(f"Skipping tweet ID {tweet_id} - could not mark as processing", "WARNING")
                            continue
                        
                        # Get user's access token
                        with sqlite3.connect("users.db") as user_conn:
                            user_conn.row_factory = sqlite3.Row
                            user_c = user_conn.cursor()
                            user_c.execute("SELECT access_token FROM users WHERE mastodon_id = ?", (user_id,))
                            user_result = user_c.fetchone()
                        
                        if not user_result:
                            log(f"No access token found for user {user_id}", "ERROR")
                            # Mark as failed
                            c.execute("UPDATE tweets SET status = 'failed' WHERE id = ?", (tweet_id,))
                            conn.commit()
                            continue
                        
                        access_token = user_result['access_token']
                        
                        try:
                            # Verify we still own the processing lock
                            if not verify_processing_id(conn, tweet_id, processing_id):
                                log(f"Lost processing lock for tweet ID {tweet_id}", "WARNING")
                                continue
                                
                            # Initialize Mastodon API
                            mastodon = Mastodon(
                                access_token=access_token,
                                api_base_url=config.MASTODON_BASE_URL
                            )
                            
                            # Post to Mastodon
                            log(f"Posting tweet with visibility: {visibility}")
                            mastodon.status_post(
                                status=message,
                                visibility=visibility
                            )
                            
                            # Verify we still own the processing lock
                            if not verify_processing_id(conn, tweet_id, processing_id):
                                log(f"Lost processing lock for tweet ID {tweet_id} after posting", "WARNING")
                                continue
                            
                            # Mark as posted
                            c.execute("""
                                UPDATE tweets 
                                SET status = 'posted', 
                                    posted_at = ?,
                                    processing_id = NULL,
                                    processing_started = NULL
                                WHERE id = ? AND processing_id = ?
                            """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), tweet_id, processing_id))
                            
                            if c.rowcount == 0:
                                log(f"Failed to mark tweet {tweet_id} as posted (lost lock)", "WARNING")
                                continue
                                
                            conn.commit()
                            
                            log(f"Successfully posted tweet ID {tweet_id}", "SUCCESS")
                            print(f"✅ Posted: '{message[:50]}...'")
                            
                        except Exception as e:
                            log(f"Error posting tweet ID {tweet_id}: {e}", "ERROR")
                            print(f"❌ Error: {e}")
                            
                            # Verify we still own the processing lock
                            if not verify_processing_id(conn, tweet_id, processing_id):
                                log(f"Lost processing lock for tweet ID {tweet_id} after error", "WARNING")
                                continue
                            
                            # Update retry count
                            c.execute("""
                                UPDATE tweets 
                                SET retry_count = COALESCE(retry_count, 0) + 1,
                                    status = 'pending',
                                    processing_id = NULL,
                                    processing_started = NULL
                                WHERE id = ? AND processing_id = ?
                            """, (tweet_id, processing_id))
                            
                            # Mark as failed if too many retries
                            c.execute("""
                                UPDATE tweets 
                                SET status = CASE WHEN COALESCE(retry_count, 0) >= 3 THEN 'failed' ELSE 'pending' END 
                                WHERE id = ? AND processing_id = ?
                            """, (tweet_id, processing_id))
                            
                            conn.commit()
                else:
                    log("No pending tweets found")
        
        except Exception as e:
            log(f"Error in main loop: {e}", "ERROR")
        finally:
            # Always release the lock
            release_lock(lock_fd)
        
        # Wait before checking again
        time.sleep(10)
        sys.stdout.flush()  # Ensure output is displayed immediately

if __name__ == "__main__":
    try:
        post_scheduled_tweets()
    except KeyboardInterrupt:
        log("Scheduler stopped by user")
        print("\nScheduler stopped")
    except Exception as e:
        log(f"Scheduler crashed: {e}", "CRITICAL")
        print(f"\nFatal error: {e}")
        sys.exit(1) 