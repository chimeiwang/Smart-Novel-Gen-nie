# CLAUDE.md

本仓库不再维护第二套 Claude 专用开发规范。

请以以下根级权威文档为准：

- [DOCS.md](DOCS.md)：文档规范、事实核对与内容归属。
- [AGENTS.md](AGENTS.md)：开发执行规则、边界、必读入口与验证要求。
- [DESIGN.md](DESIGN.md)：前端设计规范。
- [Agent 指导](apps/agent-service/AGENTS.md)：Agent 架构与协议。

产品事实按 [产品总览](docs/requirements/00-overview.md)及相关需求核对，具名数据变更读取
[授权清单](docs/DATA_CHANGE_AUTHORIZATIONS.md)及对应规格。事实优先级与文档维护方式统一遵循 `DOCS.md`。

历史说明：旧版 `CLAUDE.md` 包含 SQLite、旧 JSON response-parser、旧 executor、需求编号追溯等过期规则，已移除，不能作为当前实现依据。
