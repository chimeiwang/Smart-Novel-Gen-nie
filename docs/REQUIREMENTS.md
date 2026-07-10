# 需求文档索引

本文只做入口索引，不再维护旧 `@X.X` 追溯体系。文档治理规则见根目录 `DOCS.md`。

铁律：需求文档必须描述当前项目事实。若与代码、`prisma/schema.prisma`、共享契约或测试冲突，以项目事实为准并修正文档。

## 当前权威需求

| 领域 | 文档 | 状态 |
| --- | --- | --- |
| 总览 | `docs/requirements/00-overview.md` | 当前事实 |
| 项目与章节 | `docs/requirements/01-projects-and-chapters.md` | 当前事实 |
| 创作资料库 | `docs/requirements/02-creative-knowledge-base.md` | 当前事实 |
| AI 写作与 Agent | `docs/requirements/03-ai-writing-and-agents.md` | 当前事实 |
| 草案审核、质量检查与工作流 | `docs/requirements/04-review-quality-and-workflow.md` | 当前事实 |
| 认证、计费与运维 | `docs/requirements/05-auth-billing-and-ops.md` | 当前事实 |

## 历史需求碎片

以下文件是早期需求追溯碎片，只能作为历史线索，不能作为当前权威：

- `docs/archive/legacy-requirements/2.2-autosave.md`
- `docs/archive/legacy-requirements/2.3-word-count.md`
- `docs/archive/legacy-requirements/3.1-ai-continuation.md`
- `docs/archive/legacy-requirements/5.1-agent-core.md`
- `docs/archive/legacy-requirements/5.2-agent-tools.md`
- `docs/archive/legacy-requirements/5.3-agent-routing.md`
- `docs/archive/legacy-requirements/5.4-agent-context.md`
- `docs/archive/legacy-requirements/6.2-langsmith-tracing.md`

如果这些碎片里仍有有效规则，迁入上方 `00-05` 文档；不要继续扩展旧编号体系。

## 新需求写法

新功能不要新增 `X.X-slug.md` 编号碎片。所有后续需求都必须先写 spec，再执行修改：

```text
docs/specs/YYYY-MM-DD-short-name.md
```

spec 必须包含：

- 背景；
- 当前项目事实；
- 目标；
- 非目标；
- 设计与契约变更；
- 影响范围；
- 验收标准。

需求落地后，再把已经成为当前事实的内容迁入对应 `00-05` 需求文档。
