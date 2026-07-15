# 工作区数据新鲜度与 bootstrap 纠偏实施计划

> **面向智能体执行者：** 每个行为必须先写失败测试并观察预期失败，再写最小实现。

**目标：** 修复工作区旧缓存、bootstrap 过量计划查询和跨语言字数不一致。

**架构：** 延迟 loader 使用 generation 拒绝旧响应；浏览器事件按 novelId 失效缓存；Repository 按接口模式选择计划查询范围；字数使用统一空白规则。

**技术栈：** TypeScript、React、Python、SQLAlchemy、Node test、pytest。

**状态：** 已完成实现、独立交叉审查和全量验证。

---

### 任务 1：版本化失效延迟缓存

**文件：**

- 修改：`apps/web/src/features/workspace/deferred-workspace.ts`
- 修改：`apps/web/src/features/workspace/__tests__/deferred-workspace.test.ts`

- [ ] 先写失败测试：invalidate 后重新加载；旧 in-flight 晚完成不能覆盖新 refresh；不相关分组保持缓存。
- [ ] 运行该测试文件并确认当前 refresh 复用旧 Promise 或旧结果覆盖。
- [ ] 增加 per-group generation、`invalidate()` 和只允许当前 generation 提交结果的检查。
- [ ] 重跑测试。

### 任务 2：Agent 完成后按小说失效

**文件：**

- 新增：`apps/web/src/features/workspace/workspace-invalidation.ts`
- 修改：`apps/web/src/features/workspace/sidebar-tabs.tsx`
- 修改：`apps/web/src/features/workspace/smart-writing-panel.tsx`
- 新增：`apps/web/src/features/workspace/__tests__/workspace-invalidation.test.ts`

- [ ] 先写失败测试：同 novelId 收到分组列表，其他 novelId 不响应。
- [ ] 实现浏览器 CustomEvent 辅助函数；SidebarTabs 订阅并调用 loader.invalidate，SmartWritingPanel onComplete 失效三个分组后 refresh。
- [ ] 重跑工作区测试。

### 任务 3：bootstrap 只加载当前章节计划

**文件：**

- 修改：`apps/core-api/src/inkforge_core/novels/repository.py`
- 修改：`apps/core-api/tests/novels/test_novel_api.py`

- [ ] 先写失败测试，断言 bootstrap 的计划范围是 detail_ids，全量 workspace 是 chapter_ids。
- [ ] 抽出并使用明确的范围选择辅助函数，把计划与 SceneBeat 查询限制到选择结果。
- [ ] 运行小说 API 定向测试。

### 任务 4：统一字数规则

**文件：**

- 修改：`apps/web/src/features/workspace/sidebar-tabs.tsx`
- 修改：`apps/web/src/features/writing/writing-conversation.tsx`
- 修改：`apps/web/src/features/workspace/__tests__/deferred-workspace.test.ts`
- 修改：`apps/core-api/src/inkforge_core/novels/repository.py`
- 修改：`apps/core-api/tests/novels/test_novel_api.py`

- [ ] 先增加相同 Unicode 测试向量，确认 Python 当前对 BOM 的结果不同。
- [ ] Web 两处展示改用 `countTextLength()`；Python 和 SQL 聚合显式去除 BOM。
- [ ] 运行工作区与小说定向测试。

### 任务 5：验证

- [ ] 运行：

```powershell
npm run test:web
npm run typecheck
npm run lint
uv run pytest apps/core-api/tests/novels/test_novel_api.py -q
uv run ruff check .
uv run mypy apps/core-api/src
```
