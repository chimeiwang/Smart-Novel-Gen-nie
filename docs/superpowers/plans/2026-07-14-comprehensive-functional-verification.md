# InkForge 全面功能验收实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在隔离数据库、Redis DB15 和 fake 模型环境中，对当前权威需求、7 个页面入口和 93 个公开 API 操作完成分层验收，修复硬故障并单独记录不阻断的 Agent 效果问题。

**Architecture:** 先以当前代码、`schema-contract.json`、`docs/requirements/00-overview.md` 至 `05-auth-billing-and-ops.md` 和运行时 OpenAPI 为功能事实来源，再组合浏览器主流程、真实 Core API 调用、Python 契约测试和服务重启恢复验证。所有业务数据写入隔离克隆数据库，Redis 使用 DB15，模型使用 fake provider；仅执行用户批准的单次版本化 schema 迁移，不把固定 fake 输出当成文学质量证据。

**Tech Stack:** Next.js 16、FastAPI、PostgreSQL 14、Redis、LangGraph、Playwright CLI、Playwright Test、pytest、Ruff、Mypy、PowerShell。

---

### Task 1: 固化验收环境与功能清单

**Files:**
- Read: `DOCS.md`
- Read: `docs/requirements/00-overview.md`
- Read: `docs/requirements/01-projects-and-chapters.md`
- Read: `docs/requirements/02-creative-knowledge-base.md`
- Read: `docs/requirements/03-ai-writing-and-agents.md`
- Read: `docs/requirements/04-review-quality-and-workflow.md`
- Read: `docs/requirements/05-auth-billing-and-ops.md`
- Read: `apps/agent-service/AGENTS.md`
- Update: `docs/audits/2026-07-14-functional-verification.md`

- [x] **Step 1: 验证三服务与隔离配置**

Run:

```powershell
Get-NetTCPConnection -State Listen | Where-Object LocalPort -in 43119,8000,8001
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health/ready
Invoke-RestMethod http://127.0.0.1:8001/internal/v1/health/ready
```

Expected: 三端口监听；Core 的 configuration、database、database_schema、redis 为 `ok`；Agent 的 model_provider 为 `ok`；运行覆盖使用临时数据库、Redis DB15 和 fake provider。

- [x] **Step 2: 固化页面、OpenAPI 与测试清单**

Run:

```powershell
rg --files apps/web/src/app | Where-Object { $_ -match '(page|route)\.(tsx|ts)$' }
Invoke-RestMethod http://127.0.0.1:8000/api/v1/openapi.json
.\.venv\Scripts\python.exe -m pytest --collect-only -q
```

Expected: 7 个页面入口、93 个公开 API 操作和全部 Python 测试均进入验收映射，不以现有 7 条 E2E 代替完整覆盖。

### Task 2: 公开页面、认证、计费与页面守卫

**Files:**
- Verify: `apps/web/src/app/page.tsx`
- Verify: `apps/web/src/app/login/page.tsx`
- Verify: `apps/web/src/app/dashboard/page.tsx`
- Verify: `apps/web/src/app/billing/page.tsx`
- Verify: `apps/web/src/proxy.ts`
- Verify: `apps/core-api/src/inkforge_core/auth/router.py`
- Verify: `apps/core-api/src/inkforge_core/billing/router.py`

- [x] **Step 1: 验证公开页面和未登录守卫**

Expected: `/`、`/login` 返回 200；`/dashboard`、`/styles`、`/billing`、`/workspace/*` 和 `/debug/workflow-events` 未登录跳转 `/login`。

- [x] **Step 2: 验证注册、重复注册、错误密码、退出、重新登录和当前用户**

Expected: 合法注册为 201 并得到 1000 积分；重复用户名为 409；错误密码使用统一 401；退出清除会话；同一账号可重新登录；`/auth/me` 与浏览器用户名一致。

- [x] **Step 3: 验证用户名、密码和限流边界**

Expected: 用户名输入先 trim/casefold，再按 3 至 32 位小写规则校验和存储；不符合规范的用户名、短密码和确认密码不一致被拒绝；失败请求不会创建用户；Redis 不可用时认证按 fail-closed 返回 503 且不误记成功。

- [x] **Step 4: 验证计费摘要和使用记录**

Expected: 新用户余额为 1000；fake provider 运行不扣费；usage 返回 `totalUsage` 与 `monthlyUsage` 聚合且 token 初始为 0；未登录返回 401；重复完成回调的幂等性由对应 Python 测试证明。

