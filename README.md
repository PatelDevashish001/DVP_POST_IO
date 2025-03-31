# DVP POST IO - Mastodon Post Scheduler (PostgreSQL Version)

DVP POST IO is a web application and background scheduler designed to schedule and automatically publish posts (toots) to Mastodon accounts. It uses Mastodon's OAuth for authentication, stores scheduled posts and user credentials in a PostgreSQL database, and relies on a persistent background script to handle the posting logic.

## Features

*   **Mastodon Authentication:** Securely connect using Mastodon OAuth2.
*   **Post Scheduling:** Schedule posts with specific text content, date/time, and visibility (public, unlisted, private, direct).
*   **PostgreSQL Backend:** Uses PostgreSQL to store user information, access tokens, and scheduled posts.
*   **Background Scheduler:** A dedicated script (`dvp_post_io_pg.py`) runs continuously to check for and publish due posts.
*   **Automatic Posting:** Posts are automatically sent to Mastodon at their scheduled time.
*   **Status Tracking:** Tracks the status of posts (pending, processing, posted, failed).
*   **Basic Error Handling:** Includes simple retry logic and marks posts as failed after several attempts.
*   **Concurrency Control:** Uses file locking (`fcntl`) to prevent multiple instances of the scheduler script from running simultaneously.
*   **Configuration:** Easily configured using environment variables via a `.env` file.

## Prerequisites

Before you begin, ensure you have met the following requirements:

*   **Python:** Version 3.8 or higher recommended.
*   **Pip:** Python package installer.
*   **Git:** For cloning the repository.
*   **PostgreSQL Database:** Access to a running PostgreSQL instance (local or cloud-hosted like Render, Railway, ElephantSQL, etc.). You'll need the connection URL.
*   **Mastodon Account:** An account on a Mastodon instance.
*   **Mastodon Application Credentials:**
    *   You need to register an application on your Mastodon instance. Go to `Preferences -> Development -> New Application`.
    *   Give it a name (e.g., "DVP POST IO Scheduler").
    *   Set the **Redirect URI** to match the `REDIRECT_URI` you will configure in your `.env` file (e.g., `http://localhost:5000/callback` for local development, or your production callback URL).
    *   Ensure the necessary scopes are selected (e.g., `read`, `write:statuses`).
    *   Note down the **Client Key** (Client ID) and **Client Secret**.

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/PatelDevashish001/DVP_POST_IO.git
    cd DVP_POST_IO
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    # On Linux/macOS
    source venv/bin/activate
    # On Windows
    # venv\Scripts\activate
    ```

3.  **Create a `requirements.txt` file:**
   
    psycopg2-binary
    Mastodon.py
    python-dotenv
    Flask # Add Flask if you have a web interface
    # Add other dependencies like requests, gunicorn, etc. if used
    ```

4.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

Configuration is managed via environment variables loaded from a `.env` file in the project root.

1.  **Create a `.env` file:** Copy the example or create a new one:
    ```bash
    cp .env.example .env
    # Or create .env manually
    ```

2.  **Edit the `.env` file with your credentials:**
    ```dotenv
    # Mastodon Configuration
    MASTODON_BASE_URL=https://your-mastodon-instance.social # e.g., https://mastodon.social
    MASTODON_CLIENT_ID=YOUR_MASTODON_APP_CLIENT_ID
    MASTODON_CLIENT_SECRET=YOUR_MASTODON_APP_CLIENT_SECRET
    REDIRECT_URI=http://localhost:5000/callback # IMPORTANT: Must match Mastodon app settings and your deployment URL

    # Database Configuration (Use the full connection string from your provider)
    # Example format: postgresql://user:password@host:port/database
    DATABASE_URL=YOUR_POSTGRESQL_CONNECTION_URL

    # Flask Application Security (Change this to a long, random string!)
    SECRET_KEY=YOUR_VERY_SECRET_RANDOM_KEY_FOR_FLASK_SESSIONS
    ```

    *   **`MASTODON_BASE_URL`**: The base URL of your Mastodon instance.
    *   **`MASTODON_CLIENT_ID`**: Your Mastodon application's Client Key.
    *   **`MASTODON_CLIENT_SECRET`**: Your Mastodon application's Client Secret.
    *   **`REDIRECT_URI`**: The callback URL registered in your Mastodon app settings. This is where users are redirected after authentication. **Crucial:** This *must* match exactly what you entered when creating the Mastodon application. For production, update this to your live application's callback URL (e.g., `https://your-app-name.onrender.com/callback`).
    *   **`DATABASE_URL`**: The full connection string for your PostgreSQL database. Platforms like Render and Railway provide this automatically as an environment variable.
    *   **`SECRET_KEY`**: A secret key used by Flask for session management and security. Generate a strong, random key.

