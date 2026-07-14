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
- 全量验收结束后已停止本地三服务，并把 Redis DB15 从 25 个测试键清理为 0；生产部署稳定后已确认当前生产库为 `novelwriter`，并删除本次精确隔离克隆库 `inkforge_local_20260713232736`。

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

## 生产备份与迁移证据

- 服务器预检：PostgreSQL 14.23、Docker Compose v5.1.4、git 和 sha256sum 可用；磁盘剩余 18GB；迁移前五个容器均健康。
- 在线备份：`/srv/backups/inkforge/inkforge-20260714T070657Z`，数据库和 uploads 校验通过。
- 停止 Nginx、Web、Core API 和 Agent Service 后生成最终备份：`/srv/backups/inkforge/inkforge-20260714T071148Z`。
- 最终数据库 dump：4,588,995 字节，SHA-256 `04323d390f5dbefdb85fd4c5cb20f95ceec3aa8823e173db3c92b9e392aca1c8`。
- 最终 uploads 归档：104 字节，SHA-256 `413a5196207b06999bdb810db3cc33f161ef4c493b5527eadeefc65c601ea586`。
- `sha256sum --check`、`pg_restore --list` 和 `tar -tzf` 均通过。
- 迁移前：用户 12、小说 37、章节 41、写作会话 140、旧文风 7、文风参考 5、画像任务 5、已应用文风小说 0。
- 版本化 SQL 在一个事务中成功提交：旧文风三表清零，`WritingRunCommand`、`WritingStyle.userId`、`StylePortraitTask.section` 和活动命令唯一索引已创建。
- 迁移后：用户 12、小说 37、章节 41、写作会话 140 保持不变；文风、参考和画像任务均为 0；新命令表初始为 0。
- 本地新代码对生产数据库执行只读 schema guard：ready=true，fingerprint=`760609cdfc0b99fb0a57ecf94c292f06cddfc824694458cb2b95feaecbf39be4`，diffs=0。

## 生产部署与线上感知结果

- 推送提交：`ab8e81fa9a005c519c973da7714ef28dd1c0dbdc`。
- GitHub Actions：[CI and Deploy #37](https://github.com/chimeiwang/Smart-Novel-Gen-nie/actions/runs/29313903737)；ci 和 deploy 均为 success。
- 服务器仓库 HEAD 与部署提交一致；Web、Core API、Agent Service 三张镜像标签均为完整提交 SHA。
- Nginx、Web、Core API、Agent Service、Redis 五个容器全部 running/healthy。
- Core ready：configuration、database、database_schema、redis 均为 ok。
- Agent ready：model_provider、run_queue、service_auth、core_client、queue_consumer 均为 ok。
- 公网 `/login` 返回 200；公网 `/internal/v1/health/ready` 返回 404，内部边界未暴露。
- 生产数据复核：用户 12、小说 37、章节 41、写作会话 140、文风 0、命令 0。

### 环境阻塞

- 服务器仅开放 HTTP 80，HTTPS 443 未开放；生产 secure cookie 无法在当前公网入口完成可靠浏览器登录。
- 按验收约定停止在线写入型测试，没有在线创建账号、私有文风、单节画像或真实模型写作任务。
- 双用户隔离、真实单节更新和草案批准/丢弃已在隔离环境与自动化测试通过；真实 provider 的文学质量和实际 token 计费仍未在线验证。

## 质量边界

本地 fake provider 输出是固定文本，只能证明调用、状态、权限、SSE 和正式数据边界正确。真实模型的文学质量、画像质量和 token 计费必须在线上真实 provider 环境另行观察，不能把本次 fake 结果记作质量通过。