### Task 3: 小说、章节、自动保存和状态机

**Files:**
- Verify: `apps/web/src/app/dashboard/page.tsx`
- Verify: `apps/web/src/app/workspace/[novelId]/page.tsx`
- Verify: `apps/core-api/src/inkforge_core/novels/router.py`
- Verify: `apps/core-api/src/inkforge_core/chapters/router.py`
- Verify: `apps/core-api/src/inkforge_core/quality/router.py`

- [x] **Step 1: 验证小说创建和默认数据**

Expected: 空名称被拒绝；合法小说自动创建第一章、空文本总纲、默认剧情进度和篇幅 Profile；dashboard 按更新时间倒序显示。

- [x] **Step 2: 验证章节新增、标题兜底、正文自动保存和字数**

Expected: 新章节 order 递增；空标题保存为“未命名章节”；1.2 秒自动保存后刷新仍保留；去空白章节字数和小说总字数正确。

- [x] **Step 3: 验证章节进展和默认章节选择**

Expected: ChapterProgress 不存在时创建、存在时更新；URL chapterId 优先，其次最后 drafting 章节，最后为末章。

- [x] **Step 4: 验证章节状态机和质量门槛**

Expected: drafting 可送审；review 可撤回；终检 pending/running/failed 时禁止 completed；completed 或 skipped 后允许完成；completedAt 写入；完成后可回到 review 或 drafting。

### Task 4: 设定资料 CRUD 与作品级文本

**Files:**
- Verify: `apps/core-api/src/inkforge_core/lore/router.py`
- Verify: `apps/web/src/features/workspace/`

- [x] **Step 1: 对角色、物品、地点、势力、术语执行创建、读取、修改、删除**

Expected: 每种实体的完整字段保存并刷新恢复；删除后列表不再出现；必填字段和非法状态被拒绝。

- [x] **Step 2: 验证角色关系和角色经历**

Expected: 同小说角色可以建立、修改、删除关系和经历；目标角色不存在、跨小说角色、跨小说章节被拒绝。

- [x] **Step 3: 验证故事进展、章节进展、故事背景、世界设定和作品圣经**

Expected: 全部文本和 Profile 字段保存、刷新恢复；storyProgress 超过 30000 字符被明确拒绝而不是截断。

### Task 5: 大纲、剧情进度和伏笔

**Files:**
- Verify: `apps/core-api/src/inkforge_core/outlines/router.py`
- Verify: `apps/core-api/src/inkforge_core/outlines/service.py`

- [x] **Step 1: 验证文本总纲和剧情进度保存**

Expected: Outline.content 与 PlotProgress 四字段可创建、更新并在 workspace 聚合中恢复。

- [x] **Step 2: 验证 stage → plot_unit → chapter_group 三层结构**

Expected: 合法树可创建、修改、排序和按叶到根删除；非法父子类型、孤立子节点、含子节点删除、章节范围不成对、父范围不包含子范围和同级范围重叠均被拒绝。

- [x] **Step 3: 验证伏笔 CRUD 和状态**

Expected: active、paid_off、abandoned 状态可保存；非法状态被拒绝；跨小说操作被拒绝。

### Task 6: 参考资料、RAG 和文风画像

**Files:**
- Verify: `apps/core-api/src/inkforge_core/references/router.py`
- Verify: `apps/core-api/src/inkforge_core/styles/router.py`
- Verify: `apps/web/src/app/styles/page.tsx`

- [x] **Step 1: 验证参考资料 CRUD**

Expected: note、web、book、image、custom 类型可创建和修改；非法类型被拒绝；删除同时清理派生索引。

- [x] **Step 2: 验证 RAG disabled 路径、重建和检索边界**

Expected: 未配置 embedding 时资料仍保存且索引为 disabled；reindex 和 search 返回明确 disabled 结果，不伪装成功；跨用户检索被拒绝。

- [x] **Step 3: 验证文风创建、TXT 上传和文件校验**

Expected: 合法非空 TXT 上传并记录文件名和字数；空文件、非 TXT 和超限文件被拒绝；删除参考资料后不可再用于画像。

- [x] **Step 4: 验证画像生成、分节编辑、分节重生成、应用和删除**

Expected: fake provider 下画像任务到达终态；五类字段和 Markdown 汇总可读取；分节修改持久化；文风可应用和取消应用；被小说使用的文风删除遵循当前业务规则。

### Task 7: 写作会话、Agent 操作、SSE 与 ReviewArtifact

