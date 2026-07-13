# Python 三服务功能验收记录

## 验收范围

- 本地服务：Next.js `43119`、Core API `8000`、Agent Service `8001`。
- 本地数据：从最终备份恢复的隔离数据库 `inkforge_acceptance_20260714_001219`。
- 本地队列与短期事件：最终验收使用远程 Redis 隔离库 DB15。
- 模型：本地使用 `fake` provider，只判断协议、状态和数据边界，不评价生成质量。
- PostgreSQL schema：未修改。

## 本地验收结果

### 三服务基线

- Web `/login`：HTTP 200。
- Core `/api/v1/health/ready`：configuration、database、database_schema、redis 均为 `ok`。
- Agent `/internal/v1/health/ready`：model_provider 为 `ok`。

### Playwright 主流程

完整回归命令：

```powershell
$env:E2E_BASE_URL='http://127.0.0.1:43119'
npx playwright test
```

结果：7 passed，包含原 6 条主流程和新增的普通问答恢复回归。

1. 注册、退出并重新登录。
2. 创建小说并自动保存章节。
3. 维护设定、大纲、参考资料和文风画像。
4. 运行质量检查并查看模拟模型零扣费摘要。
5. 生成、恢复并应用待确认正文草案。
6. 丢弃待确认正文草案，正式正文保持不变。
7. 普通问答完成后，刷新并重新进入会话可以恢复用户与 Agent 双方消息。

### 补充产品边界

- `/`、`/login` 未登录可访问；`/dashboard`、`/styles`、`/billing`、`/workspace/*` 未登录均以 307 跳转 `/login`。
- 新增章节顺序为 2；章节正文保存后读取一致，字数为 210。
- 从 drafting 直接完成返回 409；进入 review 后、终检仍 pending 时完成返回 409；一致性终检 completed 后可以完成章节。
- 当前用户与计费摘要返回 200，初始余额为 1000 积分；未登录访问计费摘要返回 401。
- 另一用户读取测试用户的小说、章节、写作会话和任务事件均返回 403。
- 待确认草案重新进入会话后可恢复；应用前正式正文为空。

## 已发现并修复的硬故障

### 1. 写作会话刷新后丢失消息

- 现象：写作任务和草案可以生成，但 `WritingSession.messages` 为空；普通问答完成后也没有 Agent 回复记录。
- 根因：旧 workflow 的可见消息持久化在 Python 迁移时遗漏；Core 只保存任务快照，完成回调也丢弃了 `finalResponse`。
- 修复：Core 在任务启动时原子保存用户消息；恢复任务时保存后续用户消息；完成回调把可见回复写入 `WritingMessage` 并通过 completed SSE 返回；重复回调使用稳定元数据去重。
- 回归：新增会话消息恢复 Playwright 流程；完成回调和恢复消息单元测试完成红绿验证。

### 2. 无大纲小说的普通问答无法运行

- 现象：普通问题在意图分类前读取上下文，因没有章节组大纲返回 409，任务被队列反复重试。
- 根因：写作上下文错误地把“缺少章节组”与“章节组重叠冲突”视为同一种硬错误。
- 修复：没有章节组时返回可选规划上下文；多个章节组同时命中时仍返回 409，保留歧义保护。
- 回归：上下文选择测试和普通问答端到端恢复流程通过。

### 3. 一致性终检完成后章节完成返回 500

- 现象：质量检查已为 completed，但章节从 review 切换到 completed 返回 500。
- 根因：PostgreSQL 列为 `TIMESTAMP WITHOUT TIME ZONE`，仓储写入了带 UTC 时区的 `datetime`，asyncpg 拒绝绑定。
- 修复：统一使用项目的毫秒级无时区 `utc_now()`。
- 回归：章节状态原子测试先失败后通过，25 条章节测试通过；同一隔离数据库真实状态转换成功。

## 环境观察

- 第一次隔离启动因 PowerShell `UriBuilder` 不支持 `redis://`，Core 回退到 `.env.local` 的生产 DB0；本次误写入的 6 个精确测试限流键已删除，随后通过 DB0 为 0、DB15 出现测试键确认隔离生效。
- 本机连接服务器 Redis 时出现过两次 1 秒连接超时，Core 按 fail-closed 规则返回 503；失败请求没有增加限流计数。
- 生产 Core 与 Redis 在同一服务器网络内。该观察不作为产品逻辑故障，但线上验收仍需确认认证流程没有 503。
- 本地 `fake` provider 输出固定文本，无法形成 Agent 文学质量结论；没有把该限制作为阻断项。

## 本地门禁证据

- Python：840 passed，1 skipped；1 条第三方 Starlette/httpx 弃用警告。
- Ruff：通过。
- Mypy：177 个源文件通过。
- API 客户端生成检查：通过。
- Web 与 API 客户端测试：7 条通过。
- TypeScript：通过。
- ESLint：通过。
- Next.js 生产构建：通过。

## 线上验收

待修复提交部署成功后填写。
