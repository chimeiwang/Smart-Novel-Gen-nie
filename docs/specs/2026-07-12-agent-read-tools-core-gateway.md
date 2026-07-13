# Agent 读取工具 Core 网关补齐规格

## 目标

- 让 Agent Service 已声明的 26 个读取工具全部由 Core API 提供可调用实现。
- 保持 Agent Service 不连接 PostgreSQL，所有业务数据读取继续经过 Core API。
- 统一 Agent 与 Core 的工具名称和参数契约，修复同名工具参数不一致导致的 404 或 422。
- 所有读取都校验当前用户、小说和写作任务绑定，不允许跨任务或跨用户读取。

## 非目标

- 不修改 PostgreSQL schema、迁移或现有数据。
- 不新增 Agent 工具，不调整 Agent 能力白名单，不恢复已删除的同步设定流程。
- 不在本轮启用跨服务草案 patch，也不重做写作编排。
- 不引入长期缓存或新的基础设施依赖。

## 设计

Core API 新增统一的 `WritingReadToolService`，以 Agent Service 中的 Pydantic 参数模型为外部契约。服务按工具名称分派读取逻辑，并复用现有仓储：

- 小说、角色、势力、地点、物品、术语、章节、文风和基础大纲信息从当前小说工作区投影。
- 大纲节点和伏笔使用现有大纲仓储返回的结构化数据。
- 参考资料语义检索由 Agent Service 复用现有 embedding 客户端生成查询向量，再调用 Core 的 `ReferenceService.search()`；未配置 embedding 时明确返回未启用，不降级为伪语义字符串匹配。
- 草案详情和当前活跃草案使用 `ReviewRepository`，并额外校验草案属于当前小说和任务。
- 草案列表由 Review 仓储提供当前任务范围内的只读查询，不从工作区或历史消息推断。

Core 工具网关注册全部 26 个读取工具。所有参数使用 Agent 契约中的原始字段名，包括 `artifact_id`、`character_name`、`topK` 等；未知参数和缺失必填参数返回明确的 422 错误。

第一阶段不建立跨请求长期缓存。单次工具调用优先复用仓储现有聚合能力，避免引入缓存一致性问题；若实测同一 Agent run 的重复聚合成为瓶颈，再单独增加带短 TTL 和写入失效规则的缓存。

## 影响范围

- `apps/core-api/src/inkforge_core/writing/`：新增读取工具服务与参数校验。
- `apps/core-api/src/inkforge_core/app.py`：装配服务并注册 26 个读取工具。
- `apps/core-api/src/inkforge_core/reviews/repository.py`：补充当前任务草案列表读取能力。
- `apps/core-api/tests/writing/`：补充工具名称、参数、权限和关键结果测试。
- `apps/agent-service/tests/`：增加 Agent 契约与 Core 注册清单一致性检查；不改变 Agent 运行时。

## 错误处理

- 工具不存在：`TOOL_NOT_FOUND`。
- 参数无效：返回 422，并使用稳定的工具参数错误码。
- 资源不属于当前用户、小说或任务：返回 403。
- 按名称或标识查找不到资源：返回 404，不返回其他小说的候选数据。
- 参考资料检索依赖不可用时，沿用现有 Reference Service 的错误，不伪造空成功结果。

## 验收标准

1. Core 注册名称完整覆盖 Agent Service 的 26 个读取工具。
2. 26 个工具接受的参数字段与 Agent Pydantic 契约一致，`get_review_artifact` 使用 `artifact_id`。
3. 网关执行前继续校验用户、小说、任务绑定和 Agent 权限。
4. 角色、设定、大纲、章节、文风、参考资料和草案的代表性工具能返回完整结构化结果。
5. 草案读取不能跨任务，小说数据不能跨用户。
6. Python 相关测试、Ruff、Mypy 和 `git diff --check` 通过。
