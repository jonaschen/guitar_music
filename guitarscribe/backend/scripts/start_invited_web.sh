#!/usr/bin/env bash
# Recreate the single-host transient web unit after a stopped-service backup.
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
runtime_dir="${GUITARSCRIBE_RUNTIME_DIR:-$HOME/.cache/guitarscribe-runtime}"
if systemctl --user is-active --quiet guitarscribe-friends-web; then
  printf '%s\n' 'Invited web service is already running; no changes made.'
  exit 0
fi
systemd-run --user --unit=guitarscribe-friends-web \
  --property="WorkingDirectory=$project_dir/backend" --property=Restart=on-failure \
  --setenv="GUITARSCRIBE_WEB_ACCESS_FILE=$project_dir/output/web-preview/access.json" \
  --setenv="GUITARSCRIBE_WEB_STATIC_DIR=$project_dir/output/web-preview/site" \
  --setenv="GUITARSCRIBE_WORK_DIR=$project_dir/output/web-preview/work" \
  --setenv=GUITARSCRIBE_JOB_TTL_SECONDS=31536000 \
  --setenv=GUITARSCRIBE_BEAT_ENGINE=beat_this_small --setenv=GUITARSCRIBE_CHORD_ENGINE=chordino \
  --setenv=GUITARSCRIBE_MELODY_SEPARATOR=off --setenv=GUITARSCRIBE_BEAT_RECOVERY_ENABLED=true \
  --setenv=GUITARSCRIBE_YOUTUBE_ENABLED=true \
  --setenv="GUITARSCRIBE_SUBMISSION_RATE_LIMIT=${GUITARSCRIBE_SUBMISSION_RATE_LIMIT:-5}" \
  --setenv="GUITARSCRIBE_RHYTHM_PATTERNS_DIR=$project_dir/rhythm-patterns" \
  --setenv="GUITARSCRIBE_YOUTUBE_JS_RUNTIME=node:${GUITARSCRIBE_NODE_BINARY:-$HOME/.nvm/versions/node/v24.14.0/bin/node}" \
  --setenv="PYTHONPATH=$HOME/.cache/guitarscribe-beat-dbn/python:$HOME/.cache/guitarscribe-chordino-diagnostic/python" \
  --setenv="VAMP_PATH=$HOME/.cache/guitarscribe-chordino-diagnostic/source" --setenv=OMP_NUM_THREADS=2 \
  "$runtime_dir/bin/python" -m uvicorn app.web:create_app --factory --host 127.0.0.1 --port 5273
