# GuitarScribe

GuitarScribe is an automated audio analysis and transcription tool designed to help guitarists quickly generate an editable, synced chord chart and simplified melody from a YouTube link or uploaded audio file.

The core goal is not to perfectly transcribe every single note of the original recording, but to provide a functional, editable draft that users can easily practice and sing along with.

## Core Features

- **Audio Analysis**: Extract BPM, time signature, key, and measure boundaries.
- **Chord Recognition**: Automatically detect chords, snap them to the beat grid, and merge low-confidence sections.
- **Rhythm & Melody**: Suggest strumming patterns and extract a simplified lead melody (vocal or guitar).
- **Key & Transposition**: Full-song transposition (+/- semitones), smart Capo recommendations, and alternative chord voicings based on playability and fingering constraints.
- **Lyrics & Syncing**: Import lyrics (Text/LRC), line-by-line manual timing sync, and interactive karaoke-style highlighting.
- **Playback & Practice**:
  - Sync with the original YouTube/audio source.
  - Synthesized score playback with adjustable tempo, A-B looping, metronome, and multi-track mixing.
- **Export Formats**: JSON, ChordPro, LRC, and MIDI (with PDF and MusicXML planned for the future).

## Project Documentation

For detailed product requirements, architecture, and development handoff instructions, please refer to the following documents:

1. [`GuitarScribe_Web_UI_AI_Handoff.md`](./GuitarScribe_Web_UI_AI_Handoff.md) - Main product vision, AI handoff instructions, and core architecture.
2. [`GuitarScribe_UI_Key_and_Chord_Voicings_Addendum.md`](./GuitarScribe_UI_Key_and_Chord_Voicings_Addendum.md) - Detailed specifications for transposition, Capo advisor, and alternative chord voicings.
3. [`GuitarScribe_Lyrics_and_Score_Playback_Addendum.md`](./GuitarScribe_Lyrics_and_Score_Playback_Addendum.md) - Detailed specifications for lyrics syncing and synthesized score playback.

## Tech Stack

- **Frontend**: React, TypeScript, Vite, Tailwind CSS
- **Backend**: Python 3.10, FastAPI, Pydantic, SQLite, FFmpeg
- **Analysis Models**: Chordino (or modern alternatives) for chords, Basic Pitch for melody.
- **Deployment**: Docker and Docker Compose for a reproducible environment.

## Current Status

The project is currently at **Milestone 0: Tech Spike**. The immediate goal is to prove that the core analysis pipeline (BPM, beats, chords, melody) can run reliably inside a fixed Docker environment using a local audio file, without requiring manual plugin installations by the end user. Web UI and advanced syncing features will follow in subsequent milestones.

## Development Setup

*Instructions for setting up the Docker environment and running the basic analysis pipeline will be added here as Milestone 0 is completed.*
