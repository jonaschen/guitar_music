# GuitarScribe

Backend-first prototype for generating guitar-friendly song analysis from uploaded audio.

## Current API

- `GET /health`
- `POST /analyses`
  - multipart upload
  - fields: `audio_file`, `rights_confirmed`, `melody_mode`, `separate_vocals`, `chord_complexity`
- `POST /scores/playback/manifest`
  - compiles immutable guitar, melody, and metronome events with a content revision hash
- `POST /scores/transpose`
  - JSON body with a full `SongScore`, target semitone delta, accidental preference, and optional capo

## Run

```bash
make build
make serve-stack
```

The frontend will listen on `http://localhost:5173`.
The API will listen on `http://localhost:8000`.

## Notes

- Browser access from `http://localhost:5173` to `http://localhost:8000` is enabled via CORS in the backend API.
- The current UI intentionally supports local audio upload only. It does not implement YouTube download.

## Optional vocal isolation

Full-mix melody extraction can follow accompaniment instead of the singer. Vocal focus can optionally run Demucs before Basic Pitch without adding PyTorch to the normal backend image. In a dedicated Python 3.10-3.12 environment, install CPU PyTorch first, then the optional dependency:

```bash
python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
python -m pip install -e './backend[separation]'
```

For Docker Compose, set `GUITARSCRIBE_INSTALL_SEPARATION=true` and `GUITARSCRIBE_MELODY_SEPARATOR=demucs` in `.env`, then run `docker compose build backend` and `docker compose up -d backend`. In the web app, choose **Vocal** focus and enable **Vocal isolation** for the individual analysis. For a host installation, set `GUITARSCRIBE_MELODY_SEPARATOR=demucs` and, if `demucs` is not on `PATH`, set `GUITARSCRIBE_DEMUCS_BINARY` to its executable. The first analysis may download model weights. If isolation fails, analysis safely falls back to the original mix and reports the reason in Analysis notes. Guitar and Mix focus currently keep the original audio.
