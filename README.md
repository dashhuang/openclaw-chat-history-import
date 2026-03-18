# OpenClaw Chat History Import

An OpenClaw skill for importing external chat exports into:

- `logs/message-archive-raw/`
- `memory/YYYY-MM-DD.md`
- `MEMORY.md`

It is designed for interactive, review-first migration of chat history from sources such as Claude exports, ChatGPT exports, Slack-style transcripts, and other structured or semi-structured chat archives.

This skill is primarily about historical import.
It pairs especially well with:

- the `conversation-archive` plugin, which keeps future live chats flowing into the same raw archive tree
- the `conversation-history` skill, which lets agents search imported archive files after import

## What It Does

- inspects external export files
- normalizes messages into `conversation-archive`-compatible JSONL
- validates imported archive shape
- stages and applies model-authored daily memory merges
- stages and applies review-gated `MEMORY.md` merges

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

If you also want imported history to be searchable from normal OpenClaw conversations, install or keep a history-search companion skill such as `conversation-history`.

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
