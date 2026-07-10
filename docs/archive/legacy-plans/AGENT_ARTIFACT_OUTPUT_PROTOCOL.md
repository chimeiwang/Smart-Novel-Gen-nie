> 状态：历史归档，不作为当前实现依据。当前事实以 `DOCS.md`、`AGENTS.md`、`src/agents/AGENTS.md`、代码和 schema 为准。

# Agent 产物输出协议设计记录

> 记录时间：2026-06-15
>
> 背景：`propose_updates` 在提交长篇大纲修改草案时出现 tool arguments JSON 解析失败。失败原因不是用户输入非法，而是模型把十章大纲正文塞进 JSON tool arguments 后，长文本中的引号、标点或截断导致 JSON 不合法。

## 核心结论

不要让模型用 JSON tool arguments 承载小说正文、大纲全文、设定长文或返工稿。

JSON 工具参数只应该用于短控制信号和结构化元数据；长篇创作产物应该作为独立的 assistant 正文输出，被系统保存为 `ReviewArtifact`。审核通过后，再进入单独的结构化应用/落库流程。

一句话：

```text
工具 JSON 负责流程控制，产物正文负责给人审核，数据库更新负责最终落库。
```

## 当前问题

现有流程倾向于让 Agent 通过 `propose_updates` 一次性提交：

- `summary`
- `artifactKey`
- `reviewerAgent`
- `submitForReview`
- `updates.outlineAdjustments[].content`
- `updates.foreshadowing[]`

当 `content` 里包含整章或十章大纲草案时，tool arguments 会变成一段很长的 JSON。模型必须同时完成两件事：

1. 创作/改写长篇内容。
2. 保持整个 JSON 参数完全合法，包括所有引号、换行、逗号、转义。

这对模型来说不稳定。上下文越长、草案越长，越容易出现以下问题：

- 漏掉逗号或右括号。
- 字符串中出现未转义的双引号。
- 长文本中途截断。
- 把参数正文写成 assistant 文本。
- tool arguments 解析失败后没有真正重试机会。

这类问题不能靠简单加强提示词彻底解决。

## 设计原则

1. 长文本不进 tool arguments。
2. 工具调用只传短字段、短数组和流程元数据。
3. “给人看的草案”和“写数据库的结构化更新”分离。
4. 审核对象应该是完整可读的产物，而不是碎片化 updates。
5. 落库前必须有明确的用户确认。
6. JSON 解析失败只能作为兜底恢复机制，不能成为主流程依赖。

## 推荐流程

```text
剧情 Agent 讨论、查询、设计修改方案
        ↓
调用 submit_artifact_intent / begin_artifact_output
        ↓
系统进入“产物输出模式”
        ↓
剧情 Agent 最后一轮只输出纯正文草案
        ↓
系统把 assistant content 保存为 ReviewArtifact
        ↓
编辑 Agent 读取 ReviewArtifact 正文并复审
        ↓
编辑通过后，前端弹窗给用户最终审核
        ↓
用户确认应用
        ↓
系统进入结构化应用步骤
        ↓
逐章生成并校验 outlineAdjustments / foreshadowing
        ↓
落库
```

## 输出类型拆分

### 普通聊天输出

用途：

- 讨论需求。
- 解释判断。
- 给出评审意见。
- 汇报流程进展。

特点：

- 可以是自然语言。
- 可以分段。
- 可以包含少量列表。
- 进入聊天记录。

### 产物输出

用途：

- 小说正文。
- 大纲草案。
- 设定草案。
- 返工稿。
- Beat plan 正文。

特点：

- 是一个明确的产物，不是闲聊。
- 最后一轮只输出产物正文。
- 不输出 JSON。
- 不输出工具参数。
- 不输出额外解释或寒暄。
- 系统直接把 assistant content 保存为 `ReviewArtifact`。

示例提示：

```text
现在进入产物输出模式。
请只输出《前十章大纲修改草案》正文。
不要解释，不要 JSON，不要工具参数，不要额外寒暄。
```

## 工具职责调整

### 不推荐

让 `propose_updates` 承载长正文：

```json
{
  "summary": "前十章大纲调整",
  "updates": {
    "outlineAdjustments": [
      {
        "action": "update",
        "nodeTitle": "第一章",
        "content": "很长很长的第一章修改后大纲……"
      }
    ]
  }
}
```

