# OpenClaw Chat History Import

An OpenClaw skill bundle centered on importing external chat exports into:

- `logs/message-archive-raw/`
- `memory/YYYY-MM-DD.md`
- `MEMORY.md`

It is designed for interactive, review-first migration of chat history from sources such as Claude exports, ChatGPT exports, Slack-style transcripts, and other structured or semi-structured chat archives.

This repository now contains two companion skills:

- root `chat-history-import/`
  - imports and reviews external history
- `conversation-history/`
  - searches imported archive files later

They pair especially well with our `conversation-archive` plugin, which keeps future live chats flowing into the same raw archive tree.

## What It Does

- inspects external export files
- normalizes messages into `conversation-archive`-compatible JSONL
- validates imported archive shape
- stages and applies model-authored daily memory merges
- stages and applies review-gated `MEMORY.md` merges

## Included Skills

### `chat-history-import`

The main import workflow.

Use it to:

- inspect export files
- normalize raw history into `logs/message-archive-raw/`
- distill daily memory
- stage `MEMORY.md` candidates for review

### `conversation-history`

The companion retrieval workflow.

Use it after import when an agent needs to:

- search old decisions
- find exact wording
- retrieve old links
- confirm chronology from raw archive files

## Recommended Companion Components

### `conversation-archive` plugin

Recommended, but not required.

Use it when you want imported history and future live chat history to live under the same archive layout:

- imported history from this skill goes into `logs/message-archive-raw/`
- future live messages from the plugin also go into `logs/message-archive-raw/`

That makes one consistent archive tree instead of a one-off import silo.

### `conversation-history` skill

Strongly recommended.

This import skill writes archive files, but it does not replace search and recall workflows by itself.
If you want an OpenClaw agent to answer questions like “what did we decide last month?” or “find the old link from Telegram,” you should also install a history-search skill such as `conversation-history`.

In practice:

- `chat-history-import` writes history
- `conversation-history` searches history
- `conversation-archive` keeps new history flowing in

## Requirements

- OpenClaw
- `python3`

## Install

### Install `chat-history-import`

Copy the repository root into:

```text
<workspace>/skills/chat-history-import
```

### Install `conversation-history`

Copy the companion skill directory into:

```text
<workspace>/skills/conversation-history
```

### Shared on one machine

For shared install, copy:

```text
~/.openclaw/skills/chat-history-import
~/.openclaw/skills/conversation-history
```

Then start a new OpenClaw session or run:

```bash
openclaw skills info chat-history-import
openclaw skills info conversation-history
```

## Duplicate Install Notes

If OpenClaw already provides `conversation-history` from a plugin or shared skills directory, avoid installing a second copy into the same scope.

Practical rule:

- one `conversation-history` per scope is best
- workspace-local copies typically override shared copies
- if both exist, check `openclaw skills info conversation-history` to see which source is active

## Publish To ClawHub

For the import skill at repo root:

```bash
clawhub publish . \
  --slug chat-history-import \
  --name "Chat History Import" \
  --version 0.1.0 \
  --tags latest \
  --changelog "Initial public release."
```

For the companion retrieval skill:

```bash
clawhub publish ./conversation-history \
  --slug conversation-history \
  --name "Conversation History" \
  --version 0.1.0 \
  --tags latest \
  --changelog "Initial public release."
```

## Validate Locally

```bash
python3 -m py_compile scripts/*.py
python3 -m py_compile conversation-history/scripts/*.py
openclaw skills info chat-history-import
```

## Repository Layout

- `SKILL.md`
  OpenClaw skill entrypoint and workflow instructions.
- `conversation-history/`
  Companion archive retrieval skill.
- `references/`
  Archive schema and memory distillation prompt templates.
- `scripts/`
  Deterministic helpers for inspect, normalize, validate, and merge.

## License

MIT
