#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${GEMINI_CONFIG_DIR:-$HOME/.gemini/config}"
COMMAND_DIR="$CONFIG_DIR/plugins/custom-commands"
BIN_DIR="${ANTIGRAVITY_SAFE_BIN_DIR:-$HOME/.local/bin}"
HOOK_SCRIPT="$COMMAND_DIR/antigravity_safe_approve.py"
HOOKS_JSON="$CONFIG_DIR/hooks.json"

mkdir -p "$COMMAND_DIR" "$BIN_DIR"

install -m 0755 "$ROOT_DIR/scripts/antigravity_safe_approve.py" "$HOOK_SCRIPT"
install -m 0755 "$ROOT_DIR/scripts/agy-safe" "$BIN_DIR/agy-safe"

python3 - "$HOOKS_JSON" "$HOOK_SCRIPT" <<'PY'
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

hooks_path = Path(sys.argv[1])
hook_script = Path(sys.argv[2])
command = f"python3 {hook_script}"

if hooks_path.exists() and hooks_path.stat().st_size:
    backup = hooks_path.with_name(
        f"{hooks_path.name}.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
    )
    shutil.copy2(hooks_path, backup)
    with hooks_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
else:
    data = {}

hooks = data.setdefault("hooks", {})
pre_tool_use = hooks.setdefault("PreToolUse", [])

pre_tool_use[:] = [
    entry
    for entry in pre_tool_use
    if command
    not in [
        hook.get("command", "")
        for hook in entry.get("hooks", [])
        if isinstance(hook, dict)
    ]
]

pre_tool_use.append(
    {
        "matcher": ".*",
        "hooks": [
            {
                "type": "command",
                "command": command,
            }
        ],
    }
)

hooks_path.parent.mkdir(parents=True, exist_ok=True)
with hooks_path.open("w", encoding="utf-8") as handle:
    json.dump(data, handle, indent=2)
    handle.write("\n")
PY

printf 'Installed antigravity-safe-gate.\n'
printf 'Run: agy-safe\n'
printf 'Hook: %s\n' "$HOOK_SCRIPT"
printf 'Config: %s\n' "$HOOKS_JSON"
