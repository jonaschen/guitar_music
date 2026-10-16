#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
frontend_dir="$(cd -- "$script_dir/.." && pwd)"
repository_dir="$(cd -- "$frontend_dir/.." && pwd)"
cd "$frontend_dir"

record_dir="${TMPDIR:-/tmp}/guitarscribe-workflow-verification"
mkdir -p "$record_dir"
record_file="${GUITARSCRIBE_VERIFICATION_RECORD:-$record_dir/verification-$(date -u +%Y%m%dT%H%M%SZ).txt}"
output_file="$(mktemp "${TMPDIR:-/tmp}/guitarscribe-workflow-output.XXXXXX")"
trap 'rm -f "$output_file"' EXIT

mkdir -p "$(dirname -- "$record_file")"
{
  printf 'GuitarScribe workflow verification\n'
  printf 'Started: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'Directory: %s\n' "$frontend_dir"
  printf 'Git HEAD: %s\n' "$(git -C "$repository_dir" rev-parse HEAD)"
  if [[ -n "$(git -C "$repository_dir" status --porcelain)" ]]; then
    printf 'Git working tree dirty: yes\n'
  else
    printf 'Git working tree dirty: no\n'
  fi
  printf 'Recovery live test: %s\n' "$([[ -n "${GUITARSCRIBE_RECOVERY_REVISION:-}" ]] && printf enabled || printf disabled)"
} > "$record_file"

run_step() {
  local label="$1"
  shift
  printf '\n==> %s\n' "$label"
  if "$@" >"$output_file" 2>&1; then
    printf 'PASS %s\n' "$label" | tee -a "$record_file"
    if [[ "$label" == *Playwright* ]]; then
      local summary
      summary="$(grep -E '^[[:space:]]*[0-9]+ (passed|skipped|failed|flaky|did not run)' "$output_file" || true)"
      if [[ -n "$summary" ]]; then
        printf '%s\n' "$summary" | tee -a "$record_file"
      else
        printf 'Playwright summary unavailable in output\n' | tee -a "$record_file"
      fi
    fi
  else
    local status=$?
    {
      printf 'FAIL %s (exit %s)\n' "$label" "$status"
      printf '%s\n' 'Last output lines:'
      tail -n 30 "$output_file"
    } | tee -a "$record_file"
    printf '\nVerification failed; record: %s\n' "$record_file" >&2
    exit "$status"
  fi
}

run_step 'TypeScript check' npx --no-install tsc -b
run_step 'Vite production build' npx --no-install vite build
run_step 'Workflow Playwright regressions' npx --no-install playwright test \
  e2e/melody-editor.spec.ts \
  e2e/score-workspace.spec.ts \
  e2e/bar-timing.spec.ts \
  e2e/focused-workspace.spec.ts \
  --workers=1

if [[ -n "${GUITARSCRIBE_RECOVERY_REVISION:-}" ]]; then
  run_step 'Opt-in saved-revision Playwright live regression' npx --no-install playwright test \
    e2e/revision-recovery-live.spec.ts \
    --workers=1
fi

printf 'Finished: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$record_file"
printf '\nVerification passed; record: %s\n' "$record_file"
