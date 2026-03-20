---
name: chat-history-import
description: Use when the user wants to import external chat exports into OpenClaw. This skill normalizes raw chat history into conversation-archive-compatible JSONL, then guides the model to distill daily memory and `MEMORY.md` candidates before applying merges with user confirmation.
metadata: { "openclaw": { "emoji": "🗂️", "homepage": "https://github.com/dashhuang/openclaw-chat-history-import", "requires": { "bins": ["python3"] } } }
---

# Chat History Import

Use this skill when a user wants to import chat history from Claude, ChatGPT, Slack exports, markdown logs, JSON/JSONL transcripts, or similar archives into an OpenClaw workspace.

The most common source formats for this skill are ChatGPT exports and Claude exports.
If the user has not exported data yet, suggest the usual official export entry points first:

- ChatGPT: `Settings -> Data Controls -> Export`
- Claude: `Settings -> Privacy -> Export data`

These exports usually arrive as ZIP files and are good candidates for the built-in import flow.

## What This Skill Owns

- raw archive import into `logs/message-archive-raw/`
- daily memory distillation into `memory/YYYY-MM-DD.md`
- `MEMORY.md` candidate generation
- review and apply workflow for memory merges

## Related OpenClaw Components

This skill is not a replacement for the live archive plugin or archive search skill.

- `conversation-archive` plugin
  - Recommended when the workspace wants future live chats written into the same `logs/message-archive-raw/` tree.
  - This skill should emit archive files that are fully compatible with that plugin's raw archive layout.
- `conversation-history` skill
  - Strongly recommended when the user wants agents to search imported history after import.
  - This import skill writes archive files; it does not replace archive recall/search workflows on its own.

Preferred combined setup:

1. use `chat-history-import` to backfill old history
2. use `conversation-archive` to keep new history flowing in
3. use `conversation-history` to search both imported and live archive data

## What Scripts Do vs. What The Model Does

Scripts handle deterministic work:

- inspect the source archive
- normalize messages into the archive schema
- validate archive compatibility
- write review artifacts
- apply approved memory merges

Validation must be reported in two layers when relevant:

- `import-batch validation`: whether the files written by this import are valid
- `full-archive validation`: whether the entire existing archive tree is valid

If full-archive validation fails because of pre-existing files outside this import batch, do not describe the new import itself as failed. Report the historical archive issue separately.

The model handles semantic work:

- decide what each day is worth remembering
- rewrite imported history into the style of existing OpenClaw daily memory
- decide what belongs in `MEMORY.md`
- compare imported `MEMORY.md` candidates against existing `MEMORY.md`

Do not try to replace this semantic step with Python heuristics.

Also do not assume the bundled Python parsers can recognize every source format.
For unknown input formats, the model may need to inspect the source and write a temporary format-specific parser.

## Core Rules

1. Do not import external history into `agents/<agentId>/sessions/`.
2. Treat `logs/message-archive-raw/` as the canonical destination for imported raw chat history.
3. Imported archive output must pass `{baseDir}/scripts/validate_archive.py` and stay compatible with the `conversation-archive` plugin's archive contract.
4. Daily memory should merge into the existing `memory/YYYY-MM-DD.md` file for that date.
5. Daily memory body should look like normal OpenClaw memory: concise Chinese bullets, minimal metadata, no “Claude 备份里显示” phrasing.
6. Use a short HTML comment only to mark import provenance.
7. `MEMORY.md` is the default memory file here and is always review-required before apply.

## Large Export Handling

If the user says they already uploaded an archive, but the current chat channel only exposes a placeholder or incomplete file payload, treat that as a transport limitation first.

For large ChatGPT or similar exports, guide the user toward a smaller text-focused package before retrying upload:

1. unzip the export locally
2. keep the conversation JSON files first
3. keep optional small metadata files only when useful
4. remove bulky attachments such as images, audio, video, PDFs, Office files, and other binary artifacts
5. re-zip the reduced package and retry import

For ChatGPT-style exports, the most important files are usually:

- `conversations.json`
- `conversations-*.json`
- optional: `group_chats.json`
- optional: `export_manifest.json`

If the reduced archive still cannot be uploaded through the chat channel, ask for one of these instead:

