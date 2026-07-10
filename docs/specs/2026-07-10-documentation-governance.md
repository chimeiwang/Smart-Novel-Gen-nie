# 文档治理与 spec-first 需求流程

## 背景

仓库中长期存在多套需求、计划、蓝图、审计和助手指南文档。部分文档记录的是历史方案，部分文档仍描述当前系统，混在一起会导致后续开发引用旧事实。

本次文档治理要求建立明确的权威层级，并增加硬性限制：后续所有需求必须先写 spec，再执行修改。

## 当前项目事实

- 根目录 `DOCS.md` 是文档治理权威入口。
- 根目录 `AGENTS.md` 是 Codex 开发护栏。
- 根目录 `DESIGN.md` 是 UI / CSS / 交互设计规范。
- `src/agents/AGENTS.md` 是当前 Agent 架构与协议权威文档。
- 当前需求事实集中在 `docs/requirements/00-overview.md` 到 `docs/requirements/05-auth-billing-and-ops.md`。
- 历史需求碎片、旧计划、旧蓝图、旧审计和旧 superpowers 文档已经迁入 `docs/archive/`，不作为当前实现依据。
- 项目事实以当前代码、`prisma/schema.prisma`、`package.json`、共享 contract 和测试为最高优先级。

## 目标

- 建立清晰的文档权威层级。
- 明确历史归档文档不能作为新开发依据。
- 强制后续需求先在 `docs/specs/` 新增或更新 spec。
- spec 必须先说明背景、当前事实、目标、非目标、设计方案、影响范围和验收标准。
- 实现修改必须按 spec 落地，并在完成后把已经成为当前事实的内容迁入对应当前需求或架构文档。

## 非目标

- 不重建旧 `@X.X` 需求追溯体系。
- 不让 `docs/specs/**` 自动高于当前代码和 schema。
- 不把历史归档文件恢复为当前权威。
- 不为一次性调查、审计或解释请求强制创建 spec。

## 设计方案

1. 根目录新增或维护 `DOCS.md`，作为文档治理和权威层级入口。
2. `AGENTS.md` 明确要求：接到任何后续需求后，先新增或更新 spec，再执行实现修改。
3. `docs/REQUIREMENTS.md` 只维护当前需求入口和新需求写法，不继续扩展旧编号碎片。
4. `docs/specs/README.md` 固化 spec 文件命名与必填结构。
5. 旧文档迁入 `docs/archive/` 后必须标明历史归档状态。
6. 后续需求执行顺序固定为：
   - 查当前事实；
   - 写 spec；
   - 按 spec 修改代码、schema、文档或测试；
   - 按验收标准验证；
   - 必要时更新当前需求或架构文档。

## 影响范围

- `DOCS.md`
- `AGENTS.md`
- `CLAUDE.md`
- `README.md`
- `docs/README.md`
- `docs/REQUIREMENTS.md`
- `docs/BACKLOG.md`
- `docs/specs/README.md`
- `docs/archive/**`
- `docs/requirements/**`
- `src/agents/AGENTS.md`
- 与文档治理相关的后续开发流程

## 验收标准

- 根目录存在 `DOCS.md`，且明确项目事实优先和 spec-first 需求规则。
- `AGENTS.md` 要求后续需求先写 spec，再执行修改。
- `docs/REQUIREMENTS.md` 不再要求新增旧编号需求碎片，改为指向 `docs/specs/YYYY-MM-DD-short-name.md`。
- `docs/specs/README.md` 给出 spec 命名和必填结构。
- `docs/archive/**` 下历史文档有明确归档状态，不作为当前实现依据。
- 当前权威文档不得要求从旧 SQLite、旧 response-parser、旧 executor 或旧 `docs/superpowers/**` 推断当前事实。
- `git diff --check` 通过。
