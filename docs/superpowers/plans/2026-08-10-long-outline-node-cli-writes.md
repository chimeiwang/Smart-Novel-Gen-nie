# 长篇分层大纲节点生产写入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 安全开放长篇分层大纲节点的生产创建、更新和删除能力。

**Architecture:** Core 为现有节点资源补创建幂等和更新/删除 CAS；Web 与 CLI 只调用公共 `/api/v1/**`；生产 Skill 以精确白名单执行 GET、完整 Diff、一次确认、写入和回读。现有数据库模型不变。

**Tech Stack:** FastAPI、Pydantic、SQLAlchemy、Python CLI、Next.js/TypeScript、PowerShell Skill。

---

### Task 1：Core 节点并发契约

**Files:**
- Modify: `apps/core-api/src/inkforge_core/outlines/schemas.py`
- Modify: `apps/core-api/src/inkforge_core/outlines/service.py`
- Modify: `apps/core-api/src/inkforge_core/outlines/repository.py`
- Modify: `apps/core-api/src/inkforge_core/outlines/router.py`
- Test: `apps/core-api/tests/outlines/test_outline_node_cas.py`

- [ ] 先写创建幂等、更新/删除 CAS 的失败测试并确认因契约缺失而失败。
- [ ] 复用 `command_resource_id("outline_nodes", ...)` 和 `require_expected_updated_at()` 实现最小安全契约。
- [ ] 运行 `uv run pytest apps/core-api/tests/outlines -q` 确认通过。

### Task 2：Web 公共调用兼容

**Files:**
- Modify: `apps/web/src/features/outline/outline-panel.tsx`
- Create: `apps/web/src/features/outline/__tests__/outline-node-concurrency-source.test.ts`
- Regenerate: `packages/api-client/src/generated/schema.d.ts`

- [ ] 先写源码契约测试，要求创建携带稳定请求 ID、更新和删除携带编辑基线版本。
- [ ] 修正节点表单基线和请求体，移除误发到 body 的 `novelId`。
- [ ] 运行 API 生成与相关 Web 测试。

### Task 3：CLI 三条节点写命令

**Files:**
- Create: `tools/inkforge-cli/src/inkforge_cli/commands/long/outline_nodes.py`
- Modify: `tools/inkforge-cli/src/inkforge_cli/registry.py`
- Modify: `tools/inkforge-cli/tests/test_registry.py`
- Create: `tools/inkforge-cli/tests/test_long_outline_node_mutations.py`
- Modify: `tools/inkforge-cli/README.md`

- [ ] 先写精确路由、请求体、字段校验和 registry 失败测试。
- [ ] 实现 create/update/delete handler 并注册为三条精确命令。
- [ ] 运行全部 CLI 测试。

### Task 4：生产 Skill 安全开放

**Files:**
- Modify: `C:/Users/niebo/.codex/skills/inkforge-production-short-story-operator/SKILL.md`
- Modify: `C:/Users/niebo/.codex/skills/inkforge-production-short-story-operator/scripts/operator.ps1`
- Modify: `C:/Users/niebo/.codex/skills/inkforge-production-short-story-operator/references/cli-contract.md`
- Modify: `C:/Users/niebo/.codex/skills/inkforge-production-short-story-operator/references/long-creative-material-writes.md`
- Modify: `C:/Users/niebo/.codex/skills/inkforge-production-short-story-operator/tests/long-cli.Tests.ps1`
- Modify: `C:/Users/niebo/.codex/skills/inkforge-production-short-story-operator/tests/structured-writes.Tests.ps1`

- [ ] 先修改离线测试预期，确认三条命令仍被拒绝。
- [ ] 更新精确白名单、命令计数、Diff/CAS/恢复说明和矩阵。
- [ ] 运行 PowerShell 离线测试与 Skill 校验。

### Task 5：完整验证

- [ ] 运行 Core outline 测试、全部 CLI 测试、Web 相关测试。
- [ ] 运行 Ruff、Mypy、API client check、TypeScript 和 ESLint。
- [ ] 核对 `git diff` 只包含本功能文件和既有 `.tmp/` 不被触碰。
