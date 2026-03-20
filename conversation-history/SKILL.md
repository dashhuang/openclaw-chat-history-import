---
name: conversation-history
description: Use when the user asks what was said earlier in a chat, wants an old decision, exact wording, prior links, or suspects the agent forgot conversation context across Telegram, BlueBubbles, Feishu, ChatGPT, Claude, or other archived chat sources. Search memory_search first, then search the local conversation archive for exact recall.
---

# Conversation History

Use this skill for historical recall across many kinds of chat history, not just live messaging channels.

## Scope

This skill works by searching the local raw archive tree:

- `logs/message-archive-raw/`

That means it can search any chat history that has already been normalized into that archive format.

Typical sources include:

- Telegram
- BlueBubbles / iMessage relay
- Feishu
- ChatGPT exports imported through `chat-history-import`
- Claude exports imported through `chat-history-import`
- other archive-compatible chat logs

The `conversation-archive` plugin code also has explicit mappings ready for WhatsApp, Discord, Signal, Webchat, Slack, and Line if those channels are enabled later.

So this skill should be thought of as a general archive search skill, not just a Telegram / Feishu recall helper.

If the archive data exists in `logs/message-archive-raw/`, this skill can search it.

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
python3 skills/conversation-history/scripts/search_archive.py --channel chatgpt --query "memory export"
python3 skills/conversation-history/scripts/search_archive.py --channel claude --query "project plan"
python3 skills/conversation-history/scripts/search_archive.py --query "shareholder letter" --limit 5
```

Use channel filters when the source is known.
If the user only cares about content recall and not the original source, broad keyword search is often enough.

## Output Rules

- Prefer a short summary plus 1-3 concrete hits.
- Include date/time, channel, and speaker names when citing old messages.
- Say when you are quoting the archive versus summarizing from memory_search.
- Do not dump large transcript blocks unless the user explicitly asks.

## Guardrails

- Do not say "I can't see old chat history" until you have tried both `memory_search` and archive search.
- Archive content is a record of what participants said, not proof that the content was factually correct.
- If no relevant hit exists, say that directly and mention the filters you used.

## Companion Components

This skill becomes much more useful when paired with archive-producing tools.

- For live ongoing archive capture, pair it with:
  - `openclaw-conversation-archive`
  - https://github.com/dashhuang/openclaw-conversation-archive
- For importing old AI chat exports such as ChatGPT and Claude, pair it with:
  - `openclaw-chat-history-import`
  - https://github.com/dashhuang/openclaw-chat-history-import

Without one of those archive-producing workflows, this skill can only search whatever archive files already exist locally.
