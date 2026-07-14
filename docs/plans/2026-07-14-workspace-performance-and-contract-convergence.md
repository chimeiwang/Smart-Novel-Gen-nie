# 工作区性能与前端契约收敛实施计划

> **智能体执行要求：** 必须使用 `superpowers:executing-plans`，按任务逐项实施本计划，并使用复选框（`- [ ]`）跟踪进度。

**目标：** 把工作区首屏与延迟面板拆成四个有明确查询边界的接口，消除会话列表 2N 查询，并让 HTTP DTO 与 SSE 事件分别由生成客户端和共享样例约束。

**架构：** Next.js SSR 只请求 bootstrap；客户端按侧栏分组首次打开时请求 lore/planning/resources 并在页面会话内缓存。Core repository 按响应职责拆分查询，旧 `/workspace` 保留兼容。会话摘要通过单条聚合查询返回。HTTP 契约从 FastAPI OpenAPI 生成，SSE 由一份 Python/TypeScript 共读 JSON 样例补齐非 OpenAPI 边界。

**技术栈：** FastAPI、Pydantic v2、SQLAlchemy 2 async、Next.js 16、React 19、原生 CSS、OpenAPI TypeScript、Node test、pytest。

---

### Task 1: 定义四个工作区响应契约和路由

**Files:**
- Modify: `apps/core-api/src/inkforge_core/novels/schemas.py`
- Modify: `apps/core-api/src/inkforge_core/novels/service.py`
- Modify: `apps/core-api/src/inkforge_core/novels/router.py`
- Modify: `apps/core-api/tests/novels/test_novel_api.py`

- [x] **Step 1: 写四个接口的契约失败测试**

分别覆盖认证、小说归属、404 隐藏存在性、`chapterId` 选择和响应字段。接口固定为：

```text
GET /api/v1/novels/{novel_id}/workspace/bootstrap?chapterId={chapter_id}
GET /api/v1/novels/{novel_id}/workspace/lore
GET /api/v1/novels/{novel_id}/workspace/planning
GET /api/v1/novels/{novel_id}/workspace/resources
```

bootstrap 只包含小说摘要、章节导航、当前章节完整编辑数据和 `currentChapterId`；其他响应严格按规格分组。测试还断言旧 `/workspace` 继续可用。

- [x] **Step 2: 运行测试并确认 RED**

Run: `uv run pytest apps/core-api/tests/novels/test_novel_api.py -q`

Expected: FAIL；新 schema 和路由不存在。

- [x] **Step 3: 新增 Pydantic 契约**

复用现有叶子 DTO，新增顶层：

```python
class WorkspaceBootstrapResponse(ApiSchema):
    novel: WorkspaceNovelDto
    chapters: list[WorkspaceChapter]
    currentChapterId: str | None

class WorkspaceLoreResponse(ApiSchema):
    characters: list[WorkspaceCharacter]
    items: list[WorkspaceItem]
    locations: list[WorkspaceLocation]
    factions: list[WorkspaceFaction]
    glossaries: list[WorkspaceGlossary]

class WorkspacePlanningResponse(ApiSchema):
    storyBackground: StoryBackgroundDto | None
    worldSetting: WorldSettingDto | None
    writingBible: WritingBibleDto | None
    outline: OutlineDto | None
    outlineNodes: list[OutlineNodeDto]
    plotProgress: PlotProgressDto | None

class WorkspaceResourcesResponse(ApiSchema):
    references: list[ReferenceMaterialDto]
    writingStyles: list[WritingStyleDto]
```

不要复制已有 `QualityCheckDto`、章节、文风、引用等叶子定义。

- [x] **Step 4: 扩展 service/router**

service protocol 和实现分别调用 repository 的四个方法。路由顺序保证 `/workspace/{group}` 不被其他动态路由误匹配；全部继续依赖浏览器认证用户。

- [x] **Step 5: 验证 API 层**

Run: `uv run pytest apps/core-api/tests/novels/test_novel_api.py -q`

Run: `uv run ruff check apps/core-api/src/inkforge_core/novels apps/core-api/tests/novels`

Expected: PASS。

### Task 2: 按响应职责拆分 repository 查询

**Files:**
- Modify: `apps/core-api/src/inkforge_core/novels/repository.py`
- Modify: `apps/core-api/tests/novels/test_novel_api.py`

- [x] **Step 1: 写查询边界失败测试**

扩展现有记录型 session，为 SQL 中出现的模型分类计数。断言：

- bootstrap 不查询 Character、Item、Location、Faction、Glossary、StoryBackground、WorldSetting、WritingBible、Outline、OutlineNode、PlotProgress、ReferenceMaterial、RagDocument、WritingStyle；
- lore 只查询角色关系与设定实体；
- planning 只查询规划类表；
- resources 查询引用和当前用户文风，并包含 `WritingStyle.userId == user_id`；
- 不允许新方法先调用 `_load_workspace()` 再丢弃字段。

- [x] **Step 2: 运行测试并确认 RED**

Run: `uv run pytest apps/core-api/tests/novels/test_novel_api.py -q -k "bootstrap or lore or planning or resources or query"`

