#!/usr/bin/env python3
"""
DVP POST IO - Mastodon Post Scheduler (PostgreSQL Version)
----------------------------------------------------------
This script checks for scheduled posts and publishes them to Mastodon.
It runs continuously, checking for new posts every 10 seconds.
"""

# import sqlite3 # Remove SQLite
import psycopg2 # Use PostgreSQL driver
import psycopg2.extras # For DictCursor
import time
import sys
import os
import fcntl # File locking (remains the same)
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

# Simple console logging (remains the same)
def log(message, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")

# --- Database Connection Function ---
def get_connection():
    """Establish connection to Render PostgreSQL database."""
    return psycopg2.connect(config.RENDER_DATABASE_URL)
# Removed check_databases (file check) - Replaced by connection check in check_config

def check_config():
    """Check if required configuration is available"""
    required_mastodon_vars = ["CLIENT_ID", "CLIENT_SECRET", "MASTODON_BASE_URL"]
    required_postgres_vars = ["POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_HOST", "POSTGRES_PORT"]
    missing = []

    for var in required_mastodon_vars + required_postgres_vars:
        if not hasattr(config, var) or not getattr(config, var): # Check for None or empty string
            missing.append(var)

    if missing:
        log(f"Missing required configuration: {', '.join(missing)}", "ERROR")
        log("Please check your .env file and config.py", "ERROR")
        return False

    # --- Add connection check ---
    conn = None
    try:
        log("Attempting to connect to PostgreSQL database...")
        conn = get_connection()
        log("Database connection successful.")
        return True
    except Exception as e:
        # Error logged within get_connection or here
        log(f"Database connection check failed.", "ERROR")
        return False
    finally:
        if conn:
            conn.close()


# --- File Locking Functions (fcntl remain unchanged) ---
def acquire_lock(lock_file):
    """Acquire a lock to prevent multiple instances from processing the same posts"""
    try:
        lock_fd = open(lock_file, 'w')
        # Use non-blocking exclusive lock
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Write PID to lock file for debugging
        lock_fd.write(str(os.getpid()))
        lock_fd.flush()
        return lock_fd
    except IOError: # Catching IOError indicates the lock is held
        return None
    except Exception as e: # Catch other potential errors
        log(f"Error acquiring lock: {e}", "ERROR")
        return None

def release_lock(lock_fd):
    """Release the lock"""
    if lock_fd:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()
        except Exception as e:
            log(f"Error releasing lock: {e}", "ERROR")

# --- Processing State Functions (Converted to PostgreSQL) ---
def mark_as_processing(conn, tweet_id):
    """Mark a tweet as being processed in PostgreSQL"""
    processing_id = hashlib.md5(f"{tweet_id}_{datetime.now().timestamp()}".encode()).hexdigest()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # First check if the tweet is still in pending state
            cur.execute("SELECT status FROM tweets WHERE id = %s", (tweet_id,))
            result = cur.fetchone()
            if not result or result['status'] != 'pending':
                log(f"Tweet {tweet_id} is no longer pending (status: {result['status'] if result else 'not found'})", "WARNING")
                return False

            # Use NOW() for timestamp, %s for placeholders
            cur.execute("""
                UPDATE tweets
                SET status = 'processing',
                    processing_id = %s,
                    processing_started = NOW()
                WHERE id = %s AND status = 'pending'
            """, (processing_id, tweet_id))

            # Check if the update affected any row
            if cur.rowcount == 0:
                log(f"Failed to mark tweet {tweet_id} as processing (race condition or already processed?)", "WARNING")
                # No commit needed if nothing changed, but rollback just in case transaction started implicitly
                conn.rollback()
                return False

        conn.commit() # Commit the successful update
        return processing_id
    except (Exception, psycopg2.Error) as e:
        log(f"Error marking tweet {tweet_id} as processing: {e}", "ERROR")
        conn.rollback() # Rollback on error
        return False

def verify_processing_id(conn, tweet_id, processing_id):
    """Verify that we still own the processing lock for this tweet in PostgreSQL"""
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT processing_id FROM tweets WHERE id = %s AND status = 'processing'", (tweet_id,))
            result = cur.fetchone()

            if not result:
                log(f"Tweet {tweet_id} is no longer in processing state (verify step)", "WARNING")
                return False

            if result['processing_id'] != processing_id:
                log(f"Tweet {tweet_id} processing lock mismatch (current: {result['processing_id']}, expected: {processing_id})", "WARNING")
                return False

            return True
    except (Exception, psycopg2.Error) as e:
        log(f"Error verifying processing ID for tweet {tweet_id}: {e}", "ERROR")
        return False

# --- Schema Update Function (Converted to PostgreSQL) ---
def ensure_schema_updated(conn):
    """Ensure the PostgreSQL database schema has the necessary columns"""
    try:
        with conn.cursor() as cur:
            schema_changed = False

            # Check for processing_id column
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'tweets' AND column_name = 'processing_id'
                );
            """)
            if not cur.fetchone()[0]:
                log("Adding 'processing_id' column to 'tweets' table...")
                cur.execute("ALTER TABLE tweets ADD COLUMN processing_id TEXT NULL;")
                schema_changed = True

            # Check for processing_started column
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'tweets' AND column_name = 'processing_started'
                );
            """)
            if not cur.fetchone()[0]:
                log("Adding 'processing_started' column to 'tweets' table...")
                # Use TIMESTAMPTZ for PostgreSQL timestamps with timezone
                cur.execute("ALTER TABLE tweets ADD COLUMN processing_started TIMESTAMPTZ NULL;")
                schema_changed = True

            if schema_changed:
                conn.commit() # Commit schema changes
                log("Database schema updated successfully.", "INFO")
            else:
                log("Database schema check complete. No changes needed.", "INFO")
        return True
    except (Exception, psycopg2.Error) as e:
        log(f"Error updating schema: {e}", "ERROR")
        conn.rollback() # Rollback potential partial changes
        return False

