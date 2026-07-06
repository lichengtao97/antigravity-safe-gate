# Antigravity Safe Gate

A local approval gate for Google Antigravity / Gemini Agent hooks.

This project was inspired by [`puti001/antigravity-automation`](https://github.com/puti001/antigravity-automation), but it takes a safer default posture:

- `ask`: manually confirm every tool call.
- `whitelist`: auto-approve only low-risk read-only commands and non-sensitive reads.
- `allow-all`: auto-approve every tool call for the current session.

It installs a `PreToolUse` hook and an `agy-safe` launcher. The launcher lets you choose an approval mode before starting Antigravity CLI, passes that mode through a session-specific mode file, then resets back to `ask` when the session exits.

## Why

The original automation idea is useful because repeated confirmations slow down local agent workflows. The risky part is defaulting to broad auto-approval. This version keeps the speed path, but makes the default behavior fail closed and exposes the risky mode explicitly.

## Install

```bash
git clone https://github.com/lichengtao97/antigravity-safe-gate.git
cd antigravity-safe-gate
./install.sh
```

The installer:

- copies `scripts/antigravity_safe_approve.py` to `~/.gemini/config/plugins/custom-commands/`
- copies `scripts/agy-safe` to `~/.local/bin/`
- adds a `PreToolUse` hook to `~/.gemini/config/hooks.json`
- backs up an existing `hooks.json` before editing it

## Usage

```bash
agy-safe
```

Choose one mode for the session:

```text
1) whitelist  Auto-approve read-only low-risk commands and safe reads
2) allow-all   Auto-approve every tool call for this session
3) ask         Manually confirm every tool call
```

Press Enter at the prompt to accept the default `whitelist` mode.

You can also choose a mode non-interactively:

```bash
AGY_SAFE_MODE=whitelist agy-safe
AGY_SAFE_MODE=allow-all agy-safe
AGY_SAFE_MODE=ask agy-safe
```

## Whitelist Behavior

Whitelist mode auto-approves low-risk commands such as:

- `pwd`, `ls`, `date`, `whoami`, `uname`, `wc`
- `rg`, `grep`, `cat`, `head`, `tail`
- `sed -n ...`
- read-only Git commands: `git status`, `git diff`, `git log`, `git show`, `git grep`
- `agy --version`, `agy --help`, `agy models`

Whitelist mode asks for confirmation for:

- writes, edits, and file creation
- shell metacharacters such as pipes, redirects, command substitution, and chained commands
- installers and mutating commands such as `npm install`, `curl ... | bash`, `rm`, and `python -c`
- sensitive paths such as `.env`, `.ssh`, `.aws`, `.kube`, `.npmrc`, `.git-credentials`, private keys, token files, and `~/.gemini/oauth_creds.json`

## Allow-All Warning

`allow-all` means the hook returns `{"decision": "allow"}` for every tool call in that session, and `agy-safe` starts `agy` with `--dangerously-skip-permissions` so Antigravity's native permission prompts are skipped too. It does not grant root privileges, but it does remove the Antigravity/Gemini confirmation gate for anything the current user account can do.

Use it only for fully trusted local tasks.

## Test

```bash
python3 tests/test_antigravity_safe_approve.py
bash -n scripts/agy-safe install.sh uninstall.sh
python3 -m py_compile scripts/antigravity_safe_approve.py tests/test_antigravity_safe_approve.py
```

## Uninstall

```bash
./uninstall.sh
```

The uninstaller removes the installed hook script and launcher, removes this hook entry from `hooks.json`, and backs up `hooks.json` before editing it.