- [x] **Step 3: 提取共享的小型装配函数**

把章节相关读取抽成 `_load_chapter_workspace()`，角色关系抽成 `_load_lore()`，规划抽成 `_load_planning()`，引用/文风抽成 `_load_resources(session, novel, user_id)`。旧 `_load_workspace()` 组合这些函数，保持兼容响应；新接口只调用对应函数。

每个公开方法都在现有 repeatable-read 只读事务中先 `_require_owner()`，错误归属统一 404。文风归属规则与 P0 修复保持一致。

- [x] **Step 4: 验证查询边界**

Run: `uv run pytest apps/core-api/tests/novels/test_novel_api.py -q`

Expected: PASS；记录型 session 证明 bootstrap 没有延迟分组查询。

- [x] **Step 5: 提交 Core 工作区拆分**

```bash
git add apps/core-api/src/inkforge_core/novels apps/core-api/tests/novels/test_novel_api.py
git commit -m "性能：拆分工作区首屏与延迟查询"
```

### Task 3: 生成客户端并把 SSR 切换到 bootstrap

**Files:**
- Modify: `packages/api-client/src/generated/openapi.ts`
- Modify: `apps/web/src/app/workspace/[novelId]/page.tsx`
- Modify: `apps/web/src/features/workspace/sidebar-tabs.tsx`
- Modify: `apps/web/src/features/workspace/smart-writing-panel.tsx`
- Modify: `apps/web/src/features/workspace/workspace-shell.tsx`

- [x] **Step 1: 生成并检查 OpenAPI 客户端**

Run: `npm run api:generate`

Run: `npm run api:check`

Expected: PASS；生成文件包含四个新路径和顶层响应 schema。禁止手写对应 TypeScript DTO。

- [x] **Step 2: 写 SSR 数据边界测试或静态契约断言**

断言工作区页面只调用 `/workspace/bootstrap`，不再调用旧 `/workspace`，且传给客户端的首屏 props 不含延迟分组数据。

- [x] **Step 3: 切换页面请求**

页面保留 SSR、SEO 和当前 `chapterId` 查询语义，只替换为生成客户端的 bootstrap 路径。现有编辑器仍使用 `textarea`、1.2 秒自动保存和 `countTextLength()`，不改变视觉布局。

- [x] **Step 4: 类型检查**

Run: `npm run typecheck`

Expected: PASS；不得用 `as unknown as` 绕过新生成契约。

### Task 4: 实现侧栏分组的首次按需加载和缓存

**Files:**
- Create: `apps/web/src/features/workspace/deferred-workspace.ts`
- Create: `apps/web/src/features/workspace/__tests__/deferred-workspace.test.ts`
- Modify: `apps/web/src/features/workspace/sidebar-tabs.tsx`
- Modify: `apps/web/src/features/workspace/workspace-shell.tsx`
- Modify: `apps/web/package.json`

- [x] **Step 1: 写状态机失败测试**

将分组映射写成无 React 依赖的可测模块：

```typescript
assert.equal(groupForTab("characters"), "lore");
assert.equal(groupForTab("outline"), "planning");
assert.equal(groupForTab("references"), "resources");
```

测试同组多个 tab 只触发一次请求；失败状态保留错误并允许 retry；成功数据被缓存；一个分组失败不清空 bootstrap 或其他已加载组。

- [x] **Step 2: 运行测试并确认 RED**

在 `apps/web/package.json` 的 test 命令加入 `src/features/workspace/__tests__/*.test.ts` 后运行：

Run: `npm --workspace @inkforge/web test`

Expected: FAIL；延迟加载模块不存在。

- [x] **Step 3: 实现三组独立状态**

每组状态为 `idle/loading/success/error`，缓存请求 Promise 防止快速切 tab 产生重复并发。只有用户首次打开相应 tab 时调用真实 API；retry 清除该组失败状态后重试。错误文案使用现有面板文字样式和简体中文，不引入新 CSS 体系。

- [x] **Step 4: 接入 SidebarTabs**

`SidebarTabs` 不再要求 SSR 一次性传入所有 lore/planning/resources props。加载中、失败、重试只占用面板内容区；编辑成功后局部更新/失效对应组，不重新请求 bootstrap 或无关组。

- [x] **Step 5: 验证 Web 行为**

Run: `npm --workspace @inkforge/web test`

Run: `npm run typecheck && npm run lint`

Expected: PASS。

- [x] **Step 6: 提交 Web 延迟加载**

```bash
git add apps/web/src/app/workspace apps/web/src/features/workspace apps/web/package.json
git commit -m "性能：按需加载工作区侧栏数据"
```

### Task 5: 把写作会话列表从 2N 查询改成固定查询

**Files:**
- Modify: `apps/core-api/src/inkforge_core/writing/repository.py`
- Modify: `apps/core-api/tests/writing/test_sessions.py`

- [x] **Step 1: 写多会话查询计数失败测试**

创建至少 3 个会话、不同数量消息和相同时间戳的边界数据。监听 SQL 执行次数，断言列表查询次数不随会话数增加；同时断言 `messageCount`、最后消息摘要和排序稳定。

