# 工作区数据新鲜度与 bootstrap 纠偏规格

## 状态

- 日期：2026-07-15
- 状态：已实现
- 范围：延迟面板缓存失效、当前章节计划查询、统一字数规则

## 背景

工作区延迟分组成功后会在页面生命周期内永久缓存。Agent 应用正式草案只执行 `router.refresh()`，同一本小说的 `SidebarTabs` 不会重建，用户仍可能看到变更前的设定、规划或资料。`refresh()` 遇到旧 in-flight 请求还会复用旧请求，旧响应可能覆盖刷新后的数据。

轻量 bootstrap 已只返回当前章节详情，但仍查询全部章节的 approved Beat Plan 和 SceneBeat，只为章节导航构造附加摘要。长篇小说的查询和对象数量仍随章节数增长。

字数展示存在 `.length`、JavaScript `\s` 和 Python `\s` 三套近似规则，BOM 等 Unicode 字符会导致当前章节、故事进展和小说总字数不一致。

## 目标

- 延迟分组支持显式失效；失效后的旧 in-flight 响应不能覆盖新请求。
- Agent 工作流完成后使当前小说的 lore/planning/resources 缓存失效，再由用户打开面板时按需重载。
- bootstrap 只查询当前章节的 approved Beat Plan 与 SceneBeat；旧全量 workspace 保持原有完整摘要。
- 浏览器所有可见字数统一调用 `countTextLength()`；Python 和 PostgreSQL 查询遵循同一“忽略 Unicode 空白与 BOM”规则。

## 非目标

- 不改变工作区布局、引入全局状态库或主动预加载所有面板。
- 不删除旧 `/workspace` 兼容接口。
- 不修改 PostgreSQL schema，不处理备案、TLS 或部署。

## 设计

### 1. 版本化缓存失效

`DeferredWorkspaceLoader` 为每个分组维护 generation。`invalidate(group)` 递增 generation、清除该组缓存并从 `inFlight` 脱离。每个请求捕获启动 generation；只有完成时 generation 仍一致且它仍是当前请求，才允许写入 success/error。旧请求可以自然结束，但结果被忽略。

`refresh(group)` 必须先 invalidate 再创建新请求，不能复用旧 Promise。其他分组缓存不受影响。

### 2. 当前小说失效事件

新增仅浏览器内使用的工作区失效事件，载荷包含 `novelId` 和分组列表。`SidebarTabs` 只响应同一小说事件。智能写作完成时先失效三个延迟分组，再执行 RSC refresh；面板自身保存继续只刷新自己所属分组。

### 3. bootstrap 计划范围

`_load_chapter_workspace()` 显式计算计划查询范围：

- `include_all_details=True`：全部章节，保持旧 workspace 兼容响应；
- `include_all_details=False`：仅 `detail_ids`，即当前章节。

非当前章节导航摘要的 `approvedBeatPlan` 在 bootstrap 中允许为 null；用户切换章节后，新 bootstrap 会返回该章节的完整计划。

### 4. 字数契约

统一规则是去除 Unicode 空白和 `U+FEFF` 后统计剩余 Unicode 字符长度。Web 的故事进展和生成内容展示必须调用 `countTextLength()`。Python `count_text_length()` 显式处理 `U+FEFF`；PostgreSQL 聚合在现有空白替换后再移除 BOM。

## 测试与验收

- 成功缓存 invalidation 后下一次 load 会重新请求。
- refresh 发生在旧请求进行中时会创建第二个请求，旧请求后完成不能覆盖新结果。
- 另一小说的失效事件不影响当前 loader。
- bootstrap 的计划查询范围只包含当前章节，全量 workspace 仍包含全部章节。
- JavaScript 与 Python 测试向量覆盖普通空格、换行、制表符、全角空格、NBSP、BOM 和 NEL，并得到相同计数。
- Web 测试、小说 API 测试、类型检查、Lint、Ruff 和 Mypy 通过。
