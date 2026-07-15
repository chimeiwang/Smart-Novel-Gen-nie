# 章节安全保存与质量版本门禁实施计划

> **面向智能体执行者：** 必须按任务执行，并为每个行为先运行会因缺少目标能力而失败的测试，再写最小实现。

**目标：** 防止章节正文静默丢失或逆序覆盖，并保证质量结果只放行其实际检查的正文版本。

**架构：** 浏览器使用单写入协调器和 `updatedAt` 乐观并发；Core 统一正文版本递增和质量失效逻辑；WorkflowRun.input 保存正文快照与 SHA-256，回调按当前正文哈希决定是否能更新公共检查。

**技术栈：** React/TypeScript、Next.js、FastAPI、SQLAlchemy async、OpenAPI、Vitest、pytest。

**状态：** 已完成实现和独立交叉审查；提交前验证除测试 getter 返回类型标注导致的全仓 TypeScript 类型检查失败外均已完成。

---

### 任务 1：章节乐观并发契约

**文件：**

- 修改：`apps/core-api/src/inkforge_core/chapters/schemas.py`
- 修改：`apps/core-api/src/inkforge_core/chapters/service.py`
- 修改：`apps/core-api/src/inkforge_core/chapters/repository.py`
- 测试：`apps/core-api/tests/chapters/test_chapter_api.py`
- 测试：`apps/core-api/tests/chapters/test_atomic_status.py`

- [ ] 先写失败测试：旧 expectedUpdatedAt 覆盖新正文返回 409；相同内容的响应丢失重试幂等成功；review/completed 不能更新正文；旧版本不能送审。
- [ ] 运行章节定向测试，确认现有接口缺少版本字段并会覆盖。
- [ ] 给正文和状态请求增加必填 `expectedUpdatedAt`，状态响应补 `updatedAt`。
- [ ] 锁章后先处理“内容已相同”的幂等重试，再比较版本；不一致抛出 `CHAPTER_VERSION_CONFLICT`。
- [ ] 所有成功写入使用以下单调版本规则：

```python
next_updated_at = max(utc_now(), current_updated_at + timedelta(milliseconds=1))
```

- [ ] 只允许 drafting 更新标题/正文，重跑定向测试。

### 任务 2：统一正文变化与质量失效

**文件：**

- 新增：`apps/core-api/src/inkforge_core/chapters/content_state.py`
- 修改：`apps/core-api/src/inkforge_core/chapters/repository.py`
- 修改：`apps/core-api/src/inkforge_core/reviews/formal_writes.py`
- 测试：`apps/core-api/tests/chapters/test_atomic_status.py`
- 测试：`apps/core-api/tests/reviews/test_artifact_apply.py`

- [ ] 先写失败测试：正文变化清空 completed/skipped/failed 检查和所有评分；仅改标题不失效；ReviewArtifact 覆盖正文后章节退回 drafting。
- [ ] 运行测试确认当前旧检查仍保留。
- [ ] 抽出正文 SHA-256、报告清理和活动 WorkflowRun 取消辅助函数，始终先锁章节再锁检查项。
- [ ] 普通 PATCH 和 formal write 复用同一辅助函数；正文变化把公共检查置 pending、活动 run 置 cancelled/QUALITY_SOURCE_CHANGED。
- [ ] 重跑章节与 ReviewArtifact 测试。

### 任务 3：质量运行保存正文快照

**文件：**

- 修改：`apps/core-api/src/inkforge_core/quality/repository.py`
- 测试：`apps/core-api/tests/quality/test_quality_state.py`

- [ ] 先写失败测试，断言 WorkflowRun.input 包含 `chapterContent`、`chapterContentSha256`、`sourceUpdatedAt`。
- [ ] 先写失败测试：运行创建后正文变化，旧 success/failure 只结算自身运行，公共检查保持 pending。
- [ ] 运行测试确认当前上下文读取实时正文且旧回调会更新公共检查。
- [ ] create_run 保存完整正文快照和哈希；get_run_context 返回快照；complete/fail 回调重新计算当前正文哈希，只有匹配且 latest 才更新公共检查。
- [ ] 重跑质量测试。

### 任务 4：生成公共客户端

**文件：**

- 生成：`packages/api-client/src/generated/schema.d.ts`

- [ ] 运行 `npm run api:generate`。
- [ ] 运行 `npm run api:check`，确认生成客户端与 FastAPI 契约一致。

### 任务 5：实现单写入自动保存协调器

**文件：**

- 新增：`apps/web/src/features/editor/chapter-save-coordinator.ts`
- 新增：`apps/web/src/features/editor/__tests__/chapter-save-coordinator.test.ts`

- [ ] 先写失败测试覆盖 1.2 秒防抖、最多一个请求、请求期间新输入串行补存、flush、失败保留、retry、dispose 和 localStorage 恢复。
- [ ] 运行该测试文件，确认协调器尚不存在而失败。
- [ ] 实现 `update/flush/retry/dispose`，请求函数作为依赖注入；候选快照携带 expectedUpdatedAt，成功响应推进版本。
- [ ] 重跑协调器测试。

### 任务 6：接入编辑器、导航和质量轮询

**文件：**

- 修改：`apps/web/src/features/editor/chapter-editor.tsx`
- 修改：`apps/web/src/features/chapters/chapter-list.tsx`
- 修改：`apps/web/src/app/workspace/[novelId]/page.tsx`
- 测试：`tests/e2e/project-editor.spec.ts`
- 测试：`tests/e2e/quality-billing.spec.ts`

- [ ] 先补组件/E2E 失败测试：快速输入后切章先 flush；送审先 flush；review/completed 只读；保存失败不显示已保存；质量状态自动到终态。
- [ ] 编辑器用协调器替代直接 setTimeout；保存状态和重试按钮使用现有克制样式，不增加新视觉体系。
- [ ] 切章和状态动作 await flush，失败则保持当前页面/状态；pending/running 检查轮询并禁用重复动作。
- [ ] 运行 Web 测试、typecheck 和 lint。

### 任务 7：需求同步与验证

**文件：**

- 修改：`docs/requirements/01-projects-and-chapters.md`
- 修改：`docs/requirements/04-review-quality-and-workflow.md`

- [ ] 写明版本冲突、正文版本门禁、自动保存失败和旧回调验收。
- [ ] 运行：

```powershell
uv run pytest apps/core-api/tests/chapters apps/core-api/tests/quality apps/core-api/tests/reviews/test_artifact_apply.py -q
uv run ruff check .
uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src
npm run api:check
npm run test:web
npm run typecheck
npm run lint
```
