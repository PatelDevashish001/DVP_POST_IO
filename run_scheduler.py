import subprocess
import os
import sys
import time

def start_scheduler():
    """Start the Mastodon scheduler as a background process"""
    print("Starting Mastodon Tweet Scheduler...")
    
    # Get the current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Path to the post.py script
    post_script = os.path.join(current_dir, "post.py")
    
    # Path for log file
    log_file = os.path.join(current_dir, "scheduler_output.log")
    
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
            print("\nTo stop the scheduler, press Ctrl+C in the terminal where it's running")
            print("or use the command: kill {process.pid}")
            
            # Wait a moment to see if the process crashes immediately
            time.sleep(2)
            
            # Check if process is still running
            if process.poll() is None:
                print("Scheduler is running successfully!")
            else:
                print(f"Scheduler failed to start. Exit code: {process.returncode}")
                print(f"Check the log file at {log_file} for details")
    
    except Exception as e:
        print(f"Error starting scheduler: {e}")

if __name__ == "__main__":
    start_scheduler() 