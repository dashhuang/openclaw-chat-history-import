# OpenClaw Chat History Import

An OpenClaw skill bundle for turning your past AI chat history into OpenClaw's own memory.

这是一个 OpenClaw skill bundle，核心用途是把你过去在其他 AI 工具里的聊天记录，导入到 OpenClaw 里，变成龙虾自己的记忆。

It helps migrate old conversations from tools like ChatGPT and Claude into OpenClaw, so that past chat history can become:

它适合把 ChatGPT、Claude 等工具里的旧聊天迁移进 OpenClaw，让这些历史记录变成：

- searchable raw archive
- daily memory
- `MEMORY.md`

- 可搜索的原始 archive
- 每日记忆
- `MEMORY.md`

In short: instead of leaving your old AI conversations stranded across different products, this bundle helps bring them into OpenClaw's own memory system.

一句话说：它不是把旧聊天继续留在别的 AI 产品里，而是把它们收进 OpenClaw 自己的记忆系统里。

The bundle currently includes two companion skills:

这个仓库目前包含两个互相配合的 skill：

- `chat-history-import`
- `conversation-history`

`chat-history-import` imports external history into:

`chat-history-import` 会把外部聊天历史导入到：

- `logs/message-archive-raw/`
- `memory/YYYY-MM-DD.md`
- `MEMORY.md`

`conversation-history` searches archive files later, so agents can recall old decisions, links, wording, and chronology.

`conversation-history` 用来在导入后搜索 archive 文件，方便 agent 回忆旧决策、旧链接、原话和时间线。

This bundle is designed for interactive, review-first migration from Claude exports, ChatGPT exports, Slack-style transcripts, and other structured or semi-structured chat archives.

这个 bundle 面向交互式、先审阅再落盘的迁移流程，适合 Claude 导出、ChatGPT 导出、Slack 风格转储，以及其他结构化或半结构化聊天存档。

## Common Sources

## 常见来源

The most common use case is importing history from previous AI chat tools, especially ChatGPT and Claude.

最常见的使用场景，是把你在其他 AI 聊天工具里的旧历史导入进来，尤其是 ChatGPT 和 Claude。

### ChatGPT export

### ChatGPT 导出

As of 2026-03-19, the usual path is:

截至 2026-03-19，常见导出路径是：

- ChatGPT
- `Settings`
- `Data Controls`
- `Export`

That export usually arrives as a ZIP and commonly includes files such as `conversations.json`.

导出的结果通常是一个 ZIP，里面常见会有 `conversations.json` 之类的文件。

### Claude export

### Claude 导出

As of 2026-03-19, the usual path is:

截至 2026-03-19，常见导出路径是：

- Claude
- `Settings`
- `Privacy`
- `Export data`

That export also typically arrives as a ZIP and may include files such as `conversations.json`, `memories.json`, `projects.json`, and account metadata.

导出的结果通常也是一个 ZIP，里面可能包含 `conversations.json`、`memories.json`、`projects.json` 以及账户元数据。

If the source is not ChatGPT or Claude, this bundle can still help, but the import may need model-assisted format inspection or a temporary parser.

如果来源不是 ChatGPT 或 Claude，这个 bundle 也仍然可以尝试导入，只是更可能需要模型辅助识别格式，或者临时写一个 parser。

## Included Skills

## 包含的 Skills

### `chat-history-import`

The main import workflow.

主导入工作流。

Use it to inspect export files, normalize raw history into `logs/message-archive-raw/`, distill daily memory, and stage `MEMORY.md` candidates for review.

它负责检查导出文件、把原始聊天规范化写入 `logs/message-archive-raw/`、提炼 daily memory，并生成待审阅的 `MEMORY.md` 候选内容。

### `conversation-history`

The companion retrieval workflow.

配套的历史检索工作流。

Use it after import when an agent needs to search old decisions, exact wording, old links, or chronology from raw archive files.

在导入完成后，如果 agent 需要查找旧决策、原话、旧链接或时间线，就使用它来搜索 raw archive 文件。

## Recommended Companion Components

## 推荐搭配组件

### `conversation-archive` plugin

Recommended, but not required.

推荐安装，但不是硬依赖。

Use it when you want imported history and future live chat history to live under the same archive layout.

如果你希望“导入的旧历史”和“未来实时聊天历史”都落到同一套 archive 目录结构里，就应该搭配它使用。

In practice:

实际效果是：

- `chat-history-import` backfills old history
- `conversation-archive` keeps new history flowing in
- `conversation-history` searches both imported and live archive data

- `chat-history-import` 负责补历史
- `conversation-archive` 负责持续写入新消息
- `conversation-history` 负责搜索导入历史和实时归档

## Requirements

## 依赖

- OpenClaw
- `python3`

## Install

## 安装

### Install `chat-history-import`

### 安装 `chat-history-import`

Copy the repository root into:

把仓库根目录复制到：

```text
<workspace>/skills/chat-history-import
```

### Install `conversation-history`

### 安装 `conversation-history`

Copy the companion skill directory into:

把配套 skill 目录复制到：

```text
<workspace>/skills/conversation-history
```

### Shared on one machine

### 单机共享安装

For shared install, copy:

如果想做共享安装，复制到：

```text
~/.openclaw/skills/chat-history-import
~/.openclaw/skills/conversation-history
```

Then start a new OpenClaw session or run:

然后启动一个新的 OpenClaw session，或者运行：

```bash
openclaw skills info chat-history-import
openclaw skills info conversation-history
```

## Duplicate Install Notes

## 重复安装说明

If OpenClaw already provides `conversation-history` from a plugin or shared skills directory, avoid installing a second copy into the same scope.

如果 OpenClaw 已经通过插件或 shared skills 目录提供了 `conversation-history`，就不要在同一个 scope 里再装第二份。

Practical rule:

实践上建议这样处理：

- one `conversation-history` per scope is best
- workspace-local copies typically override shared copies
- if both exist, check `openclaw skills info conversation-history` to see which source is active

- 每个 scope 最好只保留一份 `conversation-history`
- workspace-local 通常会覆盖 shared 版本
- 如果两份都在，运行 `openclaw skills info conversation-history` 看当前实际生效的是哪一份

## Publish To ClawHub

## 发布到 ClawHub

For the import skill at repo root:

发布仓库根目录的导入 skill：

```bash
clawhub publish . \
  --slug chat-history-import \
  --name "Chat History Import" \
  --version 0.1.0 \
  --tags latest \
  --changelog "Initial public release."
```

For the companion retrieval skill:

发布配套的检索 skill：

```bash
clawhub publish ./conversation-history \
  --slug conversation-history \
  --name "Conversation History" \
  --version 0.1.0 \
  --tags latest \
  --changelog "Initial public release."
```

## Validate Locally

## 本地校验

```bash
python3 -m py_compile scripts/*.py
python3 -m py_compile conversation-history/scripts/*.py
openclaw skills info chat-history-import
```

## Repository Layout

## 仓库结构

- `SKILL.md`
  OpenClaw skill entrypoint and workflow instructions for `chat-history-import`.
- `conversation-history/`
  Companion archive retrieval skill.
- `references/`
  Archive schema and memory distillation prompt templates.
- `scripts/`
  Deterministic helpers for inspect, normalize, validate, and merge.

- `SKILL.md`
  `chat-history-import` 的 OpenClaw skill 入口和工作流说明。
- `conversation-history/`
  配套的 archive 检索 skill。
- `references/`
  archive schema 与 memory 提炼提示词模板。
- `scripts/`
  用于 inspect、normalize、validate 和 merge 的确定性辅助脚本。

## License

## 许可证

MIT
