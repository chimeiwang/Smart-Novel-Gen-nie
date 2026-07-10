# CLAUDE.md

本仓库不再维护第二套 Claude 专用开发规范。

请以以下根级权威文档为准：

- `DOCS.md`：文档规范、权威层级、归档规则。
- `AGENTS.md`：开发护栏、项目事实、实现规则。
- `DESIGN.md`：前端设计规范。
- `src/agents/AGENTS.md`：Agent 当前架构与协议。

如果这些文档与当前代码、`prisma/schema.prisma`、`package.json` 或测试冲突，必须以项目事实为准并修正文档。

历史说明：旧版 `CLAUDE.md` 包含 SQLite、旧 JSON response-parser、旧 executor、需求编号追溯等过期规则，已移除，不能作为当前实现依据。