- a direct download URL
- a host-local file path
- a cloud storage link that can be fetched from the host

Use a temp path or another host-local staging path for large imports rather than polluting `workspace/`.

## Import Workflow

### 1. Inspect

Start by inspecting the source:

```bash
python3 {baseDir}/scripts/inspect_import.py /path/to/archive-or-file
```

Use local file structure first. Use web research only as fallback for unclear formats.

When helpful, check whether the current workspace already has `conversation-archive` and `conversation-history` available, so the user can be told what will happen after import:

- archive-only import
- import plus future live archive
- import plus searchable archive recall

### 2. Normalize Raw Archive

Normalize the source into the archive schema described in `{baseDir}/references/schema.md`:

```bash
python3 {baseDir}/scripts/normalize_import.py /path/to/archive --archive-root logs/message-archive-raw --workspace workspace --agent-id main --apply
python3 {baseDir}/scripts/validate_archive.py logs/message-archive-raw
```

After validation, explicitly separate these outcomes:

1. whether the newly written files from this import batch are valid
2. whether the pre-existing archive tree is fully valid

If validation errors point to old archive files unrelated to the current import, report that clearly as a historical archive issue rather than an import-batch failure.

## Unknown Format Handling

When the bundled parser does not recognize the input format, use this fallback sequence:

1. Inspect the source files directly.
2. Determine whether the structure is simple enough to map by hand.
3. If not, write a temporary Python parser under a temp directory.
4. Make that parser output the canonical archive JSONL shape from `{baseDir}/references/schema.md`.
5. Run `{baseDir}/scripts/validate_archive.py` on the result before claiming success.

Preferred order:

1. bundled parser
2. model-assisted direct mapping
3. model-authored temporary parser

Guardrails for temporary parsers:

- only transform source data into canonical archive JSONL
- do not write directly into `MEMORY.md`
- do not bypass the archive validator
- keep source-specific logic isolated; do not pollute the skill with one-off code unless the format is worth supporting permanently

If a bundled parser is missing for a format that seems broadly reusable, mention that it may be worth promoting the temporary parser into a maintained parser later.

### 3. Distill Daily Memory

This step is model-driven.

Before writing any daily memory, switch into Plan Mode (or an equivalent explicit checklist workflow) and review the import one date at a time.

Use the helper script to build the review checklist whenever possible:

```bash
python3 {baseDir}/scripts/build_review_checklist.py logs/message-archive-raw \
  --source-archive <archive-name> \
  --source-provider <provider> \
  --md-out tmp/chat-import-review-checklist.md \
  --json-out tmp/chat-import-review-checklist.json
```

This helper gives you a date-by-date checklist with entry counts so the Plan Mode review can be explicit and auditable.

Required review process:

1. list every imported `YYYY-MM-DD.jsonl` date file first
2. create a checklist covering all imported dates
3. read each date fully before deciding what to write
4. do not infer from titles, conversation names, or sampling alone
5. do not apply `MEMORY.md` standards when deciding daily memory
6. only claim daily-memory completion after every imported date has been marked reviewed
7. when a date already has a local daily memory file, still check for missing imported bullets before deciding no change is needed

Before writing any memory, first read the local memory rules from the current OpenClaw environment.

Read in this order when available:

1. local `openclaw.json`
   - focus on `agents.defaults.compaction.memoryFlush.prompt`
   - focus on `agents.defaults.compaction.memoryFlush.systemPrompt`
2. workspace `AGENTS.md`
   - look for memory-writing rules, what counts as worth remembering, and what to exclude
3. existing `MEMORY.md`
   - learn the default memory style already in use
4. recent `memory/YYYY-MM-DD.md`
   - learn the local daily memory writing style from actual files, not assumptions

Use these local rules as the primary source of truth.
If the local environment lacks them, then fall back to the generic guidance in this skill.

For ready-to-use prompt templates, read `{baseDir}/references/prompts.md`.

For each relevant date:

- read the imported archive entries for that day
- decide what is important enough to preserve in that day's log
- write the few high-value facts, decisions, research takeaways, task progress points, preferences, or lessons worth keeping for future review
- match existing OpenClaw daily memory style

