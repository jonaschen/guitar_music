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

For persistent-data layout, backup/restore, resource controls, update checks,
and safe network exposure, see [the operations guide](docs/OPERATIONS.md).

## Notes

- Browser access from `http://localhost:5173` to `http://localhost:8000` is enabled via CORS in the backend API.
- The UI supports local audio upload and, when explicitly enabled, a single HTTPS `youtube.com` or `youtu.be` video URL. You must confirm that you own, control, or are permitted to analyze the source. Playlist URLs are handled as one video only; no account credentials, browser cookies, or bypass options are accepted.

## Optional YouTube-to-WAV import

The resolver uses `yt-dlp` with FFmpeg to extract one WAV into the temporary job directory, then sends it through the same duration, size, analysis, cancellation, and TTL cleanup path as an upload. It is disabled by default. To enable it in Docker Compose:

```bash
# .env
GUITARSCRIBE_INSTALL_YOUTUBE=true
GUITARSCRIBE_YOUTUBE_ENABLED=true
docker compose up -d --build backend frontend
```

The result's source WAV is available only through its completed job and is removed with that job's TTL cleanup. The resolver accepts only HTTPS YouTube hosts and invokes `yt-dlp` without a shell or user-supplied command options.

## Analysis submission limit

To protect the single-worker analysis service, job creation is limited per direct client address. The default is five submissions per hour; set `GUITARSCRIBE_SUBMISSION_RATE_LIMIT=0` only for a trusted development environment that needs to disable this in-memory guard. A production multi-worker deployment should replace it with a shared reverse-proxy or Redis-backed limiter.

## Optional vocal isolation

Full-mix melody extraction can follow accompaniment instead of the singer. Vocal focus can optionally run Demucs, then trace the isolated vocal's single fundamental-frequency line with pYIN; Basic Pitch remains a fallback if that trace cannot be produced. This does not add PyTorch to the normal backend image. In a dedicated Python 3.10-3.12 environment, install CPU PyTorch first, then the optional dependency:

```bash
python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
python -m pip install -e './backend[separation]'
```

For Docker Compose, set `GUITARSCRIBE_INSTALL_SEPARATION=true` and `GUITARSCRIBE_MELODY_SEPARATOR=demucs` in `.env`, then run `docker compose build backend` and `docker compose up -d backend`. In the web app, choose **Vocal** focus and enable **Vocal isolation** for the individual analysis. For a host installation, set `GUITARSCRIBE_MELODY_SEPARATOR=demucs` and, if `demucs` is not on `PATH`, set `GUITARSCRIBE_DEMUCS_BINARY` to its executable. The first analysis may download model weights. If isolation fails, analysis safely falls back to the original mix and reports the reason in Analysis notes. Guitar and Mix focus currently keep the original audio.

## Golden-fixture evaluation

The legal synthetic fixture in `fixtures/` can be used to make quality changes measurable. Given an exported SongScore JSON, run:

```bash
docker compose run --rm -v "$PWD/backend:/app" -v "$PWD:/workspace:ro" backend \
  python -m app.cli evaluate /workspace/output/result.json \
    /workspace/fixtures/annotations/test_progression.json
```

For CI, add only the thresholds that are meaningful for a fixture. A failing
threshold prints the metrics and exits non-zero:

```bash
docker compose run --rm -v "$PWD/backend:/app" -v "$PWD:/workspace:ro" backend \
  python -m app.cli evaluate /workspace/output/result.json \
    /workspace/fixtures/annotations/test_progression.json \
    --max-bpm-relative-error 0.05 --min-beat-f-measure 0.8 --min-chord-symbol-recall 0.7
```

The legacy command reports relative BPM error, beat F-measure, chord-symbol
recall, and onset/pitch melody accuracy. For the recovery quality gates, use
the layered report instead; it never combines timing, chord, and melody into a
single score, and can render six reference/estimated audition tracks:

```bash
docker compose run --rm -v "$PWD/backend:/app" -v "$PWD:/workspace" backend \
  python -m app.cli quality-report /workspace/output/result.json \
    /workspace/fixtures/annotations/test_progression.json \
    --output /workspace/output/quality-report.json \
    --sonification-dir /workspace/output/quality-audio
```

Once score files are named by each annotation's `recording_id`, compare two
runs as an immutable bundle. The destination must not already exist:

```bash
docker compose run --rm -v "$PWD/backend:/app" -v "$PWD:/workspace" backend \
  python -m app.cli quality-batch /workspace/fixtures/annotations \
    /workspace/output/baseline /workspace/output/candidate \
    /workspace/output/comparison-2026-09-15 \
    --baseline-commit BASELINE_SHA --candidate-commit CANDIDATE_SHA
```

The bundle records source hashes, canonical score hashes, analyzer provenance,
per-layer deltas, and paired WAV files. These tools are intended for regression
comparison, not as a claim of full-song transcription accuracy.

To compare three or more chord-decoder configurations, place each complete run
in a named subdirectory (for example `runs/default/*.json` and
`runs/conservative/*.json`). Every score filename must match an annotation's
`recording_id`. The calibration command retains all non-dominated settings
instead of inventing a combined quality score:

```bash
docker compose run --rm -v "$PWD/backend:/app" -v "$PWD:/workspace" backend \
  python -m app.cli chord-calibration /workspace/quality/annotations \
    /workspace/output/runs /workspace/output/chord-calibration.json
```

The report compares duration-weighted maj/min accuracy, boundary F-measure,
distance from the ideal fragmentation ratio, and Review-event load. It also
enforces the 1.25 fragmentation gate and records decoder parameters from each
score's provenance. The Pareto frontier narrows the candidates; paired
sonification and human accompaniment audition remain required before choosing
a default.

`fixtures/quality/annotations/synthetic-easy-01.json` is a short, legally safe
smoke annotation for checking this plumbing against
`fixtures/audio/test_progression.wav`. It is intentionally not counted as one
of the required 30–60 second Easy listening excerpts.

Generate a comparison run without changing source code by overriding the
documented `GUITARSCRIBE_CHORD_*` values from `.env.example`. For example, a
more conservative segmentation run can use:

```bash
docker compose run --rm \
  -e GUITARSCRIBE_CHORD_ENGINE=chromagram \
  -e GUITARSCRIBE_CHORD_CHANGE_THRESHOLD=0.18 \
  -e GUITARSCRIBE_CHORD_BASE_CHANGE_PENALTY=0.06 \
  -v "$PWD/backend:/app" -v "$PWD:/workspace" backend \
  python -m app.cli analyze /workspace/quality/audio/easy-01.wav \
    --output /workspace/output/runs/conservative/easy-01.json
```
