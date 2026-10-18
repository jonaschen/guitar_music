# Workflow verification

Run the repeatable frontend engineering checks from the frontend directory:

```sh
cd guitarscribe/frontend
./scripts/verify-workflow.sh
```

The script runs the TypeScript project check, a production Vite build, then the
single-worker Playwright regressions for melody editing, score workspace
playback/source comparison, bar timing, the focused workspace workflow, and
offline melody articulation/continuity audio rendering, plus explicit revision
links and their reload/race protections. Real-time solo playback checks cover
three loop passes without display frames, pause/resume retaining the full loop,
and cancellation preventing later scheduling. These audio checks verify
timing and signal behavior, not musical transcription correctness.
All `npx` calls use `--no-install`, so the script does not fetch missing tools.
Playwright starts the configured local Vite server as needed. Any failed step
exits nonzero and records its last output lines.

The saved-revision live regression is omitted unless
`GUITARSCRIBE_RECOVERY_REVISION` is explicitly set to a non-empty saved revision
ID. That test also uses `GUITARSCRIBE_API_URL` and `GUITARSCRIBE_UI_URL` when
provided; otherwise it targets the existing defaults (`127.0.0.1:8000` and
`127.0.0.1:5173`). It reads the revision before and after the isolated browser
workflow and verifies it remains unchanged. The same opt-in run also captures
the actual editor synthesis path through OfflineAudioContext, checks saved G
pitches/onsets/phrase endings after a deep-link reload, and emits `editor.wav`
in the Playwright test output for matched-level listening.

Each run writes a short text record with the Git HEAD, a dirty/clean working
tree flag, and each Playwright run's passed/skipped summary under
`${TMPDIR:-/tmp}/guitarscribe-workflow-verification/`. Set
`GUITARSCRIBE_VERIFICATION_RECORD` to choose a different record path. Captured
command output is temporary and removed when the script exits. The dirty flag
does not include or print filenames.
