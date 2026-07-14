# Python 三服务迁移与功能验收记录

## 验收范围

- 本地服务：Next.js `43119`、Core API `8000`、Agent Service `8001`。
- 本地数据：生产数据备份的隔离克隆库 `inkforge_local_20260713232736`；生产数据库未执行本轮迁移。
- 队列与短期事件：远程 Redis 的测试专用 DB15；生产 DB0 未清理、未写入验收键。
- 模型：本地使用 `fake` provider，只验证协议、状态、权限和正式数据边界，不评价文学质量。
- PostgreSQL schema：仅在隔离克隆库执行用户批准的单次版本化迁移，新增持久命令、文风归属和单节画像字段。

## 当前迁移结果

### 持久化写作命令

- 写作启动、普通恢复和草案决定先写入 PostgreSQL `WritingRunCommand`，再由 dispatcher 投递 Redis。
- clientRequestId 形成用户级幂等键；同一任务同一时刻只允许一条 pending、submitted 或 processing 命令。
- dispatcher 使用命令 ID 作为稳定 job ID，支持到期命令领取、退避重试和 Core 重启后补投。
- 旧任务对账器只处理没有活动命令的 active 或 waiting_call，不重新打开 awaiting_user_review。
- 完成、失败和等待用户确认回调会结束对应命令；终态数据库事务提交后才追加 SSE 终态事件。

### 草案决定与恢复

- `POST /api/v1/review-artifacts/{artifactId}/decision` 是前端唯一草案决定入口，成功返回 202。
- Core 在同一外层事务中完成正式数据写入或草案删除/返工，并创建 `artifact_decision` 命令；任一步失败整体回滚。
- 前端不再先决定再调用 resume，只连接返回 taskId 的 SSE。
- Agent 持久恢复只推进图状态，不重复应用或删除已由 Core 处理的草案。
- 已应用或已删除草案只有在存在匹配的活动决定命令时，才允许稳定快照继续恢复；其他不一致仍返回 409。

### SSE 与前端状态

- 前端按 taskId 保存 Last-Event-ID，断线重连可继续消费缺失事件并忽略重复序号。
- `agent_start` 现在发送合法的 agentId 和 agentName；前端拒绝不符合共享 Zod 契约的 SSE 载荷。
- 草案应用、丢弃和普通问答都以持久任务终态为准；测试使用轮询等待异步终态，不以正式正文先写入替代任务完成。
- Playwright 监听 React 控制台，写作主流程没有 `unique key` 或同类列表 key 警告。

### 私有文风与单节画像

- `WritingStyle.userId` 非空并外键到 User；文风、参考资料、画像任务、编辑、应用和删除全部按当前用户过滤。
- 旧文风、文风参考和画像任务按已批准方案在迁移中清空；用户、小说、章节、会话和其他正式数据保留。
- `StylePortraitTask.section` 区分整套任务和单节任务。
- 单节入口只调用目标维度，成功回调只更新目标字段，其他四个画像字段保持不变。

## 本地端到端结果

完整回归命令：

```powershell
$env:E2E_BASE_URL='http://127.0.0.1:43119'
npx playwright test --reporter=line
```

结果：`7 passed (2.0m)`。

1. 注册、退出并重新登录。
2. 维护设定、大纲、参考资料和文风画像。
3. 创建小说并自动保存章节。
4. 运行质量检查并查看 fake provider 零扣费摘要。
5. 生成、刷新恢复并应用待确认正文草案，任务最终 completed。
6. 丢弃待确认正文草案，正式正文保持不变，任务最终 completed。
7. 普通问答完成后，刷新并重新进入会话可恢复用户与 Agent 双方消息。

全量执行前发现 DB15 累积注册限流键，页面明确返回“请求过于频繁”；清空测试专用 DB15 后从头执行并全部通过。一次 7 分钟工具窗口造成 Playwright 输出管道 EPIPE，该次结果作废；延长工具窗口后获得上述有效结果。

## 冷启动与恢复证据

- 停止三服务并完成生产构建后，重新启动 Next.js、Core API 和 Agent Service；`/login`、Core ready、Agent ready 均返回 200。
- 冷启动前：awaiting_user_review 任务 26，活动命令 0。
- 冷启动并等待 dispatcher/对账器运行后：awaiting_user_review 任务仍为 26，活动命令仍为 0；无决定草案没有被重新投递。
- 远程 Redis 是共享服务器，本地验收没有重启 Redis 进程，只重置 DB15。pending 命令补投、稳定 job ID、终态不重开和 Redis 丢失对账由 dispatcher、reconciler 和队列自动化测试覆盖。
- 全量验收结束后已停止本地三服务，并把 Redis DB15 从 25 个测试键清理为 0；隔离克隆数据库暂时保留到生产迁移完成，便于复核结构和回归证据。

## 已发现并修复的硬故障

### 草案批准或丢弃后任务无法完成

- 现象：正式正文已经应用，但任务仍停在 awaiting_user_review；丢弃后待确认数量不归零。
- 根因：Core 已事务性应用或删除草案，Agent 获取上下文时仍把终态或已删除草案判为快照冲突；通过后又会重复调用 apply/discard。
- 修复：仅在匹配活动决定命令存在时允许终态草案快照恢复；Agent 的持久决定分支只更新图状态，不重复正式写入。
- 回归：应用、丢弃和普通问答三条 Playwright 流程通过，相关 Core/Agent 单元测试通过。

### React 列表 key 警告

- 现象：写作 Agent 活动卡片显示 `undefined正在接手...`，控制台报告列表缺少唯一 key。
- 根因：Agent 发送的 agent_start 只有 phase；前端解析失败后又强制类型转换，绕过共享契约。
- 修复：后端发送 `agentId=写作`、`agentName=作家`；前端删除未使用的 host_intent 兼容旁路，只处理契约校验成功的事件。
- 回归：SSE 契约测试和 Playwright 控制台断言通过。

### 写作会话消息与上下文历史问题

- 用户消息在启动/恢复时持久化，完成回调保存可见 Agent 回复并按稳定元数据去重。
- 没有章节组时允许普通问答继续；多个章节组同时命中仍返回 409，保留歧义保护。
- 章节完成时间统一使用数据库兼容的无时区 UTC 时间。

## 全量门禁证据

- API 客户端生成与 `npm run api:check`：通过。
- Web 测试：56 passed；API client 测试：2 passed。
- TypeScript：通过。
- ESLint：通过。
- Next.js 生产构建：通过，7 个动态页面路由生成成功。
- Python：872 passed，1 skipped；1 条第三方 Starlette/httpx 弃用警告。
- Ruff：通过。
- Mypy：182 个源码文件通过。
- Playwright：7 passed。

## 未完成的生产步骤

- 尚未对生产 PostgreSQL 和 uploads 生成本轮可恢复备份。
- 尚未在生产执行 `20260714_durable_writing_private_styles.sql`。
- 尚未推送本轮提交，因此 GitHub Actions、镜像发布、SSH 部署和线上感知验收仍待执行。
- 线上浏览器验收必须使用有效 HTTPS；若服务器仍只有 HTTP，secure cookie 会阻断登录，应记录为环境阻塞而不是伪造通过。

## 质量边界

本地 fake provider 输出是固定文本，只能证明调用、状态、权限、SSE 和正式数据边界正确。真实模型的文学质量、画像质量和 token 计费必须在线上真实 provider 环境另行观察，不能把本次 fake 结果记作质量通过。
