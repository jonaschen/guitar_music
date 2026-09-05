# GuitarScribe

Backend-first prototype for generating guitar-friendly song analysis from uploaded audio.

## Current API

- `GET /health`
- `POST /analyses`
  - multipart upload
  - fields: `audio_file`, `rights_confirmed`, `melody_mode`, `chord_complexity`
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
