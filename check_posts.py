#!/usr/bin/env python3
"""
DVP POST IO - Check Post Status
-----------------------------
This script checks the status of posts in the database.
"""

import sqlite3
from datetime import datetime

def check_tweets():
    """Check the status of tweets in the database"""
    print("\n=== DVP POST IO Status Check ===")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("===============================\n")
    
    try:
        # Connect to tweets database
        with sqlite3.connect("tweets.db") as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            
            # Get all tweets
            c.execute("""
                SELECT id, user_id, message, schedule_time, visibility, status, 
                       posted_at, retry_count, processing_id, processing_started
                FROM tweets
                ORDER BY schedule_time DESC
            """)
            
            tweets = c.fetchall()
            
            if not tweets:
                print("No tweets found in the database.")
                return
            
            print(f"Found {len(tweets)} tweets in the database:\n")
            
            # Count by status
            c.execute("""
                SELECT status, COUNT(*) as count
                FROM tweets
                GROUP BY status
            """)
            
            status_counts = c.fetchall()
            
            for status in status_counts:
                status_text = status['status'] or 'unknown'
                status_icon = "✅" if status_text == "posted" else "⏳" if status_text == "pending" else "🔄" if status_text == "processing" else "❌"
                print(f"{status_icon} {status_text}: {status['count']}")
            
            print("\n=== Recent Tweets ===\n")
            
            # Print details of recent tweets
            for tweet in tweets[:5]:  # Show only the 5 most recent tweets
                status = tweet['status'] or 'unknown'
                status_icon = "✅" if status == "posted" else "⏳" if status == "pending" else "🔄" if status == "processing" else "❌"
                
                print(f"{status_icon} Tweet ID: {tweet['id']}")
                print(f"   Message: {tweet['message'][:50]}...")
                print(f"   Scheduled: {tweet['schedule_time']}")
                print(f"   Status: {status}")
                
                if tweet['posted_at']:
                    print(f"   Posted at: {tweet['posted_at']}")
                
                if tweet['retry_count']:
                    print(f"   Retry count: {tweet['retry_count']}")
                    
                if tweet['processing_id']:
                    print(f"   Processing ID: {tweet['processing_id'][:8]}...")
                    print(f"   Processing started: {tweet['processing_started']}")
                
                print("")
                
            # Check for stuck processing tweets
            c.execute("""
                SELECT id, processing_started
                FROM tweets
                WHERE status = 'processing'
                AND datetime(processing_started) < datetime('now', '-10 minute')
            """)
            
            stuck_tweets = c.fetchall()
            if stuck_tweets:
                print("\n=== Stuck Processing Tweets ===\n")
                print(f"Found {len(stuck_tweets)} tweets stuck in processing state for more than 10 minutes:")
                
                for tweet in stuck_tweets:
                    print(f"   Tweet ID: {tweet['id']}, Processing started: {tweet['processing_started']}")
                
                print("\nTo reset these tweets, run:")
                print("   python -c \"import sqlite3; conn = sqlite3.connect('tweets.db'); c = conn.cursor(); c.execute('UPDATE tweets SET status = \\'pending\\', processing_id = NULL, processing_started = NULL WHERE status = \\'processing\\''); conn.commit(); print('Reset', c.rowcount, 'tweets')\"")
    
    except Exception as e:
        print(f"Error checking tweets: {e}")

if __name__ == "__main__":
    check_tweets() 