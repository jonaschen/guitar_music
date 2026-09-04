# GuitarScribe

貼上歌曲連結，取得與原曲同步的和弦、小節、節奏建議及簡化主旋律，並能人工修正及匯出。

## Current Status

**Milestone 0 — Tech Spike**
No web UI yet, just a Docker-based CLI that processes local audio files.

## Prerequisites

- Docker
- Docker Compose

## Quick Start

```bash
make build
make test
make analyze FILE=/app/fixtures/audio/test_progression.wav
```

## Usage

The CLI can be used via Docker Compose (make targets). To analyze a file, use the `make analyze` command and pass the path to the audio file as `FILE`:

```bash
make analyze FILE=/path/to/your/audio.wav
```
Outputs are saved to `/app/output/result.json` within the container, which maps to `./output/result.json` on the host.

## Architecture Overview

The system features:
- Core signal processing pipeline using Librosa and Vamp plugins
- CLI interface using Click
- Data modeling with Pydantic
- Modular analyzer engines for Beats, Chords, and Melody

## Chord Engine Status

The app uses the Chordino (nnls-chroma) Vamp plugin by default. If Chordino is not available or fails to download during the Docker build, the system automatically falls back to a basic chromagram-based chord extraction algorithm.

## Known Limitations for M0

- CLI interface only, no GUI
- Supports local audio files only, no URL fetching
- Melody extraction is basic
- Rhythm patterns are manually defined stubs

## License

TBD
