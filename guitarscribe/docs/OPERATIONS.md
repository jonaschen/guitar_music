# GuitarScribe operations guide

GuitarScribe is designed for a single trusted host running Docker Compose. The
analysis worker is intentionally limited to one concurrent job by default;
long audio and optional vocal separation can use substantial CPU, RAM, and
disk.

## Start and check

```bash
cp .env.example .env
make build
docker compose up -d backend frontend
docker compose ps
curl --fail http://localhost:8000/health
```

The web app is served on port 5173 and the API on port 8000. Run
`docker compose logs -f backend` to follow a job through its stages. A failed
or cancelled job exposes its message through `GET /api/v1/jobs/{job_id}`.

## Persistent data and backup

The Compose configuration maps `./output` into the backend. It contains the
SQLite job metadata, SQLite score/revision database, and short-lived job
artifacts under `output/work/`. Do not use `make clean` on a host whose
revisions you need to retain.

For a consistent simple backup, stop the backend before copying the directory:

```bash
docker compose stop backend
tar -C . -czf guitarscribe-output-$(date +%F).tar.gz output
docker compose start backend
```

Keep backups access-controlled: saved revisions can contain user-provided
lyrics and analysis metadata. To restore, stop the backend, replace only the
intended `output/` directory from a known backup, then start it again. Never
restore untrusted SQLite files onto a production host.

## Resource and retention controls

Set these in `.env` and rebuild/restart the backend after changing build-time
options:

| Setting | Default | Purpose |
|---|---:|---|
| `GUITARSCRIBE_MAX_DURATION_SECONDS` | `600` | Reject audio beyond this duration. |
| `GUITARSCRIBE_MAX_UPLOAD_BYTES` | 100 MiB | Reject oversized upload bodies. |
| `GUITARSCRIBE_MAX_CONCURRENT_JOBS` | `1` | Maximum simultaneous analyses on this host. |
| `GUITARSCRIBE_MAX_QUEUED_JOBS` | `3` | Maximum waiting analyses; later submissions receive HTTP 503. |
| `GUITARSCRIBE_SUBMISSION_RATE_LIMIT` | `5` | Per-client submissions during the window; set `0` only for trusted development. |
| `GUITARSCRIBE_SUBMISSION_RATE_WINDOW_SECONDS` | `3600` | Rate-limit window. |
| `GUITARSCRIBE_MELODY_SEPARATOR` | `off` | Enable `demucs` only after building its optional dependency. |
| `GUITARSCRIBE_YOUTUBE_ENABLED` | `false` | Enable the restricted, rights-confirmed YouTube resolver. |

Completed-job artifacts are cleaned according to the backend job TTL. The API
does not accept downloader cookies, credentials, playlists, or arbitrary
download arguments.

## Updates and verification

Before updating a host, create an `output/` backup, pull the desired commit,
then rebuild and run the checks:

```bash
git pull --ff-only
docker compose build
docker compose run --rm -v "$PWD/backend:/app" backend pytest -q
cd frontend && npm ci && npm run build && npx playwright test --workers=1
```

The repository CI performs the backend test suite and frontend build/E2E on
push and pull request. The optional `guitarscribe evaluate` command is useful
for quality-gate thresholds on legal golden fixtures; it is not a guarantee of
accurate transcription for arbitrary music.

## Exposure and security boundaries

The included CORS policy permits only local development origins. If exposing
the app beyond localhost, place it behind an authenticated TLS reverse proxy,
keep ports 5173/8000 private where practical, set an appropriate CORS allow
list in a deployment-specific build, and use a shared rate limiter for
multiple backend workers. Do not treat the in-memory submission limiter as a
distributed production control.