**Files:**
- Verify: `apps/core-api/src/inkforge_core/writing/router.py`
- Verify: `apps/core-api/src/inkforge_core/reviews/router.py`
- Verify: `apps/agent-service/src/inkforge_agents/operations/graph.py`
- Verify: `tests/e2e/writing-artifact.spec.ts`

- [x] **Step 1: 验证会话 CRUD 和消息持久化**

Expected: 会话可创建、列出、改名、读取和删除；用户与 Agent 消息刷新后恢复；删除后不可读取；会话与小说/章节绑定不可跨域。

- [x] **Step 2: 验证普通问答和显式 Agent 路由**

Expected: answer_question 不生成草案；`@设定`、`@剧情`、`@写作`、`@校验`、`@编辑` 映射到合法 Operation；无法识别时回退 answer_question；不再生成 sync_lore。

- [x] **Step 3: 验证草案操作和正式数据边界**

Expected: chapter_draft、outline_draft、beat_plan/beat_plan_draft 和 agent_updates 在 awaiting_user 前不修改正式数据；approve 后写入正确目标；discard 物理删除；revise 继续同一草案；revision_brief 禁止应用；部分 agent_updates 只应用选择项。

- [x] **Step 4: 验证 SSE 顺序、重连和去重**

Expected: start、Agent 过程、草案/完成、done 顺序合法；`Last-Event-ID` 可以重放缺失事件；重复来源事件不重复展示；终态连接收敛并可从会话恢复。

- [x] **Step 5: 验证任务提交失败和进程恢复**

Expected: 队列提交失败不留下伪运行状态；重启 Agent 后非终态任务从稳定快照恢复；Redis 已终态任务不会被强制重新打开；错误图使用失败回调而不是完成回调。

### Task 8: 权限、内部边界、调试与服务恢复

**Files:**
- Verify: `apps/core-api/src/inkforge_core/debug/router.py`
- Verify: `packages/service-auth/`
- Verify: `infra/nginx/nginx.conf`

- [x] **Step 1: 使用第二用户验证全部资源归属**

Expected: 小说、章节、质量检查、角色资料、大纲、伏笔、参考资料、文风、写作会话、任务、事件和草案的跨用户读写均返回 403 或不泄露存在性的 404。

- [x] **Step 2: 验证内部接口认证和防重放**

Expected: 无服务令牌、错误受众、错误摘要、跨任务/跨小说绑定和重复 jti 被拒绝；Agent Service 不接收数据库配置，也无法直接访问数据库。

- [x] **Step 3: 验证调试开关和页面**

Expected: 默认关闭时调试 API 明确拒绝；开启时仍需浏览器认证和资源归属；调试页只显示当前用户运行。

- [x] **Step 4: 验证健康、就绪、重启和持久化**

Expected: Web、Core、Agent 均健康；Core schema 指纹为 ok；重启三服务后新账号、小说、章节、消息和草案仍可恢复。

### Task 9: 全量门禁、故障修复和审计收口

**Files:**
- Modify: 仅修改失败证据指向的实现文件
- Test: 对应 Python 测试或 `tests/e2e/*.spec.ts`
- Update: `docs/audits/2026-07-14-functional-verification.md`

- [x] **Step 1: 运行全部自动化门禁**

Run:

```powershell
$env:E2E_BASE_URL='http://127.0.0.1:43119'; npx playwright test
npm run api:check
npm run test:web
npm run typecheck
npm run lint
npm run build
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy apps/core-api/src apps/agent-service/src packages
```

Expected: 所有门禁通过。若出现硬故障，先增加最小失败回归测试，再修改根因实现并重跑受影响域与全量门禁。

- [x] **Step 2: 单独记录 Agent 效果观察**

Expected: 对真实或 fake 输出明确区分“协议/状态正确”和“文学质量”；能运行但效果不佳记录输入、输出摘要、差距和待用户决策项，不阻断硬功能验收。

- [x] **Step 3: 更新审计并清理隔离资源**

Expected: 审计逐项列出通过、失败、修复、未测原因和证据；关闭临时服务后只删除本次临时数据库和 Redis DB15，原数据库及生产 Redis DB0 不变；工作树只包含明确需要保留的测试、修复和审计改动。

- [x] **Step 4: 本地全部通过后恢复线上验收**

Expected: 仅在有效 HTTPS 入口可用后执行生产感知流程；真实模型输出不使用 fake 固定文案和零扣费断言；公网 `/internal/**` 继续返回 404。
