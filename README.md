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


Create `.streamlit/secrets.toml` with your local Google OIDC credentials, then
start the Streamlit development server:

```bash
python -m streamlit run streamlit_app.py
```

Streamlit will print the local URL in the terminal, typically
`http://localhost:8501`. The app automatically reloads when source files are
saved.

To stop the server, press `Ctrl+C` in the terminal.

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
```

Use the same production callback URL as an authorized redirect URI in the
Google Cloud OAuth client, then restart the Streamlit app.