Daily memory is a day log, not a default-memory summary. Do not over-filter it using long-term-memory standards.

Good output shape:

```md
# 2024-04-14

<!-- imported-memory provider=claude archive=data-...zip -->
- 开始用 Claude 辅助起草中文股东信，采用“逐段整理，最后整合全文”的工作方式。
```

Bad output shape:

- profile dumps
- long autobiographical summaries
- “Claude 备份显示……”
- verbose provenance in the body

### 4. Distill `MEMORY.md` Candidates

Choose one of these modes explicitly:

1. `source-memory only`
   Use a dedicated memory-like file from the import source when available, such as Claude `memories.json`.

2. `archive-distill only`
   Distill `MEMORY.md` candidates directly from the imported archive.

3. `hybrid`
   Use source memory as the base, then refine or supplement it from archive evidence.

Default:

- if source memory exists, prefer `source-memory only`
- only use `archive-distill only` or `hybrid` when the user explicitly wants the heavier path

Before choosing wording and granularity, read local `MEMORY.md` and recent daily memory files so the imported candidates match the current workspace style.

Preferred user-facing wording:

- call `MEMORY.md` the default memory or 默认记忆
- only use “长期记忆” when needed to contrast it with daily logs
- avoid treating “long-term memory” as the canonical product term

Warn the user that archive-wide `MEMORY.md` distillation is slower and more dependent on model quality.

### 5. Stage Review Payload

After the model writes daily memory bullets and `MEMORY.md` bullets, save them in a JSON payload with this shape:

```json
{
  "daily_memory": [
    {
      "date": "2024-04-14",
      "source_provider": "claude",
      "source_archive": "claude-export.zip",
      "bullets": [
        "开始用外部模型辅助起草正式中文文稿，采用“逐段整理，最后整合全文”的工作方式。"
      ]
    }
  ],
  "memory_md": [
    {
      "section": "关于用户",
      "source_provider": "claude",
      "source_archive": "claude-export.zip",
      "bullets": [
        "用户可在多语言环境中自然切换，个人交流常偏好中文。",
        "长期关注科技、游戏与时事。"
      ]
    }
  ]
}
```

Then stage or apply with:

```bash
python3 {baseDir}/scripts/memory_merge.py /path/to/payload.json --review-root tmp/chat-history-import-review
```

Use `memory_md` as the preferred payload key.
`long_term_memory` is still accepted for compatibility, but new work should use `memory_md`.

### 6. Apply

Daily memory can be applied directly:

```bash
python3 {baseDir}/scripts/memory_merge.py /path/to/payload.json --memory-root memory --apply-daily
```

`MEMORY.md` candidates must be confirmed first:

```bash
python3 {baseDir}/scripts/memory_merge.py /path/to/payload.json --memory-file MEMORY.md --apply-long-term
```

After a successful import, ask the user whether they want to delete the source archive, extracted source directory, and temp files to save disk space.
Do not delete them without explicit confirmation.

## Output Expectations

When reporting progress or completion, include:

- detected source format
- archive root written
- import-batch validation result
- full-archive validation result (if checked)
- reviewed dates / total imported dates
- which daily memory dates were updated
- whether `MEMORY.md` candidates were only staged or also applied

## Guardrails

- Do not claim imported archive compatibility unless validation passes.
- Do not describe the current import as failed when only pre-existing archive files failed full-archive validation.
- Do not imply that imported history will automatically be searchable unless the workspace also has an archive-retrieval workflow such as `conversation-history`.
- Do not imply that future live chats will keep flowing into the same archive tree unless `conversation-archive` or equivalent live archive plumbing is enabled.
- Do not let imported daily memory read like a profile summary.
- Do not silently overwrite existing `MEMORY.md` facts.
- Do not add bulky metadata into daily memory bodies.
- Do not skip daily-memory review based only on titles, thread names, or sparse sampling.
- Do not apply `MEMORY.md` filtering standards to daily memory distillation.
- Do not assume unknown source formats can be handled safely without inspection.
- Do not promote a temporary parser into the skill unless it is stable and broadly reusable.
- Do not invent memory-writing preferences when the local OpenClaw environment already exposes them in config or existing memory files.

Read `{baseDir}/references/schema.md` before changing archive output.
