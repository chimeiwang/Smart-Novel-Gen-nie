# 工作区性能与前端契约收敛规格

## 状态

- 日期：2026-07-14
- 状态：已批准，待实现
- 范围：工作区首屏、延迟面板、写作会话查询、公共 DTO、SSE 跨语言契约

## 背景

当前工作区 SSR 调用一个聚合接口，串行读取章节、质量检查、计划、设定、大纲、引用和所有文风，再把所有数据一次性发送给浏览器。用户即使只编辑当前章节，也要承担全部面板的数据库和网络成本。

写作会话列表对每个会话分别查询消息数量和最后消息，形成 `2N` 查询。前端还维护了一份手写 `QualityCheckDto` 并通过类型断言适配生成客户端，公共接口变化无法被编译器可靠发现。

## 目标

- 工作区 SSR 首屏只加载页面外壳、小说摘要、章节导航和当前章节编辑所需数据。
- 设定、规划、引用和文风按用户实际打开的面板延迟加载并在当前页面会话中缓存。
- 会话列表使用固定数量的聚合查询，不随会话数线性增加 SQL 次数。
- 公共 HTTP DTO 由 FastAPI/OpenAPI 生成客户端提供；前端不重复声明同名 DTO。
- SSE 等非 OpenAPI 运行时契约至少通过共享跨语言样例约束事件名称和关键载荷。

## 非目标

- 不取消 Next.js SSR，也不把公开 SEO 页面改成纯 SPA。
- 不改变工作区现有视觉布局、PC 优先策略或章节 `textarea` 编辑器。
- 不引入 Tailwind、全局状态库或新的数据库索引。
- 不删除历史 `sync_lore` 快照解析兼容。

## 设计

### 1. 轻量首屏接口

新增公开接口：

```text
GET /api/v1/novels/{novel_id}/workspace/bootstrap?chapterId=...
```

返回：

- 小说基础字段和已应用文风摘要；
- 章节导航摘要；
- 当前章节完整正文、进度、一致性检查和已批准 Beat Plan；
- 当前章节 ID。

bootstrap 不查询角色、物品、地点、势力、术语、故事背景、世界设定、写作圣经、大纲树、剧情进度、参考资料或文风库。

旧 `/workspace` 接口暂时保留为兼容入口并修复用户隔离，但 Web 不再把它作为首屏入口。接口在当前阶段不删除，避免没有迁移窗口的破坏性变更。

### 2. 延迟面板接口

新增三个按职责聚合、仍由 Core 做归属校验的接口：

```text
GET /api/v1/novels/{novel_id}/workspace/lore
GET /api/v1/novels/{novel_id}/workspace/planning
GET /api/v1/novels/{novel_id}/workspace/resources
```

- `lore`：角色及关系/经历、物品、地点、势力、术语。
- `planning`：故事背景、世界设定、写作圣经、文本大纲、大纲节点、剧情进度和故事进展。
- `resources`：参考资料、当前用户文风列表和已应用文风摘要。

前端 `SidebarTabs` 只在首次打开对应分组时请求，成功后缓存；切换章节不重复下载小说级数据。加载中、失败和重试使用现有面板样式与文字状态，不引入新的视觉系统。编辑成功后只刷新受影响分组或局部状态，不能每次都重新加载完整工作区。

### 3. 查询边界

Repository 按响应职责拆分方法，禁止轻量 bootstrap 调用旧的全量 `_load_workspace` 后再丢弃字段。测试使用记录型 session 或 SQL 事件计数证明：

- bootstrap 不执行延迟分组对应的查询；
- 每个延迟分组只执行自身需要的查询；
- 文风分组始终按当前用户过滤。

### 4. 写作会话列表

会话列表使用聚合子查询或窗口函数，一次返回：

- 会话字段；
- `messageCount`；
- 最后一条消息摘要。

消息数量和最后消息不能放在 Python `for record` 循环中逐条查询。会话详情只加载恢复所需的 currentTask、lastTask 和受控消息集合，不扫描无界任务历史。

### 5. 公共 DTO

`QualityCheckDto` 改为从 `@inkforge/api-client` 的 `components["schemas"]` 派生。前端本地 `quality-check.ts` 只保留 UI 定义、展示映射和必要的视图辅助类型，删除重复 DTO schema、转换器和页面里的强制类型断言。

新增或修改上述 FastAPI/Pydantic 响应后运行 `npm run api:generate`，生成文件是 TypeScript HTTP 契约的唯一来源。

### 6. SSE 跨语言契约

Pydantic `AgentEvent` 继续约束跨服务事件信封。对于事件名称和关键载荷，在共享契约包维护可机读样例清单，Python 测试验证 Agent/Core 接受并发布这些样例，TypeScript 测试使用真实 `parseSseEvent` 解析同一份样例。

该清单至少覆盖草案等待确认、Agent 状态、完成、失败、更新构建器和 ReviewArtifact 请求。新增事件必须先更新共享样例，再修改生产代码，避免 Python 与 TypeScript 各自测试但彼此漂移。

## 错误处理

- bootstrap 归属失败继续返回 404；单个延迟面板失败不能清空已经加载的章节正文。
- 延迟请求失败显示可重试中文错误，不把空数组伪装成成功数据。
- 生成客户端检查失败时禁止提交手写类型绕过。
- SSE 样例不一致时测试直接失败，不能静默忽略未知关键事件。

## 测试与验收

- API 测试覆盖四个新接口的认证、归属、响应字段和双用户隔离。
- 查询边界测试证明 bootstrap 不加载三个延迟分组。
- Web 测试证明面板首次打开才请求、同组只请求一次、失败后可重试。
- 会话列表测试用多条会话证明 SQL 次数固定且结果顺序正确。
- 页面不再导入手写公共 `QualityCheckDto` 或使用对应强制断言。
- Python 和 TypeScript 读取同一组 SSE 契约样例并通过。
- `npm run api:generate` 后 `npm run api:check`、Web 测试、类型检查、Lint 和生产构建通过。
