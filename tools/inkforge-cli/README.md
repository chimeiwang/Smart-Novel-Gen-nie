# InkForge CLI

这个 CLI 给本机 Codex 和作者提供中短篇工作室与长篇服务端控制台的公开接口。它绕过 Web UI，
但不绕过 Core API 登录、作品归属、并发控制、ReviewArtifact、Diff 确认或版本状态机。

## 本地启动

在仓库根目录执行：

```powershell
uv sync --frozen --all-packages --group dev
uv run --package inkforge-cli inkforge auth.login `
  --origin http://127.0.0.1:8000 `
  --username <用户名>
```

`auth.login` 是唯一交互命令。密码只从真实 TTY 隐藏读取；登录会话写入 Windows Credential
Manager，不写入仓库、普通配置、stdout 或日志。远程 Core 默认只允许 HTTPS，本地 HTTP 只允许
回环地址。已明确接受风险的受控 wrapper 可以把
`INKFORGE_CLI_ALLOW_INSECURE_HTTP_ORIGIN` 设置为一个完整 HTTP origin；该放行只匹配这个地址，
不得使用通配值。

除登录外，命令都从 stdin 读取一个 UTF-8 JSON 对象，stdout 返回 JSON；`short.agent.watch` 和
`long.task.watch` 返回 JSONL。例如：

```powershell
'{}' | uv run --package inkforge-cli inkforge auth.whoami
'{}' |
  uv run --package inkforge-cli inkforge short.list
'{}' |
  uv run --package inkforge-cli inkforge long.novel.list
```

## 中短篇写作边界

- `short.pull` 导出完整 `outline.md`、`manuscript.txt` 和 manifest。
- `short.draft.save` 只保存可编辑工作稿，不创建版本。
- `short.version.submit`、`short.version.adopt`、`short.version.restore` 必须先取得完整 Diff，并
  提交用户确认过的同一 `confirmationHash`。
- Agent 只接受 `outline`、`manuscript`、`selection`、`full_check` 四种操作。文档操作只产生
  候选版本，不自动采用；全文检查只产生报告。
- 启动 Agent、提交、采用和恢复都必须携带 `short.pull` 生成的 `manifestPath`；本地快照
  dirty 时 CLI 直接拒绝。选区修改只发送权威基础版本、Unicode 码点范围和选区哈希，正文由
  Core 读取。

Codex 的完整操作规程位于用户 Skill：
`C:\Users\niebo\.codex\skills\inkforge-short-story-operator\SKILL.md`。

## 长篇写作边界

- 长篇命令只通过 `/api/v1/**` 访问 Core，不连接数据库、Agent Service 或内部接口。
- 小说、章节、任务、草案和质量状态始终以 Core 为权威；CLI 不创建 manifest、dirty 标志、本地章节
  镜像或任务账本。
- `long.novel.list` 固定查询 `long_serial`；调用方不能覆盖篇幅过滤条件。
- 普通查询默认完整内联返回。显式提供 `outputFile` 时，章节正文写为原始 UTF-8 文本，其余查询写为
  完整 JSON；不会按大小自动截断或切换输出形式。
- 人工章节保存使用 `expectedUpdatedAt` 做并发检查。Agent 产物只能通过 ReviewArtifact 的
  approve、revise 或 discard 流程处理，不能直接写入正式内容。
- `long.task.watch` 只观察权威 `outcome`，停止 watcher 不会取消服务端任务；真正取消必须显式执行
  `long.task.cancel`。
- 大纲节点、伏笔、设定、参考资料和文风的结构化写命令仍未开放，不能用现有读接口或批量请求绕过
  幂等、CAS 和来源绑定门槛。

## 命令清单

以下标记区由注册表测试精确校验。每行都是已注册的具体命令，不接受前缀通配。

<!-- command-list:start -->
```text
auth.login
auth.logout
auth.whoami
short.list
short.create
short.pull
short.draft.save
short.version.preview
short.version.submit
short.version.list
short.version.diff
short.version.get
short.version.adopt
short.version.restore
short.agent.start
short.agent.watch
long.novel.list
long.novel.get
long.chapter.list
long.chapter.get
long.session.list
long.session.get
long.planning.get
long.lore.get
long.resources.get
long.outline-node.list
long.foreshadowing.list
long.task.list
long.task.get
long.task.watch
long.artifact.list
long.artifact.get
long.quality.get
long.chapter.save
long.chapter.status
long.chapter.progress.save
long.agent.start
long.task.resume
long.task.cancel
long.artifact.approve
long.artifact.revise
long.artifact.discard
long.quality.run
long.quality.skip
long.quality.reset
```
<!-- command-list:end -->
