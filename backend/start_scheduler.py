#!/usr/bin/env python3
"""
Start DVP POST IO Scheduler
-------------------------
This script starts the post scheduler as a background process.
It detects the operating system and runs the appropriate version of the post.py script.
"""

import subprocess
import os
import sys
import time
import platform

def start_scheduler():
    """Start the Mastadon scheduler as a background process"""
    print("\n=== Starting DVP POST IO Scheduler ===\n")
    
    # Get the current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Determine which script to run based on the operating system
    if platform.system() == "Windows":
        post_script = os.path.join(current_dir, "post_windows.py")
        if not os.path.exists(post_script):
            print(f"Error: {post_script} not found.")
            print("Please make sure post_windows.py exists in the same directory.")
            return
    else:
        post_script = os.path.join(current_dir, "post.py")
        if not os.path.exists(post_script):
            print(f"Error: {post_script} not found.")
            print("Please make sure post.py exists in the same directory.")
            return
    
    # Path for log file
    log_file = os.path.join(current_dir, "scheduler.log")
    
    try:
        # Open log file
        with open(log_file, "w") as log:
            # Start the process
            process = subprocess.Popen(
                [sys.executable, post_script],
                stdout=log,
                stderr=log,
                cwd=current_dir
            )
            
            print(f"Scheduler started with PID: {process.pid}")
            print(f"Output is being logged to: {log_file}")
            
            # Wait a moment to see if the process crashes immediately
            time.sleep(2)
            
            # Check if process is still running
            if process.poll() is None:
                print("\nScheduler is running successfully!")
                print("\nTo check the status of posts, run:")
                print("  python check_tweets.py")
                print("\nTo stop the scheduler, run:")
                if platform.system() == "Windows":
                    print(f"  taskkill /PID {process.pid} /F")
                else:
                    print(f"  kill {process.pid}")
            else:
                print(f"\nScheduler failed to start. Exit code: {process.returncode}")
                print(f"Check the log file at {log_file} for details")
    
    except Exception as e:
        print(f"Error starting scheduler: {e}")

if __name__ == "__main__":
    start_scheduler() 