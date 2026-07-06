#!/usr/bin/env python3
import json
import os
import re
import shlex
import sys
from datetime import datetime, timezone
from pathlib import PurePath


HOME = os.path.expanduser("~")
DEFAULT_MODE_FILE = os.path.join(HOME, ".gemini", "config", "antigravity-safe-mode.json")
DEFAULT_LOG_FILE = os.path.join(HOME, ".gemini", "config", "antigravity-safe-hook.log")

READ_TOOLS = {
    "read_file",
    "view_file",
    "list_directory",
    "search_directory",
    "find_file",
}
WRITE_TOOLS = {
    "write_file",
    "replace_file_content",
    "multi_replace_file_content",
    "create_file",
    "edit_file",
}
PASSIVE_TOOLS = {"finish", "ask_question"}

SIMPLE_READ_ONLY_COMMANDS = {
    "basename",
    "date",
    "df",
    "dirname",
    "du",
    "file",
    "head",
    "id",
    "ls",
    "pwd",
    "tail",
    "uname",
    "wc",
    "which",
    "whoami",
}
SEARCH_COMMANDS = {"cat", "grep", "rg"}
VERSION_ONLY_COMMANDS = {"node", "npm", "pnpm", "python", "python3", "yarn"}
GIT_READ_ONLY_SUBCOMMANDS = {
    "blame",
    "branch",
    "describe",
    "diff",
    "grep",
    "log",
    "ls-files",
    "remote",
    "rev-parse",
    "show",
    "status",
}
AGY_READ_ONLY_SUBCOMMANDS = {"--help", "--version", "changelog", "help", "models"}

SHELL_META = re.compile(r"(\|\||&&|[|;<>`])|\$\(")
SECRET_ASSIGNMENT = re.compile(
    r"(?i)(token|secret|password|passwd|api[_-]?key|credential)=([^\\s]+)"
)


def emit(decision):
    print(json.dumps({"decision": decision}))


