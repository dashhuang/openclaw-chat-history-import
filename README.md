# OpenClaw Chat History Import

An OpenClaw skill for importing external chat exports into:

- `logs/message-archive-raw/`
- `memory/YYYY-MM-DD.md`
- `MEMORY.md`

It is designed for interactive, review-first migration of chat history from sources such as Claude exports, ChatGPT exports, Slack-style transcripts, and other structured or semi-structured chat archives.

## What It Does

- inspects external export files
- normalizes messages into `conversation-archive`-compatible JSONL
- validates imported archive shape
- stages and applies model-authored daily memory merges
- stages and applies review-gated `MEMORY.md` merges

## Requirements

- OpenClaw
- `python3`

## Install

### Workspace-local

Copy this repository into:

```text
<workspace>/skills/chat-history-import
```

### Shared on one machine

Copy this repository into:

```text
~/.openclaw/skills/chat-history-import
```

Then start a new OpenClaw session or run:

```bash
openclaw skills info chat-history-import
```

## Publish To ClawHub

From the repository root:

```bash
clawhub publish . \
  --slug chat-history-import \
  --name "Chat History Import" \
  --version 0.1.0 \
  --tags latest \
  --changelog "Initial public release."
```

## Validate Locally

```bash
python3 -m py_compile scripts/*.py
openclaw skills info chat-history-import
```

## Repository Layout

- `SKILL.md`
  OpenClaw skill entrypoint and workflow instructions.
- `references/`
  Archive schema and memory distillation prompt templates.
- `scripts/`
  Deterministic helpers for inspect, normalize, validate, and merge.

## License

MIT
