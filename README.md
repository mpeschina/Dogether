# Dogether

Dogether is a Streamlit prototype for shared daily and weekly goals. Users sign in
with Google, add friends by email, approve friend requests, and create shared
goals where every participant has their own progress and target.

## Features

- Google-authenticated account view with name, email, and completion stats
- Main shared-goals view with participant progress numbers and progress bars
- Friend invitations by email with approval/decline on the Friends view
- Friends view with accepted friends plus incoming and outgoing pending invites
- Goal creation for accepted friends with daily/weekly schedule classes
- Per-user target/progress updates and leave-goal behavior
- JSON persistence with period history for account stats

## Run locally for development

### Prerequisites

- Python 3.9 or newer
- `pip`

### Setup

The project is in a dev container. Dependencies are installed via the
`devcontainer.json` file. Python dependencies are listed in `requirements.txt`.

Create `.streamlit/secrets.toml` with your local Google OIDC credentials and
JSON persistence settings:

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
```

Then start the Streamlit development server:

```bash
python -m streamlit run streamlit_app.py
```

Streamlit will print the local URL in the terminal, typically
`http://localhost:8501`. The app automatically reloads when source files are
saved.

To stop the server, press `Ctrl+C` in the terminal.

## App behavior

Pending and declined friend invites are stored inside the JSON persistence file.
Accepted invites are deleted after the friendship is created. No email is sent.
When the invited Google email signs in, the pending invite appears in the
Friends view.

Goals can be shared only with accepted friends. After a goal is created, the
shared description and schedule class are immutable. Each participant can update
only their own current progress and target, or leave the goal, which removes
them from the stored participant list. Goals with no remaining participants are
deleted.

Supported schedule classes are:

- `daily`: fulfilled when the daily progress reaches the target
- `weekly`: fulfilled when the weekly progress reaches the target
- `daily with X per week`: daily progress resets each day; weekly completion is
  based on summed daily progress reaching `X * target`
- `weekly with X per month`: weekly progress resets each Monday; monthly
  completion is based on summed weekly progress reaching `X * target`

Days start at midnight in `Europe/Berlin`, and weeks start on Monday. Completed
period history is stored for account stats; there is no per-goal history table
in this prototype.

## Tests

Run the pytest suite from the repository root:

```bash
./run_tests.sh
```

## Persistence

This prototype intentionally supports only JSON persistence. Local development
defaults to `data/users.json`, configured through `.streamlit/secrets.toml`:

```toml
[persistence]
backend = "json"
json_path = "data/users.json"
```

The JSON document contains users, friend invites, friendships, goals, and period
records. The file is written atomically with a temporary file replacement.

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
backend = "json"
json_path = "data/users.json"
```

Use the same production callback URL as an authorized redirect URI in the Google
Cloud OAuth client, then restart the Streamlit app.