def load_mode():
    env_mode = os.environ.get("ANTIGRAVITY_SAFE_MODE")
    if env_mode:
        return normalize_mode(env_mode)

    mode_file = os.environ.get("ANTIGRAVITY_SAFE_MODE_FILE", DEFAULT_MODE_FILE)
    try:
        with open(mode_file, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return normalize_mode(str(payload.get("mode", "")))
    except Exception:
        return "ask"


def normalize_mode(mode):
    normalized = mode.strip().lower().replace("-", "_")
    if normalized in {"allow_all", "all", "turbo"}:
        return "allow_all"
    if normalized in {"whitelist", "white_list", "safe"}:
        return "whitelist"
    return "ask"


def get_arg(args, *names):
    for name in names:
        if name in args and args[name] is not None:
            return str(args[name])
    return ""


def path_from_args(args):
    return get_arg(
        args,
        "TargetFile",
        "target_file",
        "FilePath",
        "file_path",
        "path",
        "Path",
        "directory",
        "Directory",
        "target",
        "Target",
    )


def command_from_args(args):
    return get_arg(args, "CommandLine", "command", "cmd", "Command")


def path_parts(path):
    return [part.lower() for part in PurePath(path).parts if part not in {"", "/"}]


def is_sensitive_path(path):
    if not path:
        return False

    lowered = path.lower()
    parts = path_parts(lowered)
    basename = PurePath(lowered).name

    if basename.startswith(".env"):
        return True

    sensitive_basenames = {
        ".git-credentials",
        ".netrc",
        ".npmrc",
        ".pypirc",
        "google_accounts.json",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "id_rsa",
        "kubeconfig",
        "oauth_creds.json",
        "trustedfolders.json",
    }
    if basename in sensitive_basenames:
        return True

    if basename.endswith((".key", ".pem", ".p12", ".pfx")):
        return True

    if any(marker in basename for marker in ("credential", "password", "secret", "token")):
        return True

    sensitive_dirs = {".ssh", ".gnupg", ".aws", ".azure", ".kube"}
    if any(part in sensitive_dirs for part in parts):
        return True

    if ".config" in parts and "gcloud" in parts:
        return True

    return False


def command_mentions_sensitive_path(parts):
    return any(is_sensitive_path(part) for part in parts[1:])


def has_shell_meta(command):
    return bool(SHELL_META.search(command))


def parse_command(command):
    try:
        return shlex.split(command)
    except ValueError:
        return []


def command_basename(executable):
    return os.path.basename(executable)


def allow_git(parts):
    index = 1
    while index < len(parts):
        token = parts[index]
        if token == "-C" and index + 1 < len(parts):
            index += 2
            continue
        if token in {"--version", "-v"}:
            return True
        if token.startswith("-"):
            return False
        break

    if index >= len(parts):
        return False

    return parts[index] in GIT_READ_ONLY_SUBCOMMANDS


def allow_find(parts):
    denied = {"-delete", "-exec", "-execdir", "-ok", "-okdir"}
    return not any(part in denied for part in parts[1:])


def allow_sed(parts):
    if any(part == "-i" or part.startswith("-i") for part in parts[1:]):
        return False
    return "-n" in parts[1:]


def allow_version_only(parts):
    return len(parts) == 2 and parts[1] in {"--version", "-v", "-V", "version"}


def allow_agy(parts):
    if len(parts) == 2 and parts[1] in AGY_READ_ONLY_SUBCOMMANDS:
        return True
    if len(parts) == 3 and parts[1] in {"help"}:
        return True
    return False


def allow_command(command):
    command = command.strip()
    if not command or has_shell_meta(command):
        return False

    parts = parse_command(command)
    if not parts or command_mentions_sensitive_path(parts):
        return False

    base = command_basename(parts[0])

    if base in SIMPLE_READ_ONLY_COMMANDS:
        return True
    if base in SEARCH_COMMANDS:
        return True
    if base == "command" and len(parts) >= 3 and parts[1] == "-v":
        return True
    if base == "git":
        return allow_git(parts)
    if base == "find":
        return allow_find(parts)
    if base == "sed":
        return allow_sed(parts)
    if base in VERSION_ONLY_COMMANDS:
        return allow_version_only(parts)
    if base == "agy":
        return allow_agy(parts)

    return False


def whitelist_decision(tool_name, args):
    if tool_name in PASSIVE_TOOLS:
        return "allow", "passive_tool"

    if tool_name == "run_command":
        command = command_from_args(args)
        if allow_command(command):
            return "allow", "whitelisted_command"
        return "ask", "command_not_whitelisted"

    if tool_name in READ_TOOLS:
        target = path_from_args(args)
        if is_sensitive_path(target):
            return "ask", "sensitive_path"
        return "allow", "safe_read_tool"

    if tool_name in WRITE_TOOLS:
        return "ask", "write_tool"

    return "ask", "unknown_tool"


def sanitized_preview(value, limit=220):
    if not value:
        return ""
    redacted = SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=<redacted>", value)
    redacted = redacted.replace(HOME, "~")
    if len(redacted) > limit:
        return redacted[: limit - 3] + "..."
    return redacted


def log_decision(mode, decision, reason, tool_name, args):
    log_file = os.environ.get("ANTIGRAVITY_SAFE_LOG_FILE", DEFAULT_LOG_FILE)
    if not log_file:
        return

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "decision": decision,
        "reason": reason,
        "tool": tool_name,
    }

    command = command_from_args(args)
    target = path_from_args(args)
    if command:
        record["command"] = sanitized_preview(command)
    if target:
        record["target"] = sanitized_preview(target)

    try:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        with open(log_file, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")
    except Exception:
        pass


def decide(event_data):
    mode = load_mode()
    tool_call = event_data.get("toolCall", {})
    tool_name = str(tool_call.get("name", "")).strip()
    args = tool_call.get("args", {})
    if not isinstance(args, dict):
        args = {}

    if mode == "allow_all":
        decision, reason = "allow", "allow_all_mode"
    elif mode == "whitelist":
        decision, reason = whitelist_decision(tool_name, args)
    else:
        decision, reason = "ask", "ask_mode"

    log_decision(mode, decision, reason, tool_name, args)
    return decision


def main():
    try:
        input_data = sys.stdin.read()
        if not input_data:
            emit("ask")
            return

        event_data = json.loads(input_data)
        if not isinstance(event_data, dict):
            emit("ask")
            return

        emit(decide(event_data))
    except Exception:
        emit("ask")


if __name__ == "__main__":
    main()
