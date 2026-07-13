# 本地与线上功能逐项验收计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 逐项验证 Python 三服务迁移后的用户功能，修复硬故障，单独记录不阻断验收的 Agent 效果问题，并在本地全部通过后验证生产地址。

**Architecture:** 以当前 `main`、现有 PostgreSQL、根目录三服务启动器和六个 Playwright 主流程为权威基线。每个流程单独运行以隔离故障；自动化未覆盖的页面守卫、章节状态、会话恢复和草案边界通过真实浏览器与公共 API 补验。生产验收只在本地门禁全部通过后执行，并使用随机测试账号和测试小说隔离业务数据。

**Tech Stack:** Next.js 16、FastAPI、PostgreSQL、Redis、LangGraph、Playwright、PowerShell。

---

### Task 1: 建立本地三服务基线

**Files:**
- Read: `scripts/dev.mjs`
- Read: `.env.local`
- Verify: `apps/core-api/src/inkforge_core/app.py`
- Verify: `apps/agent-service/src/inkforge_agents/app.py`

- [x] **Step 1: 核对 43119、8000、8001 和 Redis 监听进程是否属于当前仓库**

Run:

```powershell
Get-NetTCPConnection -State Listen | Where-Object LocalPort -in 43119,8000,8001,6379
Get-CimInstance Win32_Process | Where-Object ProcessId -in $processIds | Select-Object ProcessId,CommandLine
```

Expected: 不保留来源不明或旧工作树的服务进程。

- [x] **Step 2: 启动当前 `main` 的 Next.js、Core API 和 Agent Service**

Run:

```powershell
npm run dev
```

Expected: 三个服务持续运行，任一子进程退出都会明确失败。

- [x] **Step 3: 验证三个真实健康入口**

Run:

```powershell
Invoke-WebRequest http://127.0.0.1:43119/login
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health/ready
Invoke-RestMethod http://127.0.0.1:8001/internal/v1/health/ready
```

Expected: 全部 HTTP 200，Core 的 configuration、database、database_schema、redis 为 ok，Agent 的 model_provider 为 ok。

### Task 2: 逐个运行六个 Playwright 主流程

**Files:**
- Verify: `tests/e2e/auth.spec.ts`
- Verify: `tests/e2e/project-editor.spec.ts`
- Verify: `tests/e2e/knowledge-style.spec.ts`
- Verify: `tests/e2e/quality-billing.spec.ts`
- Verify: `tests/e2e/writing-artifact.spec.ts`

- [x] **Step 1: 验证注册、退出和重新登录**

Run: `$env:E2E_BASE_URL='http://127.0.0.1:43119'; npx playwright test --grep '用户可以注册、退出并重新登录'`

Expected: 1 passed。

- [x] **Step 2: 验证小说创建和章节自动保存**

Run: `$env:E2E_BASE_URL='http://127.0.0.1:43119'; npx playwright test --grep '用户可以创建小说并自动保存章节'`

Expected: 认证准备和目标流程通过。

- [x] **Step 3: 验证设定、大纲、参考资料和文风画像**

Run: `$env:E2E_BASE_URL='http://127.0.0.1:43119'; npx playwright test --grep '用户可以维护设定、大纲、参考资料和文风画像'`

Expected: 认证准备和目标流程通过。

- [x] **Step 4: 验证一致性终检和零扣费摘要**

Run: `$env:E2E_BASE_URL='http://127.0.0.1:43119'; npx playwright test --grep '用户可以运行质量检查并查看模拟模型零扣费摘要'`

Expected: 认证准备和目标流程通过，fake 模型 token 计费为 0。

- [x] **Step 5: 验证写作草案生成和应用**

Run: `$env:E2E_BASE_URL='http://127.0.0.1:43119'; npx playwright test --grep '模拟模型可以完成写作会话和草案应用'`

Expected: 认证准备和目标流程通过，正式章节仅在用户应用后变化。

- [x] **Step 6: 验证待确认草案丢弃**

Run: `$env:E2E_BASE_URL='http://127.0.0.1:43119'; npx playwright test --grep '用户可以丢弃待确认草案'`