- [x] **Step 2: 运行测试并确认 RED**

Run: `uv run pytest apps/core-api/tests/writing/test_sessions.py -q`

Expected: FAIL；当前每条会话分别查询 count 和 last message。

- [x] **Step 3: 用聚合与窗口函数一次返回摘要**

构造消息聚合子查询和 `row_number() over(partition_by=sessionId order_by=createdAt desc, id desc)` 最后消息子查询，再 left join WritingSession。Python `for record` 只做 DTO 映射，不再执行 SQL。

目标 SQL 次数为固定 1 次；若 SQLAlchemy 方言兼容测试需要拆成 2 次批量查询，也必须固定且与 N 无关，并在测试中锁定。

- [x] **Step 4: 验证并提交**

Run: `uv run pytest apps/core-api/tests/writing/test_sessions.py -q`

```bash
git add apps/core-api/src/inkforge_core/writing/repository.py apps/core-api/tests/writing/test_sessions.py
git commit -m "性能：聚合写作会话摘要查询"
```

### Task 6: 删除手写 QualityCheckDto 重复契约

**Files:**
- Modify: `apps/web/src/shared/contracts/quality-check.ts`
- Modify: `apps/web/src/app/workspace/[novelId]/page.tsx`
- Modify: `apps/web/src/features/workspace/*.tsx`
- Modify: `apps/web/src/shared/contracts/__tests__/quality-check.test.ts`

- [x] **Step 1: 写类型来源检查**

本地文件导入生成客户端并派生：

```typescript
import type { components } from "@inkforge/api-client";
export type QualityCheckDto = components["schemas"]["QualityCheckDto"];
```

测试/静态搜索断言不再存在同名 Zod DTO schema、手工 converter 或页面强制断言。

- [x] **Step 2: 删除重复转换层**

保留 UI 标签、颜色和展示辅助函数；删除公共字段的第二份定义。修正调用点直接接受生成类型，不使用 `as QualityCheckDto`。

- [x] **Step 3: 验证**

Run: `npm --workspace @inkforge/web test`

Run: `npm run api:check && npm run typecheck && npm run lint`

Expected: PASS。

### Task 7: 用同一份样例锁定 Python/TypeScript SSE 契约

**Files:**
- Create: `packages/service-contracts/contracts/writing-sse-events.json`
- Create: `packages/service-contracts/tests/test_writing_sse_examples.py`
- Modify: `packages/api-client/src/__tests__/sse.test.ts`
- Modify: `packages/api-client/package.json`

- [x] **Step 1: 新增共享机器可读样例**

样例至少包含：`artifact_awaiting_user_approval`、Agent 状态、完成、失败、更新构建器、ReviewArtifact 请求。每条包含 SSE event 名称和完整 Pydantic `AgentEvent` 信封，ID/序号保持稳定且载荷使用真实字段名。

- [x] **Step 2: 写双语言失败测试**

Python 读取 JSON 并逐条 `AgentEvent.model_validate()`，同时验证 Core 接受的事件名。TypeScript 从同一路径读取 JSON，把信封 `data` 交给真实 `parseSseEvent`，断言解析后的关键字段。

- [x] **Step 3: 运行测试并确认 RED**

Run: `uv run pytest packages/service-contracts/tests/test_writing_sse_examples.py -q`

Run: `npm --workspace @inkforge/api-client test`

- [x] **Step 4: 只修正生产解析器的真实漂移**

如果共享样例暴露事件名或载荷漂移，先以 Pydantic/现有 Core 发布契约为权威修正 TypeScript；不得为了让测试通过忽略未知关键事件。

- [x] **Step 5: 验证并提交契约收敛**

Run: `uv run pytest packages/service-contracts/tests/test_writing_sse_examples.py apps/core-api/tests/writing/test_sse.py -q`

Run: `npm --workspace @inkforge/api-client test`

```bash
git add packages/service-contracts/contracts/writing-sse-events.json packages/service-contracts/tests/test_writing_sse_examples.py packages/api-client/src packages/api-client/package.json apps/web/src/shared/contracts/quality-check.ts apps/web/src/app/workspace apps/web/src/features/workspace
git commit -m "重构：收敛 HTTP 与 SSE 前端契约"
```

### Task 8: 工作区性能与契约全量验证

**Files:**
- Verify only

- [ ] **Step 1: API 与契约**

Run: `npm run api:generate && npm run api:check`

Run: `uv run pytest apps/core-api/tests/novels apps/core-api/tests/writing/test_sessions.py packages/service-contracts/tests/test_writing_sse_examples.py -q`

- [ ] **Step 2: 前端质量门**

Run: `npm --workspace @inkforge/web test`

Run: `npm --workspace @inkforge/api-client test`

Run: `npm run typecheck && npm run lint && npm run build`

- [ ] **Step 3: Python 质量门**

Run: `uv run ruff check .`

Run: `uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src`

Expected: 全部 PASS，页面视觉、SSR、textarea 和自动保存规则不变。
