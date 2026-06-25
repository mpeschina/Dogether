# Dogether

A small Streamlit app testing Google Login. 

## Run locally for development

### Prerequisites

- Python 3.9 or newer
- `pip`

### Setup

The project is in a dev container. 
Dependencies are installed via the devcontainer.json file.
Python deps are in requirements.txt


Create `.streamlit/secrets.toml` with your local Google OIDC credentials and
persistence settings:

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

## Tests

Install the requirements and run the pytest suite from the repository root:

```bash
./run_tests.sh
```

## Persistence

The app stores a counter and text value per authenticated user, keyed by the
stable OpenID Connect `sub` claim from `st.user`.

Local development defaults to `data/users.json`. Configure persistence in
`.streamlit/secrets.toml`:

```toml
[persistence]
backend = "json"
json_path = "data/users.json"
```

To use MongoDB Atlas, switch the same configuration to:

```toml
[persistence]
backend = "mongodb"
mongodb_uri = "mongodb+srv://USERNAME:PASSWORD@CLUSTER.mongodb.net/"
mongodb_database = "dogether"
mongodb_collection = "users"
```

## Deploy on Streamlit Community Cloud

The local `.streamlit/secrets.toml` file is intentionally excluded from Git.
In the app's **Settings > Secrets**, add:

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

Use the same production callback URL as an authorized redirect URI in the
Google Cloud OAuth client, then restart the Streamlit app.
