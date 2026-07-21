# YouTube Live List

A tiny self-hosted FastAPI page that lists live, upcoming, and recent completed
YouTube broadcasts owned by your account. It uses read-only OAuth access, so it
can find unlisted broadcasts that do not appear on your public channel page.

## Google setup

1. Create a project in the [Google Cloud Console](https://console.cloud.google.com/).
2. Enable the **YouTube Data API v3**.
3. Configure the Google Auth Platform audience. For a personal Google account,
   add yourself as a test user while setting up, then choose an appropriate
   production audience for long-running use. External apps left in **Testing**
   have authorizations (including refresh tokens) that expire after seven days.
4. Create an OAuth client with application type **Desktop app** and download its
   client JSON file.
5. Install the project and authorize your YouTube account locally:

   ```console
   uv sync
   uv run python -m yt_live_list.auth \
       --client-secrets ./client_secret.json \
       --token ./data/youtube-token.json
   ```

   A browser opens for Google consent. The command requests only the
   `youtube.readonly` scope. If the service will run on another machine, securely
   copy the generated token file there. Never commit either credential file.

## Run

Set the token path and start the FastAPI application factory:

```console
export YTLL_TOKEN_FILE="$PWD/data/youtube-token.json"
uv run uvicorn yt_live_list.app:create_app --factory --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000/>. `GET /healthz` provides a lightweight liveness
check that does not contact YouTube.

The optional `YTLL_CACHE_TTL_SECONDS` setting defaults to `60`. Results are
cached only in memory; after an upstream failure, the last successful result is
shown with a warning until YouTube becomes available again.

The page includes a stable social preview image rather than allowing link-preview
crawlers to choose one of the broadcast thumbnails. When the app is served below
a reverse-proxy subpath, set `YTLL_PUBLIC_BASE_URL` to its public base URL, such as
`https://example.com/yt-live-list`, so the Open Graph image has the correct
absolute URL.

The application intentionally has no viewer authentication. An obscure hostname
reduces accidental discovery but is not access control: anyone who learns the
page URL can see and share its unlisted YouTube links. Put authentication in a
reverse proxy if that assumption changes.

## Development

```console
uv run pytest
```

The app targets Python 3.14 and uses server-rendered HTML with no frontend build
step or persistent database.
