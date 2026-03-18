# Chat History Import Schema

This reference defines the output contract for imported raw chat history.

## Destination

Imported raw chat history must be written under:

```text
logs/message-archive-raw/<channel>/<chat_type>/<conversation_slug>/<YYYY-MM-DD>.jsonl
```

This matches the `conversation-archive` plugin directory layout.

## Compatibility Goal

Imported JSONL must be compatible with:

- `extensions/conversation-archive/index.js`
- `extensions/conversation-archive/scripts/check_archive.py`
- `extensions/conversation-archive/scripts/search_archive.py`
- `skills/conversation-history/scripts/search_archive.py`

## Required Fields

Every archive entry must contain:

- `timestamp_utc`
- `timestamp_local`
- `local_date`
- `local_time`
- `channel`
- `chat_type`
- `role`
- `text`

These are the minimum fields enforced by the archive health check.

## Recommended Full Entry Shape

Use this full object shape when possible:

```json
{
  "source": "import",
  "timestamp_utc": "2026-03-18T05:35:19.000Z",
  "timestamp_local": "2026-03-18T18:35:19+13:00",
  "local_date": "2026-03-18",
  "local_time": "18:35:19",
  "workspace": "/Users/dash/.openclaw/workspace",
  "agent_id": "main",
  "channel": "claude",
  "chat_type": "direct",
  "peer_id": "claude:account:example-account",
  "conversation_label": "Example conversation",
  "conversation_slug": "example-conversation",
  "message_id": "example-message-id",
  "role": "user",
  "speaker_name": "Example User",
  "speaker_id": "example-user-id",
  "text": "message text",
  "source_provider": "claude",
  "source_type": "account-export",
  "source_archive": "claude-export.zip",
  "source_conversation_id": "example-conversation-id",
  "source_message_id": "example-source-message-id",
  "import_run_id": "20260318-example-import",
  "imported_at": "2026-03-18T18:35:19+13:00"
}
```

## Field Rules

### `channel`

Use the true source channel when known:

- `slack`
- `discord`
- `whatsapp`
- `telegram`

For assistant-platform exports that do not map to a real chat channel, use:

- `claude`
- `chatgpt`

### `chat_type`

Allowed values:

- `direct`
- `group`
- `channel`

### `role`

Allowed values:

- `user`
- `assistant`

Do not emit tool-only records as standalone archive entries unless they are converted into user-visible text.

### `text`

- must contain user-visible text only
- normalize newlines to `\n`
- trim trailing whitespace
- avoid embedding raw tool payloads into main message text

### `conversation_slug`

- lowercase slug
- filesystem safe
- stable within the import run

## Import-Specific Metadata

The following extra fields are encouraged and do not break compatibility:

- `source_provider`
- `source_type`
- `source_archive`
- `source_conversation_id`
- `source_message_id`
- `import_run_id`
- `imported_at`

## Dedupe Expectations

Imported messages should dedupe cleanly using the same fields the search scripts rely on:

- `channel`
- `chat_type`
- `peer_id`
- `role`
- `message_id` or timestamp fallback
- `text`

If the source does not provide message IDs, generate a stable synthetic ID from source conversation ID, timestamp, role, and ordinal position.

## Memory Merge Rules

### Daily Memory (`memory/YYYY-MM-DD.md`)

- merge into the existing date file instead of creating a separate imported file
- keep the body close to normal OpenClaw memory style
- use concise Chinese bullets
- use only a short HTML comment for provenance
- daily memory content must be model-authored, not heuristic-only script output

### `MEMORY.md` (默认记忆)

- always review before apply
- provenance should stay lightweight
- prefer merging into an existing `##` section when the model can identify one
- if no suitable section exists, create a short new section name instead of a verbose imported appendix

## Validation

Use:

```bash
python3 skills/chat-history-import/scripts/validate_archive.py logs/message-archive-raw
```

The validator must pass before claiming compatibility.

## Bundled Script Roles

- `scripts/inspect_import.py`
  Detects likely source format and reports archive structure.
- `scripts/archive_contract.py`
  Provides the canonical helper functions for compatible archive entries and paths.
- `scripts/normalize_import.py`
  Converts supported sources into `conversation-archive` compatible JSONL.
- `scripts/memory_merge.py`
  Writes review artifacts and applies model-authored daily or `MEMORY.md` payloads.
- `scripts/validate_archive.py`
  Enforces archive path and field compatibility.
- `scripts/build_review_checklist.py`
  Builds a date-by-date review checklist for Plan Mode daily-memory review, with counts and optional Markdown/JSON outputs.
