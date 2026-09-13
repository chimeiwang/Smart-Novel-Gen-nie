# 8 月 29 日 LangGraph 写作流程兼容回退

日期：2026-09-13

状态：用户已要求生产回退并确认内容保护边界；兼容实现与验证中，尚未部署。

## 用户目标与授权

用户要求从当前生产版本回退至 2026-08-29 的写作状态，恢复 LangGraph 编排及模型自主读取资料的工具循环，明确包含生产。随后确认：正文和大纲不得受到影响，其他历史兼容不作为阻断，对话历史允许删除。

此授权不解释为清库、账户或账务删除、数据库 DDL rollback，也不要求为了删除而删除。默认保留全部数据；如对话确实阻断回退，只能在备份和精确清单复核后处理对话记录，不级联删除作品、版本、候选、Task、Command 或 V2 审计来源。

## 基线与选择

- 旧版基线：`a37d87373ce9f10ed6c41dca9ff2a74956b76718`，2026-08-29 21:13。
- 兼容底座：`8eabd60b4900c005a608042017d5619d6bc7abd5`，已部署 Java Core 与 Python Agent。
- 生产 `novelwriter` 已为 `migrated-with-v2`；2026-09-13 01:12 UTC 只读核验活动 V2 为 0，三服务健康。
- 原始旧版已在独立分支检出，图、Operation、Runtime 和工具测试 286 项通过；这不是生产兼容验收。

原始旧镜像不认识现有数据库结构。为满足内容保护要求，本次选择兼容回退，而不是数据库倒退：保留 V2-aware Java Core、Python Agent、统一接口契约和持久执行 Redis，恢复 8 月 29 日写作入口；新任务走仍然保留的 V1 LangGraph。

这不是逐文件等同旧提交的整仓发布。未开放的视频功能不在此次恢复范围内，保持关闭；不为恢复旧视频复制已退役接口。新 V2 自然请求、同 Run 澄清不再作为本次默认写作入口，旧对话不要求续跑。

## 实现边界

1. 恢复旧写作会话发送、V1 SSE、审核及恢复交互，并使用当前生成客户端完成类型适配；不手写重复 DTO。
2. 普通输入发送旧 `userMessage/selectedAgents` 请求，选区继续发送显式 Operation；不能向 route-off 的服务发送 V2 `inputMode=natural`。
3. 部署设置 `DURABLE_AGENT_EXECUTION_SCHEMA_READY=true`、`DURABLE_AGENT_EXECUTION_ROUTE_MODE=off`、`V1_FRESH_AGENT_STARTS_ENABLED=true`。先关闭全部 fresh start 并联合排空，再部署，最后开放 V1。
4. 保留旧 V2 查询、取消、回调、用量收尾和来源读取能力；不修改既有 Run 的引擎身份，不删除 execution Redis。
5. 新写作必须实际进入 `parent_graph -> operations.graph -> AgentRuntime`，主 Agent 具有现有只读工具；模型不得直接写数据库或正式正文。
6. 正文和大纲仍走 `proposal -> ReviewArtifact -> 作者确认 -> Core 应用`，不因回退省略确认。
7. 遵循现有原生 CSS、普通段落 Agent 正文和 textarea 编辑器规范，不进行视觉重设计。

### 旧请求幂等兼容修复

隔离 PostgreSQL 回归发现：旧 Web 命令只保存 `userId:clientRequestId` key，不保存新版幂等信封。
统一解析器虽查询到该行，但忽略了无信封记录，导致同请求重放落到会话忙判断。补丁只恢复这类旧 key 的
身份识别，不补造历史请求指纹、不改写旧 payload；新协议使用同 key 时仍不得把旧任务转换成新引擎。

## 数据保护与验收

- 切换前对 `novelwriter` 作完整备份，包含持久 execution 日志；检查归档可读、校验和及备份身份。
- 对正式作品保护表建立按完整序列化行确定性排序的摘要；至少覆盖 `Novel`、`Chapter`、`Outline`、`OutlineNode`，并纳入章节进展、Beat Plan、文档版本及设定相关表。具体生产表名以实际结构核对为准。
- 在独立测试库验证 V1 新任务、真实工具网关读取、待审候选、采用、取消、重启恢复与新旧身份隔离，不使用生产作品作测试写入。
- Web 相关测试、typecheck、lint、build；Agent 图/工具/runtime 测试；Java 路由及接口测试；完整 Maven verify；契约漂移和 Compose 健康检查通过后才发布。
- 上线后重新核对三服务不可变镜像、实际路由、V1 任务引擎及 LangGraph 读取工具证据；正式作品保护表前后摘要一致。
- 测试失败则修复或恢复上一健康应用版本，不恢复旧数据库备份来掩盖失败。

## 明确排除

不执行生产 DDL，不恢复 8 月 29 日数据库，不删正文/大纲/小说归属及其来源链，不更改用户凭据，不启用视频或真实 Seedance，不把本地测试通过或 HTTP 202 当成生产完成。
