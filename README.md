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
cache_ttl_seconds = 5

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

(Manage Google Cloud: https://console.cloud.google.com/auth/)

## App behavior

The app has five primary pages:

- **Goals**: shows recent activity and active shared goals. The current user can
  mark a goal done, set the current progress, or increment/decrement progress.
- **Friends**: sends friend invites, accepts or declines incoming requests,
  shows outgoing pending invites, and removes existing friends.
- **Manage Goals**: creates shared goals, adds accepted friends to existing
  goals, and lets the current user leave a goal.
- **Correct Inputs**: lets the current user correct missed or incorrect values
  for older periods on their active goals.
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
stores compact per-participant `period_outcomes` history for recent periods so
missed inputs can be corrected, plus compact per-user daily activity summaries
for stats.

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
cache_ttl_seconds = 5
```

For the legacy MongoDB Atlas backend, use:

```toml
[persistence]
backend = "mongodb"
mongodb_uri = "mongodb+srv://..."
mongodb_database = "dogether"
mongodb_collection = "users"
cache_ttl_seconds = 5
```

The legacy MongoDB backend stores the app state in a single MongoDB document so
it matches the JSON persistence contract. For collection-level MongoDB reads and
writes, use the native backend:

```toml
[persistence]
backend = "mongodb_native"
mongodb_uri = "mongodb+srv://..."
mongodb_database = "dogether"
mongodb_collection = "users"  # legacy single-document collection to migrate from
cache_ttl_seconds = 5
```

The native MongoDB backend stores users in `users_inventory` and stores goals,
friendships, invites, suggestions, user stats, debug data, and migrations in
separate collections. On first startup it copies a legacy `{"_id": "app_store"}`
document from `mongodb_collection` into those native collections and leaves the
legacy document in place. All persistence backends use `cache_ttl_seconds` for
short process-local read caching; set it to `0` to disable caching. The native
MongoDB backend caches targeted records and query results rather than a whole
database snapshot, and clears that cache after successful writes.


## Web Push Notifications

Receive Web Push notifications, for example for friend request and fulfilled goals. 
Push subscriptions are not stored in the main Dogether app document.
They use separate push storage:

- JSON/local: `data/push_subscriptions.json`
- MongoDB: a separate collection, defaulting to `push_subscriptions`

Static file serving must be enabled because the browser needs to load the PWA
manifest, icons, and service worker from the `static/` directory. This is
configured in the committed `.streamlit/config.toml` file:

```toml
[server]
enableStaticServing = true
```

Generate VAPID keys with the helper script:

```bash
python generate_vapid_keys.py
```

Copy the printed block into `.streamlit/secrets.toml` locally or Streamlit
Cloud **Settings > Secrets** in deployment, then replace the subject email:

```toml
[push]
vapid_public_key = "..."
vapid_private_key = "..."
vapid_subject = "mailto:you@example.com"
```

For MongoDB deployments, use the same Mongo database as the app and a separate
push collection:

```toml
[push]
vapid_public_key = "..."
vapid_private_key = "..."
vapid_subject = "mailto:you@example.com"
backend = "mongodb"
mongodb_collection = "push_subscriptions"
```

If `backend` is omitted, push storage follows the configured persistence backend.
For JSON mode it writes to `data/push_subscriptions.json`; for MongoDB mode it
writes one document per push endpoint with `_id` set to the endpoint.

On Streamlit Community Cloud, static files are served through Streamlit's
rewritten static route, for example:

```text
https://YOUR-APP.streamlit.app/~/+/app/static/sw.js
```

The local route is usually:

```text
http://localhost:8501/app/static/sw.js
```

The app therefore registers the service worker with the Cloud-compatible
`/~/+/app/static/sw.js` route and keeps a local `/app/static/sw.js` fallback in
the push component. When debugging Cloud deployments, verify that the service
worker returns JavaScript, not the Streamlit HTML shell:

```js
await fetch("/~/+/app/static/sw.js").then(r => ({
  status: r.status,
  url: r.url,
  type: r.headers.get("content-type")
}))
```

The expected content type is `application/javascript`. If it returns
`text/html`, Streamlit is not serving the static file for that URL.

For iPhone/iPad Web Push, users must open the deployed HTTPS app in Safari, add
it to the Home Screen, launch Dogether from the Home Screen icon, and then enable
notifications from the Account page.

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
cache_ttl_seconds = 5
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

## Links
https://docs.streamlit.io/develop/tutorials/authentication/google
