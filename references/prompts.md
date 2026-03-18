# Memory Distillation Prompts

Use these templates after you have already:

1. imported raw chat history into `logs/message-archive-raw/`
2. read local `openclaw.json` memoryFlush settings
3. read local `AGENTS.md`
4. read local `MEMORY.md`
5. read several recent `memory/YYYY-MM-DD.md` files

The local workspace always wins over these defaults.

## Daily Memory Prompt

### System Prompt

```text
提取值得记住的内容，不要废话。
```

### User Prompt Template

```text
将以下某一天的导入聊天记录提炼写入 memory/YYYY-MM-DD.md。

优先遵循当前本地 OpenClaw 的记忆规则：
- memoryFlush.systemPrompt
- memoryFlush.prompt
- workspace/AGENTS.md 中关于记忆写法的要求
- 最近几天 memory/YYYY-MM-DD.md 的真实风格

聚焦于：
- 决策
- 状态变更
- 经验教训
- 待办事项
- 重要研究结论
- 重要问答结论
- 任务推进与排查结果
- 只有当确实稳定且有价值时，才记录偏好

如果没有值得存储的内容：NO_FLUSH

要求：
1. 只写当天新增、当天重要、以后回看有价值的内容。
2. 不要写闲聊、寒暄、纯机械执行细节或明显无回看价值的碎片。
3. 不要写“Claude 备份显示”“导入记录表明”之类的来源措辞。
4. 正文风格尽量贴近当前本地 daily memory 文件。
5. 一般输出 1-5 条简洁 bullet；只有当天明显是专题整理时才使用短标题。
6. 不要写成长篇 profile summary。
7. 只输出适合写进 memory/YYYY-MM-DD.md 的 Markdown 正文，不要解释。

日期：{{date}}
导入来源注释：{{html_comment}}
当天聊天摘要或原文：{{day_archive_excerpt}}
```

### Good Output Example

```md
<!-- imported-memory provider=claude archive=data-...zip -->
- 开始用 Claude 辅助起草中文股东信，采用逐段整理、最后整合全文的工作方式。
```

## `MEMORY.md` Prompt

Use one of the following modes explicitly.

### Mode A: `source-memory only`

Use when the import source already includes memory-like summary content, such as Claude `memories.json`.

#### System Prompt

```text
提取值得写进 MEMORY.md 的内容，不要废话。
```

#### User Prompt Template

```text
将以下导入源自带的记忆摘要，整理成适合合并进 MEMORY.md 的候选内容。

优先遵循当前本地 OpenClaw 的默认记忆风格：
- 现有 MEMORY.md 的表达方式
- workspace/AGENTS.md 对默认记忆的要求

只保留：
- 长期稳定的个人偏好
- 长期稳定的项目背景
- 长期有效的工作方式
- 重要资产与长期事项
- 跨会话值得保留的高价值背景

不要保留：
- 临时情绪
- 当天新闻
- 一次性问答
- 过长背景叙述
- 明显过期或不确定的信息

要求：
1. 输出贴近现有 MEMORY.md 风格：简洁、稳定、跨会话有用。
2. 不要写来源措辞，不要解释为什么选它。
3. 能压缩成短 bullet 就不要写长段。
4. 能并入已有概念就不要重复造新表述。
5. 如果没有足够稳定的内容，返回 NO_FLUSH。
6. 按目标章节分组输出；优先复用现有 MEMORY.md 里的章节名。
7. 如果现有章节都不合适，只新增一个很短的新章节名。
8. 只输出候选条目，格式用 JSON：

```json
[
  {
    "section": "关于用户",
    "bullets": [
      "..."
    ]
  }
]
```

现有 MEMORY.md：{{current_memory}}
导入源长期记忆：{{source_memory}}
```

### Mode B: `archive-distill only`

Use when no source long-term memory exists, or when the user explicitly wants archive-wide distillation.

#### System Prompt

```text
提取值得写进 MEMORY.md 的内容，不要废话。
```

#### User Prompt Template

```text
阅读以下导入聊天 archive 的高价值摘要，提炼出适合合并进 MEMORY.md 的候选内容。

优先遵循当前本地 OpenClaw 的默认记忆风格：
- 现有 MEMORY.md
- workspace/AGENTS.md
- 近几天 daily memory 如何把短期信息升级为 MEMORY.md

只保留：
- 长期稳定的偏好
- 持续有效的决策或约束
- 长期项目背景
- 重要资产与长期安排
- 高复用的工作流或经验

不要保留：
- 单日事件本身
- 闲聊
- 一次性问答
- 冗长叙事
- 只适合写入 daily memory 的内容

要求：
1. 比 daily memory 更稳定、更抽象。
2. 输出尽量短，宁缺毋滥。
3. 不要写来源说明，不要写“可能”“似乎”等模糊废话。
4. 如果没有足够稳定的内容，返回 NO_FLUSH。
5. 按目标章节分组输出；优先复用现有 MEMORY.md 里的章节名。
6. 如果现有章节都不合适，只新增一个很短的新章节名。
7. 只输出 JSON：

```json
[
  {
    "section": "工作方式",
    "bullets": [
      "..."
    ]
  }
]
```

现有 MEMORY.md：{{current_memory}}
导入 archive 摘要：{{archive_summary}}
```

### Mode C: `hybrid`

Use source long-term memory as the base, then refine or supplement it from archive evidence.

#### User Prompt Template

```text
先以导入源自带的记忆摘要为底稿，再结合 archive 摘要做补充和纠偏，整理成适合合并进 MEMORY.md 的候选内容。

要求：
1. 保留稳定、长期、跨会话有价值的信息。
2. 删除明显过期、重复、一次性的信息。
3. 如果 archive 与 source memory 冲突，以更可靠、更近期、更稳定的内容为准。
4. 输出保持简洁，不写来源说明。
5. 按目标章节分组输出；优先复用现有 MEMORY.md 的章节。
6. 只输出 JSON，格式同上。

现有 MEMORY.md：{{current_memory}}
导入源长期记忆：{{source_memory}}
导入 archive 摘要：{{archive_summary}}
```

## Review Prompt

Use this when showing `MEMORY.md` candidates to the user before apply.

```text
下面是准备合并进 MEMORY.md 的候选内容。

请按三类整理给用户看：
1. 建议保留
2. 建议忽略
3. 与现有 MEMORY.md 重复或冲突，需要确认

要求：
- 简洁
- 逐条列出
- 不要重写候选本身，只做 review 说明

现有 MEMORY.md：{{current_memory}}
候选内容：{{candidate_bullets}}
```
