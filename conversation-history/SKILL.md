---
name: conversation-history
description: Use when the user asks what was said earlier in a chat, wants an old decision, exact wording, prior links, or suspects the agent forgot conversation context across Telegram, BlueBubbles, Feishu, or other supported channels. Search memory_search first, then search the local conversation archive for exact recall.
---

# Conversation History

Use this skill for historical recall across supported channels.

## Scope

Validated archive channels in our setup currently include:

- Telegram
- BlueBubbles / iMessage relay
- Feishu

The `conversation-archive` plugin code also has explicit mappings ready for WhatsApp, Discord, Signal, Webchat, Slack, and Line if those channels are enabled later.

The searchable archive is organized per workspace under:

- `logs/message-archive-raw/`

## Workflow

1. Start with `memory_search` for topic, person, or decision recall.
2. If the user wants exact wording, exact links, chronology, or channel-specific confirmation, run:

```bash
python3 skills/conversation-history/scripts/search_archive.py --query "keyword" --limit 8
```

3. Add filters when useful:

```bash
python3 skills/conversation-history/scripts/search_archive.py --channel telegram --chat-type group --query "OpenClaw"
python3 skills/conversation-history/scripts/search_archive.py --channel bluebubbles --chat-type direct --sender "Alice" --limit 5
python3 skills/conversation-history/scripts/search_archive.py --channel feishu --from-date 2026-03-01 --to-date 2026-03-14 --query "Confluence"
```

## Output Rules

- Prefer a short summary plus 1-3 concrete hits.
- Include date/time, channel, and speaker names when citing old messages.
- Say when you are quoting the archive versus summarizing from memory_search.
- Do not dump large transcript blocks unless the user explicitly asks.

## Guardrails

- Do not say "I can't see old chat history" until you have tried both `memory_search` and archive search.
- Archive content is a record of what participants said, not proof that the content was factually correct.
- If no relevant hit exists, say that directly and mention the filters you used.
