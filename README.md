# Dogether

Dogether is a Streamlit prototype for shared daily and weekly goals. Users sign in
with Google, add friends by email, approve friend requests, and create shared goals.


## Features

- Google-authenticated account view with name, email, and completion stats
- Main shared-goals view with participant progress numbers and progress bars
- Friend invitations by email with approval/decline on the Friends view
- Friends view with accepted friends plus incoming and outgoing pending invites
- Goal creation for accepted friends with daily/weekly schedule classes
- Per-user target/progress updates and leave-goal behavior
- JSON persistence with compact streak and activity stats

## Run locally for development

### Prerequisites

- Python 3.9 or newer
- `pip`

### Setup

The project is in a dev container. Dependencies are installed via the
`devcontainer.json` file. Python dependencies are listed in `requirements.txt`.

Create `.streamlit/secrets.toml` with JSON persistence settings. Add Google OIDC
credentials when you want to use the real login flow:

```toml
[auth]
redirect_uri = "http://localhost:8501/oauth2callback"
cookie_secret = "A-LONG-RANDOM-SECRET"
client_id = "YOUR-GOOGLE-CLIENT-ID"
client_secret = "YOUR-GOOGLE-CLIENT-SECRET"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"

[persistence]
backend = "json"
json_path = "data/users.json"

[debug]
view = true
```

When `[debug].view = true`, the app shows a Debug page and a local debug login
so you can create or select test users without Google sign-in. Set it to `false`
or omit the section for normal Google-authenticated use.

Then start the Streamlit development server:

```bash
python -m streamlit run streamlit_app.py
```

Streamlit will print the local URL in the terminal, typically
`http://localhost:8501`. The app automatically reloads when source files are
saved.

To stop the server, press `Ctrl+C` in the terminal.

## App behavior

The app has four primary pages:

- **Goals**: shows recent activity and active shared goals. The current user can
  mark a goal done, set the current progress, or increment/decrement progress.
- **Friends**: sends friend invites, accepts or declines incoming requests,
  shows outgoing pending invites, and removes existing friends.
- **Manage Goals**: creates shared goals, adds accepted friends to existing
  goals, and lets the current user leave a goal.
- **Account**: shows profile details, goal/friend stats, completion rate, and a
  year of activity.


Supported schedule classes are:

- `daily`: fulfilled when the daily progress reaches the target
- `weekly`: fulfilled when the weekly progress reaches the target
- `daily with X per week`: daily progress resets each day; weekly completion is
  based on summed daily progress reaching `X * target`
- `weekly with X per month`: weekly progress resets each Monday; monthly
  completion is based on summed weekly progress reaching `X * target`

Days start at midnight in `Europe/Berlin`, and weeks start on Monday. The app
does not store per-period completion history; it keeps current per-goal streaks
and compact per-user daily activity summaries for stats.

## Tests

Run the pytest suite from the repository root:

```bash
./run_tests.sh
```

## Persistence

The app supports JSON persistence for local development and a document-backed
MongoDB persistence backend for Atlas deployments. Local development defaults to
`data/users.json`, configured through `.streamlit/secrets.toml`:

```toml
[persistence]
backend = "json"
json_path = "data/users.json"
```

For MongoDB Atlas, use:

```toml
[persistence]
backend = "mongodb"
mongodb_uri = "mongodb+srv://..."
mongodb_database = "dogether"
mongodb_collection = "users"
```

Both backends persist the same app store shape: users, friend invites,
friendships, goals, compact user stats, and debug settings. The JSON backend
writes the file atomically; the MongoDB backend stores the app state in a single
MongoDB document for now so it matches the existing persistence contract.

## Debug Time Travel

Set `[debug].view = true` in `.streamlit/secrets.toml` to show the Debug page
and local debug login. The Debug page can add one hour or one day to the app's
effective time. That offset is persisted by the configured backend and is
applied to goal period rollover and completion calculations only while the debug
view is enabled.

## Deploy on Streamlit Community Cloud

The local `.streamlit/secrets.toml` file is intentionally excluded from Git. In
the app's **Settings > Secrets**, add:

```toml
[auth]
redirect_uri = "https://YOUR-APP.streamlit.app/oauth2callback"
cookie_secret = "A-LONG-RANDOM-SECRET"
client_id = "YOUR-GOOGLE-CLIENT-ID"
client_secret = "YOUR-GOOGLE-CLIENT-SECRET"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"

[persistence]
backend = "mongodb"
mongodb_uri = "mongodb+srv://..."
mongodb_database = "dogether"
mongodb_collection = "users"
```

Use the same production callback URL as an authorized redirect URI in the Google
Cloud OAuth client, then restart the Streamlit app.

Please Note: 

If MongoDB Atlas reports an SSL handshake error from Streamlit Cloud, first
verify the app's Streamlit secrets contain the full `mongodb+srv://...` URI.
Then check Atlas **Network Access**: Atlas only accepts clients whose source IP
is in the project's IP access list, and Streamlit Community Cloud outbound IPs
can change. For a prototype, add `0.0.0.0/0` in Atlas Network Access; for a
production app, use a host with stable outbound networking or a private network
path.

Streamlits Cloud IPs are listed here: 
https://docs.streamlit.io/deploy/streamlit-community-cloud/status
35.230.127.150
35.203.151.101
34.19.100.134
34.83.176.217
35.230.58.211
35.203.187.165
35.185.209.55
34.127.88.74
34.127.0.121
35.230.78.192
35.247.110.67
35.197.92.111
34.168.247.159
35.230.56.30
34.127.33.101
35.227.190.87
35.199.156.97
34.82.135.155
