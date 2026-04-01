# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A bridge between Claude Code and Feishu (飞书/Lark) that sends interactive card notifications to Feishu when Claude Code needs permission approval or user input. Users respond via Feishu buttons or text replies, and the decision is relayed back to Claude Code.

## Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Start the webhook server
python3 src/server/webhook_server.py

# Test hooks
./scripts/test_hook.sh
```

There is no formal test suite or linter configured.

## Architecture

### Data Flow

1. **Claude Code triggers a hook** (PermissionRequest or PreToolUse) → Hook script reads JSON from stdin
2. **Hook sends Feishu card** via Feishu OpenAPI → User sees interactive notification on phone
3. **Hook polls storage** (blocking loop) waiting for status change
4. **User responds** in Feishu (button click or text reply) → Feishu sends webhook callback
5. **Webhook server processes callback** → Updates JSON storage with the decision/answer
6. **Hook detects status change** → Returns decision to Claude Code via stdout

### Key Components

- **`src/hooks/permission_request.py`** — PermissionRequest hook. For other tools (Bash, Write, etc.), sends Feishu permission card with allow/deny buttons and blocks until user responds. For AskUserQuestion, sends Feishu interactive card, blocks for answer, writes answer to `data/last_answer.json`, returns allow.
- **`src/hooks/ask_user_question.py`** — PreToolUse hook for AskUserQuestion. Returns `{}` immediately (its presence enables the terminal selection box to show alongside the Feishu card).
- **`src/server/webhook_server.py`** — FastAPI server handling Feishu callbacks. Processes card button clicks and text messages. Supports AES-encrypted payloads from Feishu.
- **`src/storage.py`** — JSON-file-based state store with file locking (`fcntl`). Contains `PermissionStorage` for request data. Both hooks and webhook server share the same storage.
- **`src/feishu/client.py`** — Feishu OpenAPI client. Uses `curl` subprocess (not `requests`) for HTTP calls to avoid DNS issues in certain environments. Manages tenant access token with auto-refresh.
- **`src/feishu/cards.py`** — Card builder for Feishu interactive message cards. Constructs JSON card payloads for permission requests, question forms, and result displays.

### AskUserQuestion Handling

Both terminal and Feishu show simultaneously. PermissionRequest hook sends a Feishu interactive card and blocks for the answer. The terminal selection box also appears. Users can answer from either channel:

- **At computer**: answer in terminal → Claude gets answer directly
- **Away from computer**: answer on Feishu → answer written to `data/last_answer.json`

**IMPORTANT**: When AskUserQuestion tool returns an empty result, read `data/last_answer.json` to get the user's Feishu answer.

### Hook Input/Output Protocol

Hooks receive JSON via **stdin** and return JSON via **stdout**:
- PermissionRequest: outputs `{"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": {"behavior": "allow|deny", "message": "..."}}}`
- PreToolUse (AskUserQuestion): outputs `{"toolInput": {...modified questions with answers...}}`

### Configuration

- **`config/config.yaml`** — Main config (Feishu credentials, webhook port, storage path, timeouts). Excluded from git via `.gitignore`. Copy from `config/config.yaml.example`.
- **`.claude/settings.local.json`** — Claude Code hook registration. Defines which hooks fire on which events and their timeouts.

### Storage Concurrency

`PermissionStorage` uses `threading.Lock` for in-process safety and `fcntl.flock` + atomic temp-file rename for cross-process safety (hooks and webhook server are separate processes sharing the same JSON file).