# --- Main Scheduler Function (Converted to PostgreSQL) ---
def post_scheduled_tweets():
    """Main function to check for and post scheduled tweets using PostgreSQL"""
    log("Starting DVP POST IO Scheduler (PostgreSQL Version)")

    # Check configuration and database connection
    if not check_config():
        log("Cannot start scheduler: Initial checks failed.", "CRITICAL")
        return # Exit if config/connection is bad

    # Create lock file path (remains the same)
    lock_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scheduler.lock")

    # Initialize database schema if needed
    conn_init = None
    try:
        conn_init = get_connection()
        if not ensure_schema_updated(conn_init):
             log("Failed to ensure database schema is up-to-date. Exiting.", "CRITICAL")
             return
    except Exception as e:
        log(f"Failed during initial schema check: {e}", "CRITICAL")
        return # Exit if initial check fails
    finally:
        if conn_init:
            conn_init.close()

    # Reset any tweets stuck in 'processing' state
    conn_reset = None
    try:
        conn_reset = get_connection()
        with conn_reset.cursor() as cur:
            # Reset status and clear processing fields
            cur.execute("""
                UPDATE tweets SET status = 'pending', processing_id = NULL, processing_started = NULL
                WHERE status = 'processing'
            """)
            reset_count = cur.rowcount
        if reset_count > 0:
            conn_reset.commit() # Commit the reset
            log(f"Reset {reset_count} tweets from 'processing' to 'pending' state.", "INFO")
        else:
            conn_reset.rollback() # No changes, just rollback
            log("No tweets found stuck in 'processing' state.", "INFO")
    except Exception as e:
        log(f"Error resetting processing tweets: {e}", "ERROR")
        if conn_reset:
            conn_reset.rollback()
    finally:
        if conn_reset:
            conn_reset.close()

    log("Scheduler initialized. Will check for tweets every 10 seconds.")
    print("\nPress Ctrl+C to stop the scheduler")

    # --- Main Loop ---
    while True:
        lock_fd = None
        conn_main = None # Connection for this loop iteration
        try:
            # Try to acquire file lock
            lock_fd = acquire_lock(lock_file)
            if not lock_fd:
                # Don't log every time, maybe less frequently?
                # log("Another instance is already running. Waiting...", "DEBUG")
                time.sleep(10)
                continue

            log("Acquired lock. Checking for pending tweets...", "DEBUG")

            # Get current time for comparison (use timezone-aware if possible, or rely on DB timezone)
            # PostgreSQL TIMESTAMPTZ handles timezones well. Using simple string comparison might
            # be okay if schedule_time is stored consistently, but NOW() is safer.
            # current_time_for_query = datetime.now() # Use NOW() in query instead

            conn_main = get_connection()
            with conn_main.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:

                # Find tweets that are due (schedule_time <= NOW()) and pending
                cur.execute("""
                    SELECT id, user_id, message, schedule_time,
                           COALESCE(visibility, 'public') as visibility
                    FROM tweets
                    WHERE schedule_time <= NOW() AND status = 'pending'
                    ORDER BY schedule_time
                    LIMIT 5 -- Process in small batches
                """, ) # No parameters needed for NOW()

                tweets = cur.fetchall()

                if tweets:
                    log(f"Found {len(tweets)} tweets to post", "INFO")

                    for tweet in tweets:
                        tweet_id = tweet['id']
                        user_id = tweet['user_id']
                        message = tweet['message']
                        visibility = tweet['visibility']

                        log(f"Processing tweet ID {tweet_id}: '{message[:30]}...'", "INFO")

                        # Mark as processing within the same transaction context if possible
                        # The mark_as_processing function handles its own commit/rollback
                        processing_id = mark_as_processing(conn_main, tweet_id)
                        if not processing_id:
                            log(f"Skipping tweet ID {tweet_id} - could not mark as processing", "WARNING")
                            continue # Try next tweet

                        # Get user's access token (uses the same connection)
                        access_token = None
                        try:
                            with conn_main.cursor(cursor_factory=psycopg2.extras.DictCursor) as user_cur:
                                user_cur.execute("SELECT access_token FROM users WHERE mastodon_id = %s", (user_id,))
                                user_result = user_cur.fetchone()
                                if user_result:
                                    access_token = user_result['access_token']
                        except (Exception, psycopg2.Error) as db_err:
                             log(f"Database error fetching access token for user {user_id}: {db_err}", "ERROR")
                             # Attempt to reset tweet status before continuing
                             try:
                                 with conn_main.cursor() as reset_cur:
                                     reset_cur.execute("""
                                        UPDATE tweets SET status='pending', processing_id=NULL, processing_started=NULL
                                        WHERE id = %s AND processing_id = %s
                                     """, (tweet_id, processing_id))
                                 conn_main.commit()
                             except Exception as reset_e:
                                 log(f"Failed to reset status for tweet {tweet_id} after token fetch error: {reset_e}", "ERROR")
                                 conn_main.rollback()
                             continue # Skip to next tweet

                        if not access_token:
                            log(f"No access token found for user {user_id}. Marking tweet {tweet_id} as failed.", "ERROR")
                            try:
                                with conn_main.cursor() as fail_cur:
                                    fail_cur.execute("""
                                        UPDATE tweets SET status = 'failed', processing_id = NULL, processing_started = NULL
                                        WHERE id = %s AND processing_id = %s
                                        """, (tweet_id, processing_id))
                                conn_main.commit()
                            except Exception as fail_e:
                                log(f"Failed to mark tweet {tweet_id} as failed after missing token: {fail_e}", "ERROR")
                                conn_main.rollback()
                            continue # Skip to next tweet

                        # --- Post to Mastodon ---
                        post_error = None
                        try:
                            # Verify we still own the processing lock before posting
                            if not verify_processing_id(conn_main, tweet_id, processing_id):
                                log(f"Lost processing lock for tweet ID {tweet_id} before posting", "WARNING")
                                # Don't rollback here, another process is handling it
                                continue # Skip to next tweet

                            mastodon_client = Mastodon(
                                access_token=access_token,
                                api_base_url=config.MASTODON_BASE_URL
                            )

                            log(f"Posting tweet ID {tweet_id} with visibility: {visibility}", "INFO")
                            mastodon_client.status_post(
                                status=message,
                                visibility=visibility
                            )
                            log(f"Successfully posted tweet ID {tweet_id}", "SUCCESS")
                            print(f"✅ Posted: '{message[:50]}...'")

                            # Mark as posted in DB
                            try:
                                with conn_main.cursor() as post_cur:
                                     # Verify lock again before final update
                                     if not verify_processing_id(conn_main, tweet_id, processing_id):
                                         log(f"Lost processing lock for tweet ID {tweet_id} after posting, cannot mark as posted", "WARNING")
                                         # Don't commit/rollback - let the other process handle it
                                         continue
                                     post_cur.execute("""
                                         UPDATE tweets
                                         SET status = 'posted',
                                             posted_at = NOW(),
                                             processing_id = NULL,
                                             processing_started = NULL
                                         WHERE id = %s AND processing_id = %s
                                     """, (tweet_id, processing_id))
                                     if post_cur.rowcount == 0:
                                          log(f"Failed to mark tweet {tweet_id} as posted (lost lock or already updated?)", "WARNING")
                                          conn_main.rollback() # Rollback this attempt
                                     else:
                                         conn_main.commit() # Commit 'posted' status
                            except (Exception, psycopg2.Error) as db_post_err:
                                log(f"Database error marking tweet {tweet_id} as posted: {db_post_err}", "ERROR")
                                conn_main.rollback()
                                # Tweet is posted but status not updated - requires manual check later

                        except Exception as e:
                            # Handle Mastodon API errors or other issues during posting
                            post_error = e
                            log(f"Error posting tweet ID {tweet_id}: {post_error}", "ERROR")
                            print(f"❌ Error posting tweet {tweet_id}: {post_error}")

                            # Attempt to update retry count / mark as failed / reset to pending
                            try:
                                with conn_main.cursor() as retry_cur:
                                     # Verify lock again before updating status after error
                                     if not verify_processing_id(conn_main, tweet_id, processing_id):
                                         log(f"Lost processing lock for tweet ID {tweet_id} after posting error, cannot update status", "WARNING")
                                         # Don't commit/rollback
                                         continue # Skip this tweet

                                     # Increment retry_count, check if it exceeds limit (e.g., 3 retries)
                                     retry_cur.execute("""
                                        UPDATE tweets
                                        SET retry_count = COALESCE(retry_count, 0) + 1,
                                            status = CASE WHEN COALESCE(retry_count, 0) + 1 >= 3 THEN 'failed' ELSE 'pending' END,
                                            error_message = %s, -- Store the error message
                                            processing_id = NULL,
                                            processing_started = NULL
                                        WHERE id = %s AND processing_id = %s
                                     """, (str(post_error)[:500], tweet_id, processing_id)) # Limit error message size
                                     if retry_cur.rowcount == 0:
                                         log(f"Failed to update status/retry for tweet {tweet_id} after error (lost lock?)", "WARNING")
                                         conn_main.rollback()
                                     else:
                                         conn_main.commit() # Commit the retry/failed status
                                         log(f"Updated status/retry for tweet {tweet_id} after error.", "INFO")
                            except (Exception, psycopg2.Error) as db_retry_err:
                                log(f"Database error updating retry/status for tweet {tweet_id}: {db_retry_err}", "ERROR")
                                conn_main.rollback() # Rollback retry update attempt

                        # --- End of single tweet processing ---
                    # --- End of tweet processing loop ---
                else:
                    log("No pending tweets found this cycle.", "DEBUG")

        except (Exception, psycopg2.Error) as e:
            log(f"Error in main scheduler loop: {e}", "ERROR")
            if conn_main:
                try:
                    conn_main.rollback() # Attempt rollback on general loop errors
                except Exception as rb_e:
                    log(f"Error during rollback attempt: {rb_e}", "ERROR")
        finally:
            # Always release the file lock
            release_lock(lock_fd)
            # Always close the connection for this loop iteration
            if conn_main:
                conn_main.close()
            log("Released lock, cycle complete.", "DEBUG")


        # Wait before checking again
        time.sleep(10)
        sys.stdout.flush() # Ensure output is displayed immediately

# --- Main Execution Block ---
if __name__ == "__main__":
    try:
        post_scheduled_tweets()
    except KeyboardInterrupt:
        log("Scheduler stopped by user (Ctrl+C)", "INFO")
        print("\nScheduler stopped.")
    except Exception as e:
        # Catch unexpected fatal errors
        log(f"Scheduler CRASHED with unhandled exception: {e}", "CRITICAL")
        import traceback
        traceback.print_exc() # Print full traceback for debugging
        print(f"\nScheduler CRASHED. Check logs. Error: {e}")
        # Consider cleaning up lock file if possible, though it might be stuck
        sys.exit(1) # Exit with error code
