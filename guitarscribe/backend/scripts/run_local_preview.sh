#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
runtime_dir="${GUITARSCRIBE_RUNTIME_DIR:-$HOME/.cache/guitarscribe-runtime}"
chordino_dir="${GUITARSCRIBE_CHORDINO_DIR:-$HOME/.cache/guitarscribe-chordino-diagnostic}"
export PYTHONPATH="$project_dir/backend:$chordino_dir/python${PYTHONPATH:+:$PYTHONPATH}"
export VAMP_PATH="$chordino_dir/source"
export OMP_NUM_THREADS=2
export GUITARSCRIBE_BEAT_ENGINE=beat_this_small
export GUITARSCRIBE_CHORD_ENGINE=chordino
export GUITARSCRIBE_MELODY_SEPARATOR=demucs
export GUITARSCRIBE_DEMUCS_BINARY="$runtime_dir/bin/demucs"
export GUITARSCRIBE_YOUTUBE_ENABLED=true
export GUITARSCRIBE_RHYTHM_PATTERNS_DIR="$project_dir/rhythm-patterns"
export GUITARSCRIBE_WORK_DIR="${GUITARSCRIBE_WORK_DIR:-$project_dir/output/work}"
# Retain local historical jobs and their source audio during preview development.
export GUITARSCRIBE_JOB_TTL_SECONDS=315360000
"$runtime_dir/bin/python" - <<'PY'
from app.core.config import Settings
from app.services.capabilities import analysis_capabilities
capabilities = analysis_capabilities(Settings.from_env())
if not capabilities['improved_accompaniment'] or not capabilities['melody_available']:
    raise SystemExit(f'Preview dependencies unavailable: {capabilities}')
print('Preview engines:', capabilities, flush=True)
PY
cd "$project_dir/backend"
exec "$runtime_dir/bin/python" -m uvicorn app.api:app --host 127.0.0.1 --port 8000
