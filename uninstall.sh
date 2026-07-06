#!/usr/bin/env bash
set -euo pipefail

CONFIG_DIR="${GEMINI_CONFIG_DIR:-$HOME/.gemini/config}"
COMMAND_DIR="$CONFIG_DIR/plugins/custom-commands"
BIN_DIR="${ANTIGRAVITY_SAFE_BIN_DIR:-$HOME/.local/bin}"
HOOK_SCRIPT="$COMMAND_DIR/antigravity_safe_approve.py"
HOOKS_JSON="$CONFIG_DIR/hooks.json"

if [[ -f "$HOOKS_JSON" ]]; then
  python3 - "$HOOKS_JSON" "$HOOK_SCRIPT" <<'PY'
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

hooks_path = Path(sys.argv[1])
hook_script = Path(sys.argv[2])
command = f"python3 {hook_script}"

backup = hooks_path.with_name(
    f"{hooks_path.name}.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
)
shutil.copy2(hooks_path, backup)

with hooks_path.open("r", encoding="utf-8") as handle:
    data = json.load(handle)

hooks = data.get("hooks", {})
pre_tool_use = hooks.get("PreToolUse", [])
filtered = []
for entry in pre_tool_use:
    entry_hooks = [
        hook
        for hook in entry.get("hooks", [])
        if not (isinstance(hook, dict) and hook.get("command") == command)
    ]
    if entry_hooks:
        entry["hooks"] = entry_hooks
        filtered.append(entry)

if filtered:
    hooks["PreToolUse"] = filtered
else:
    hooks.pop("PreToolUse", None)

with hooks_path.open("w", encoding="utf-8") as handle:
    json.dump(data, handle, indent=2)
    handle.write("\n")
PY
fi

rm -f "$HOOK_SCRIPT" "$BIN_DIR/agy-safe" "$CONFIG_DIR/antigravity-safe-mode.json"

printf 'Uninstalled antigravity-safe-gate.\n'