Expected: 认证准备和目标流程通过，章节正文保持未应用状态。

### Task 3: 补验自动化未覆盖的关键产品边界

**Files:**
- Verify: `apps/web/src/app/page.tsx`
- Verify: `apps/web/src/app/dashboard/page.tsx`
- Verify: `apps/web/src/app/workspace/[novelId]/page.tsx`
- Verify: `apps/web/src/app/billing/page.tsx`
- Verify: `apps/web/src/proxy.ts`
- Record: `docs/audits/2026-07-14-functional-verification.md`

- [x] **Step 1: 用 Playwright CLI 验证官网首页、登录入口和未登录页面守卫**

Expected: `/` 和 `/login` 可公开访问；未登录访问 `/dashboard`、`/styles`、`/billing` 和工作台会进入登录页。

- [x] **Step 2: 验证章节新增、切换、字数统计、送审和完成门槛**

Expected: 新章节顺序递增；正文刷新后保留；一致性终检未完成时不能标记完成；完成或显式跳过后允许完成。

- [x] **Step 3: 验证写作会话刷新恢复和待确认草案恢复**

Expected: 刷新或重新进入工作台后仍显示已持久化消息和待确认草案入口，未应用草案不进入正式正文。

- [x] **Step 4: 验证计费页、当前用户和越权保护的公共 API 响应**

Expected: 登录用户能读取 1000 初始积分摘要；未登录返回 401；跨用户小说、章节、任务和草案请求被拒绝。

### Task 4: 故障修复与 Agent 效果记录

**Files:**
- Modify: 仅修改失败证据指向的实现文件
- Test: 在对应 `tests/e2e/*.spec.ts` 或 Python 测试中增加最小回归用例
- Record: `docs/audits/2026-07-14-functional-verification.md`

- [x] **Step 1: 对每个硬故障保留失败截图、trace、请求状态和服务日志**

Expected: 根因证据能区分前端交互、Core 业务规则、Agent 队列、服务鉴权和环境配置。

- [x] **Step 2: 先写能稳定复现的失败测试，再修改实现并运行相关测试、Ruff、Mypy、TypeScript 和 Lint 门禁**

Expected: 修复前测试失败，修复后目标测试和受影响门禁通过；不修改 PostgreSQL schema。

- [x] **Step 3: 把“Agent 能完成流程但输出质量不佳”记录为非阻断观察项**

Expected: 记录输入、实际输出摘要、期望差距和建议决策，不把主观效果问题伪装成系统故障，也不阻断其他功能验收。

### Task 5: 本地总回归与生产地址验收

**Files:**
- Verify: `.github/workflows/build.yml`
- Verify: `playwright.config.ts`
- Update: `docs/audits/2026-07-14-functional-verification.md`

- [x] **Step 1: 运行本地六流程总回归和静态门禁**

Run:

```powershell
$env:E2E_BASE_URL='http://127.0.0.1:43119'; npm run test:e2e
npm run api:check
npm run test:web
npm run typecheck
npm run lint
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

Expected: 所有门禁通过；Agent 主观效果观察项允许保留但必须已记录。

- [ ] **Step 2: 仅在本地全部通过后对生产地址执行生产感知的六流程**

Run: 使用随机测试账号逐项执行六个主流程；对真实模型输出只断言任务完成、草案边界、消息恢复和计费一致性，不复用仅适用于 `fake` provider 的固定文案与零扣费断言。

Expected: 六个主流程全部通过，生产公网 `/internal/**` 返回 404，测试数据只属于随机测试账号；Agent 输出效果不足单独记录，不阻断协议与状态验收。

- [ ] **Step 3: 核对生产服务健康、数据库结构只读指纹和 GitHub Actions 最新部署状态**

Expected: 五服务 healthy；数据库结构差异为 0；最新 `main` 部署成功。

- [ ] **Step 4: 完成验收审计并提交需要保留的修复和记录**

Expected: 审计逐项列出通过、已修复、Agent 非阻断观察和证据路径；工作树干净且远端 `main` 同步。