风险：`content` 越长，JSON 越容易坏。

### 推荐

让工具只传元数据：

```json
{
  "artifactKey": "遗产猎人-前十章大纲调整-v1",
  "kind": "outline_draft",
  "reviewerAgent": "编辑",
  "submitForReview": true,
  "summary": "根据编辑七条商业评审意见生成前十章大纲修改草案。"
}
```

正文由最后一次 assistant content 承载：

```text
第一章 遗孤与遗产
……

第二章 山谷里的哭声
……
```

## ReviewArtifact 建议类型

后续可以扩展 `ReviewArtifact.kind`：

- `agent_updates`：结构化 updates 草案。
- `outline_draft`：大纲文本草案。
- `chapter_draft`：章节正文草案。
- `lore_draft`：设定文本草案。
- `revision_brief`：返工说明。
- `beat_plan_draft`：写作节拍草案。

其中 `outline_draft`、`chapter_draft`、`lore_draft` 等长文本产物应优先保存 assistant content，而不是 tool arguments。

## 应用/落库流程

用户审核通过后，不应直接把文本草案硬写进数据库。

建议进入单独的结构化应用步骤：

1. 系统读取已通过的 `ReviewArtifact`。
2. 针对目标数据类型选择应用器。
3. 如果是大纲草案，则逐章生成 `outlineAdjustments`。
4. 对每个结构化 patch 做 schema 校验。
5. 预览 diff。
6. 用户确认后落库，或由用户已确认的 artifact 自动进入落库事务。

这样可以把“创作质量审核”和“数据库结构化写入”拆开。

## 兜底机制

即使主流程改成产物正文，也仍应保留兜底：

1. tool arguments JSON 解析失败时，不要把坏参数当 `{}`。
2. 不要直接落库。
3. 可以把错误作为 tool result 喂回模型，允许一次短参数重试。
4. 如果连续失败，再终止并向前端展示明确错误。
5. 日志中记录 raw arguments preview、工具名、requestId。

兜底机制的目标是恢复短参数错误，不是鼓励继续把长文本塞进 JSON。

## 前端展示建议

前端应区分：

- 聊天消息。
- 流程日志。
- 待审核产物。
- 待应用 diff。

当 `ReviewArtifact.status === "awaiting_user"` 时，前端应直接弹出审核面板，并保留底部卡片入口。

审核面板应展示：

- artifact 标题/类型。
- 创建 Agent。
- 复审 Agent。
- 复审结论。
- 草案正文预览。
- 变更摘要。
- 操作按钮：应用、继续修改、丢弃。

## 日志与调试

需要补齐“本轮到底发给模型什么”的可观测性：

- requestId。
- messages 清单：role、字符数、摘要。
- tools schema 摘要。
- tool calls 清单。
- tool arguments 长度。
- parse error 位置和 preview。
- 产物正文长度。
- artifactId / artifactKey / status。

这样排查时可以明确区分：

- 用户输入。
- 系统上下文。
- 工具 schema。
- 模型正文输出。
- 模型工具调用参数。
- runtime 处理结果。

## 成功标准

改造完成后，应满足：

1. 十章大纲草案可以稳定生成，不再依赖超长 JSON tool arguments。
2. 模型输出的长草案可以完整保存为 `ReviewArtifact`。
3. 编辑 Agent 能读取该 artifact 并复审。
4. 编辑通过后，用户能看到明确审核弹窗。
5. 用户确认后，系统能进入结构化应用步骤。
6. 任何落库操作都经过 schema 校验和权限校验。
7. tool arguments JSON 解析失败不会导致静默丢草案。

## 迁移建议

优先级建议：

1. 新增文本型 `ReviewArtifact` 保存路径。
2. 新增“产物输出模式”协议。
3. 让剧情/写作/设定 Agent 的长草案走产物输出模式。
4. 保留 `propose_updates` 处理短结构化 updates。
5. 增加审核弹窗与请求审计日志。
6. 最后再做文本 artifact 到结构化 patch 的应用器。

不要一开始就试图一次性改完所有 Agent。先从“大纲修改草案”这个失败场景落地。