## Database Setup

1.  **Connect** to your PostgreSQL database using a tool like `psql`, DBeaver, pgAdmin, or your hosting provider's interface.
2.  **Create the necessary tables.** The scheduler script (`dvp_post_io_pg.py`) ensures certain *columns* exist (`processing_id`, `processing_started`) but does not create the initial tables. You need to create the `users` and `tweets` tables manually first.

    *(**TODO:** Provide the exact SQL `CREATE TABLE` statements here or link to a `schema.sql` file in your repository)*

    **Example `schema.sql` (Adapt types/constraints as needed):**
    ```sql
    -- Users table to store Mastodon ID and access token
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        mastodon_id VARCHAR(255) UNIQUE NOT NULL,
        username VARCHAR(255) NOT NULL,
        access_token VARCHAR(255) NOT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

    -- Tweets table to store scheduled posts
    CREATE TABLE IF NOT EXISTS tweets (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL, -- References users(mastodon_id)
        message TEXT NOT NULL,
        schedule_time TIMESTAMPTZ NOT NULL,
        status VARCHAR(50) DEFAULT 'pending' NOT NULL, -- pending, processing, posted, failed
        visibility VARCHAR(50) DEFAULT 'public' NOT NULL, -- public, unlisted, private, direct
        created_at TIMESTAMPTZ DEFAULT NOW(),
        posted_at TIMESTAMPTZ NULL,
        processing_id TEXT NULL,       -- Added by scheduler script if needed
        processing_started TIMESTAMPTZ NULL, -- Added by scheduler script if needed
        retry_count INTEGER DEFAULT 0,
        error_message TEXT NULL,
        FOREIGN KEY (user_id) REFERENCES users(mastodon_id) ON DELETE CASCADE -- Optional: link to users table
    );

    -- Optional: Add indexes for performance
    CREATE INDEX IF NOT EXISTS idx_tweets_status_schedule_time ON tweets (status, schedule_time);
    CREATE INDEX IF NOT EXISTS idx_users_mastodon_id ON users (mastodon_id);
    ```
    Execute this SQL against your database.

## Usage

The application consists of two main parts: the web interface (likely Flask) and the background scheduler.

1.  **Run the Web Application (Flask):**
    *(Assuming your main Flask app file is `app.py`)*
    ```bash
    # Make sure your virtual environment is active and .env is configured
    flask run
    ```
    Access the application in your browser (usually `http://localhost:5000`). Use this interface to authenticate with Mastodon and schedule your posts.

2.  **Run the Background Scheduler:**
    This script needs to run continuously to check for and send scheduled posts.
    ```bash
    # Make sure your virtual environment is active and .env is configured
    python dvp_post_io_pg.py
    ```
    The scheduler will log its activity to the console. For production, you should run this script persistently using tools like:
    *   `systemd` (recommended for Linux servers)
    *   `supervisor`
    *   `screen` or `tmux` (simpler, but less robust for unattended operation)
    *   Platform-specific background workers (e.g., Render Background Worker, Railway background process).

## Deployment (Example: Render/Railway)

1.  **Configure Environment Variables:** Set all the variables from your `.env` file in the platform's dashboard environment settings. **Do not** commit your `.env` file.
2.  **Database:** Create a PostgreSQL instance on the platform and use the provided `DATABASE_URL` environment variable. Run the `schema.sql` (or equivalent DDL commands) against the production database.
3.  **Services:** You typically need two services:
    *   **Web Service:**
        *   **Build Command:** `pip install -r requirements.txt`
        *   **Start Command:** `gunicorn app:app` (Replace `app:app` with `your_flask_file:your_flask_app_instance` if different. Install `gunicorn` via pip).
    *   **Background Worker:**
        *   **Build Command:** `pip install -r requirements.txt`
        *   **Start Command:** `python dvp_post_io_pg.py`
4.  **Redirect URI:** Ensure the `REDIRECT_URI` environment variable on the platform matches the callback URL registered in your Mastodon application settings *and* points to your live web service URL (e.g., `https://dvp-post-io.onrender.com/callback`).

## Important Notes

*   **File Locking (`fcntl`):** The file lock used by the scheduler (`scheduler.lock`) works reliably on standard Linux filesystems but might have issues on certain network file systems (like NFS).
*   **Error Handling:** Error handling is basic. Posts that fail multiple times will be marked 'failed' and require manual intervention.
*   **Database Schema:** Ensure your database schema is created *before* running the application or scheduler for the first time.

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues.

*(Add specific contribution guidelines if you have them)*
