#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

FAKE_AGY="$TMP_DIR/agy"
MODE_FILE="$TMP_DIR/mode.json"

cat > "$FAKE_AGY" <<'SH'
#!/usr/bin/env bash
printf 'fake-agy:%s\n' "$*"
printf 'mode-env:%s\n' "${ANTIGRAVITY_SAFE_MODE_FILE:-}"
if [[ -n "${ANTIGRAVITY_SAFE_MODE_FILE:-}" && -f "$ANTIGRAVITY_SAFE_MODE_FILE" ]]; then
  printf 'mode-content:'
  cat "$ANTIGRAVITY_SAFE_MODE_FILE"
fi
SH
chmod +x "$FAKE_AGY"

AGY_SAFE_MODE=allow-all \
  AGY_BIN="$FAKE_AGY" \
  HOME="$TMP_DIR/home" \
  "$ROOT_DIR/scripts/agy-safe" --version > "$TMP_DIR/session.out" 2> "$TMP_DIR/session.err"

grep -q 'mode-env:' "$TMP_DIR/session.out"
if grep -q 'mode-env:$' "$TMP_DIR/session.out"; then
  echo 'session mode file was not exported to agy child process' >&2
  exit 1
fi
grep -q 'mode-content:{"mode":"allow_all"' "$TMP_DIR/session.out"

AGY_SAFE_MODE=allow-all \
  AGY_BIN="$FAKE_AGY" \
  ANTIGRAVITY_SAFE_MODE_FILE="$MODE_FILE" \
  "$ROOT_DIR/scripts/agy-safe" --version > "$TMP_DIR/noninteractive.out" 2> "$TMP_DIR/noninteractive.err"

grep -q 'fake-agy:--dangerously-skip-permissions --version' "$TMP_DIR/noninteractive.out"
grep -q 'Antigravity approval mode: allow_all' "$TMP_DIR/noninteractive.err"
grep -q '"mode":"ask"' "$MODE_FILE"

AGY_SAFE_MODE=whitelist \
  AGY_BIN="$FAKE_AGY" \
  ANTIGRAVITY_SAFE_MODE_FILE="$MODE_FILE" \
  "$ROOT_DIR/scripts/agy-safe" --version > "$TMP_DIR/whitelist.out" 2> "$TMP_DIR/whitelist.err"

grep -q 'fake-agy:--version' "$TMP_DIR/whitelist.out"
if grep -q -- '--dangerously-skip-permissions' "$TMP_DIR/whitelist.out"; then
  echo 'whitelist mode should not skip native permissions' >&2
  exit 1
fi

printf '\n' | script -q /dev/null \
  env AGY_BIN="$FAKE_AGY" \
    ANTIGRAVITY_SAFE_MODE_FILE="$MODE_FILE" \
    "$ROOT_DIR/scripts/agy-safe" > "$TMP_DIR/default.pty" 2>&1

grep -q 'fake-agy:' "$TMP_DIR/default.pty"
grep -q 'Choose Antigravity approval mode for this session:' "$TMP_DIR/default.pty"
grep -q 'Antigravity approval mode: whitelist' "$TMP_DIR/default.pty"
if grep -q 'Antigravity approval mode: Choose Antigravity' "$TMP_DIR/default.pty"; then
  echo 'interactive menu was captured as the mode value' >&2
  exit 1
fi
