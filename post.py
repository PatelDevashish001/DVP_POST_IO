#!/usr/bin/env python3

import psycopg2
import psycopg2.extras
import time
import sys
import os
import fcntl
from datetime import datetime
from mastodon import Mastodon
import hashlib

try:
    import config
except ImportError as e:
    sys.exit(1)

def get_connection():
    return psycopg2.connect(config.RENDER_DATABASE_URL)

def check_config():
    required_mastodon_vars = ["CLIENT_ID", "CLIENT_SECRET", "MASTODON_BASE_URL"]
    required_postgres_vars = ["POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_HOST", "POSTGRES_PORT"]
    missing = []

    for var in required_mastodon_vars + required_postgres_vars:
        if not hasattr(config, var) or not getattr(config, var):
            missing.append(var)

    if missing:
        return False

    conn = None
    try:
        conn = get_connection()
        return True
    except Exception as e:
        return False
    finally:
        if conn:
            conn.close()

def acquire_lock(lock_file):
    try:
        lock_fd = open(lock_file, 'w')
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Removed PID writing
        return lock_fd
    except IOError:
        return None
    except Exception as e:
        return None

def release_lock(lock_fd):
    if lock_fd:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()
        except Exception as e:
            pass # Ignore errors on release

def mark_as_processing(conn, tweet_id):
    processing_id = hashlib.md5(f"{tweet_id}_{datetime.now().timestamp()}".encode()).hexdigest()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT status FROM tweets WHERE id = %s", (tweet_id,))
            result = cur.fetchone()
            if not result or result['status'] != 'pending':
                return False

            cur.execute("""
                UPDATE tweets
                SET status = 'processing',
                    processing_id = %s,
                    processing_started = NOW()
                WHERE id = %s AND status = 'pending'
            """, (processing_id, tweet_id))

            if cur.rowcount == 0:
                conn.rollback()
                return False

        conn.commit()
        return processing_id
    except (Exception, psycopg2.Error) as e:
        conn.rollback()
        return False

def verify_processing_id(conn, tweet_id, processing_id):
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT processing_id FROM tweets WHERE id = %s AND status = 'processing'", (tweet_id,))
            result = cur.fetchone()

            if not result:
                return False

            if result['processing_id'] != processing_id:
                return False

            return True
    except (Exception, psycopg2.Error) as e:
        return False

def ensure_schema_updated(conn):
    try:
        with conn.cursor() as cur:
            schema_changed = False

            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'tweets' AND column_name = 'processing_id'
                );
            """)
            if not cur.fetchone()[0]:
                cur.execute("ALTER TABLE tweets ADD COLUMN processing_id TEXT NULL;")
                schema_changed = True

            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'tweets' AND column_name = 'processing_started'
                );
            """)
            if not cur.fetchone()[0]:
                cur.execute("ALTER TABLE tweets ADD COLUMN processing_started TIMESTAMPTZ NULL;")
                schema_changed = True

            if schema_changed:
                conn.commit()
        return True
    except (Exception, psycopg2.Error) as e:
        conn.rollback()
        return False

