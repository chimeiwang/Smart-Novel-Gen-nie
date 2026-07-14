# P0 正确性与隔离修复规格

## 状态

- 日期：2026-07-14
- 状态：已批准，待实现
- 范围：跨用户文风隔离、生产会话密钥、草案事件与稳定快照顺序

## 背景

全仓审查确认了三个会阻断生产发布的问题：

1. 工作区聚合查询没有按 `WritingStyle.userId` 过滤，任意已登录用户都可能看到其他用户的文风名称和画像正文。
2. Core API 强制读取生产 `JWT_SECRET`，但生产 Compose 没有把同一变量注入 Web。Web 会退回历史默认密钥，导致 Core 签发的会话在页面代理层被拒绝。
3. Agent Service 在进入草案等待确认时先保存未来序号的稳定快照，再发送 `artifact_awaiting_user_approval`。进程在两步之间退出后，恢复运行会跳过尚未写入的事件序号。

## 目标

- 工作区、文风列表和已应用文风始终沿关系过滤到当前用户。
- Web 与 Core 在生产环境使用同一个显式配置、长度合格的 HS256 密钥；生产环境不允许退回历史默认密钥。
- 草案等待确认事件先成为 Core 的权威事件，再保存包含最新序号的稳定快照。
- 为三个问题增加能够先失败、修复后通过的回归测试。

## 非目标

- 不修改 PostgreSQL schema。
- 不把当前 HS256 会话改成新的认证协议。
- 不改变 ReviewArtifact 的状态机或用户决定入口。
- 不调整页面视觉设计。

## 设计

### 1. 文风隔离

`NovelRepository` 的工作区查询继续先校验小说所有者。返回可选文风列表时必须增加 `WritingStyle.userId == user_id`；读取 `Novel.appliedStyleId` 时也必须同时验证文风属于同一用户，不能只按主键读取。

保留现有 `/api/v1/novels/{novel_id}/workspace` 兼容入口，但该入口和后续新增的轻量工作区接口都必须遵守相同隔离规则。不存在资源和他人资源继续统一表现为 404，不泄露资源存在性。

### 2. 生产会话密钥

生产 Compose 的 `web.environment` 显式注入：

```yaml
JWT_SECRET: ${JWT_SECRET:?必须配置会话签名密钥}
```

Web 的代理层不再在模块加载时固定一个可能不安全的密钥。它在请求时解析环境变量：

- 生产环境缺少密钥、密钥等于历史默认值或 UTF-8 长度不足 32 字节时明确失败；
- 非生产测试环境可以使用已有测试默认值；
- JWT 算法继续固定为 HS256；
- 不把密钥放入浏览器 bundle 或公开环境变量。

架构测试必须同时证明 Core 与 Web 都接收同一个 Compose 变量，并证明生产配置不存在默认密钥回退。

### 3. 草案事件与快照顺序

当图进入等待用户确认且存在 `activeArtifactId` 时，顺序固定为：

1. 发送 `artifact_awaiting_user_approval`；
2. Core 按连续序号持久化并发布该事件；
3. 保存稳定 checkpoint；
4. checkpoint 的 `eventSequence` 包含 checkpoint 回调自身对应的最新序号；
5. 恢复后下一个事件从最新序号加一开始。

如果进程在事件成功后、checkpoint 成功前退出，队列重试必须依靠稳定 `eventId` 和序号幂等重放该事件，再补写 checkpoint；不能创建重复的用户可见草案入口。如果 checkpoint 已成功，则恢复不能复用旧序号。

## 错误处理

- 文风归属不匹配按 404 处理。
- 生产 Web 密钥配置错误时 readiness 和受保护页面请求必须失败，不能自动采用默认密钥。
- Core 拒绝序号缺口；Agent 重试负责用同一事件身份补齐，而不是绕过检查。

## 测试与验收

- 双用户工作区测试证明用户 A 的响应中不包含用户 B 的文风名称、ID 或 `portraitMarkdown`。
- 已应用文风必须和小说属于同一用户。
- Compose 架构测试证明 Web 和 Core 都使用 `${JWT_SECRET:?...}`。
- Web 单元测试覆盖生产缺失、默认值、短密钥和合法密钥。
- Agent 作业测试断言顺序为“等待确认事件 -> checkpoint”。
- 故障注入测试覆盖事件成功后 checkpoint 失败，再次运行不会产生序号缺口或重复事件。
- 相关 Python、Web、架构测试、Ruff、Mypy、TypeScript、Lint 和生产构建全部通过。