def post_scheduled_tweets():
    if not check_config():
        return

    lock_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scheduler.lock")

    conn_init = None
    try:
        conn_init = get_connection()
        if not ensure_schema_updated(conn_init):
             return
    except Exception as e:
        return
    finally:
        if conn_init:
            conn_init.close()

    conn_reset = None
    try:
        conn_reset = get_connection()
        with conn_reset.cursor() as cur:
            cur.execute("""
                UPDATE tweets SET status = 'pending', processing_id = NULL, processing_started = NULL
                WHERE status = 'processing'
            """)
            reset_count = cur.rowcount
        if reset_count > 0:
            conn_reset.commit()
        else:
            conn_reset.rollback()
    except Exception as e:
        if conn_reset:
            conn_reset.rollback()
    finally:
        if conn_reset:
            conn_reset.close()

    while True:
        lock_fd = None
        conn_main = None
        try:
            lock_fd = acquire_lock(lock_file)
            if not lock_fd:
                time.sleep(10)
                continue

            conn_main = get_connection()
            with conn_main.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("""
                    SELECT id, user_id, message, schedule_time,
                           COALESCE(visibility, 'public') as visibility
                    FROM tweets
                    WHERE schedule_time <= NOW() AND status = 'pending'
                    ORDER BY schedule_time
                    LIMIT 5
                """)
                tweets = cur.fetchall()

                if tweets:
                    for tweet in tweets:
                        tweet_id = tweet['id']
                        user_id = tweet['user_id']
                        message = tweet['message']
                        visibility = tweet['visibility']

                        processing_id = mark_as_processing(conn_main, tweet_id)
                        if not processing_id:
                            continue

                        access_token = None
                        try:
                            with conn_main.cursor(cursor_factory=psycopg2.extras.DictCursor) as user_cur:
                                user_cur.execute("SELECT access_token FROM users WHERE mastodon_id = %s", (user_id,))
                                user_result = user_cur.fetchone()
                                if user_result:
                                    access_token = user_result['access_token']
                        except (Exception, psycopg2.Error) as db_err:
                             try:
                                 with conn_main.cursor() as reset_cur:
                                     reset_cur.execute("""
                                        UPDATE tweets SET status='pending', processing_id=NULL, processing_started=NULL
                                        WHERE id = %s AND processing_id = %s
                                     """, (tweet_id, processing_id))
                                 conn_main.commit()
                             except Exception as reset_e:
                                 conn_main.rollback()
                             continue

                        if not access_token:
                            try:
                                with conn_main.cursor() as fail_cur:
                                    fail_cur.execute("""
                                        UPDATE tweets SET status = 'failed', processing_id = NULL, processing_started = NULL
                                        WHERE id = %s AND processing_id = %s
                                        """, (tweet_id, processing_id))
                                conn_main.commit()
                            except Exception as fail_e:
                                conn_main.rollback()
                            continue

                        post_error = None
                        try:
                            if not verify_processing_id(conn_main, tweet_id, processing_id):
                                continue

                            mastodon_client = Mastodon(
                                access_token=access_token,
                                api_base_url=config.MASTODON_BASE_URL
                            )

                            mastodon_client.status_post(
                                status=message,
                                visibility=visibility
                            )

                            try:
                                with conn_main.cursor() as post_cur:
                                     if not verify_processing_id(conn_main, tweet_id, processing_id):
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
                                          conn_main.rollback()
                                     else:
                                         conn_main.commit()
                            except (Exception, psycopg2.Error) as db_post_err:
                                conn_main.rollback()

                        except Exception as e:
                            post_error = e
                            try:
                                with conn_main.cursor() as retry_cur:
                                     if not verify_processing_id(conn_main, tweet_id, processing_id):
                                         continue

                                     retry_cur.execute("""
                                        UPDATE tweets
                                        SET retry_count = COALESCE(retry_count, 0) + 1,
                                            status = CASE WHEN COALESCE(retry_count, 0) + 1 >= 3 THEN 'failed' ELSE 'pending' END,
                                            error_message = %s,
                                            processing_id = NULL,
                                            processing_started = NULL
                                        WHERE id = %s AND processing_id = %s
                                     """, (str(post_error)[:500], tweet_id, processing_id))
                                     if retry_cur.rowcount == 0:
                                         conn_main.rollback()
                                     else:
                                         conn_main.commit()
                            except (Exception, psycopg2.Error) as db_retry_err:
                                conn_main.rollback()
                # else: # No pending tweets
                #     pass # No action needed

        except (Exception, psycopg2.Error) as e:
            if conn_main:
                try:
                    conn_main.rollback()
                except Exception as rb_e:
                    pass # Ignore rollback errors
        finally:
            release_lock(lock_fd)
            if conn_main:
                conn_main.close()

        time.sleep(10)

if __name__ == "__main__":
    try:
        post_scheduled_tweets()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        sys.exit(1)
