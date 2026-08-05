# InkForge 中短篇 CLI

这个 CLI 给本机 Codex 和作者提供中短篇工作室的公开接口。它绕过 Web UI，但不绕过 Core API
登录、作品归属、并发控制、Diff 确认或版本状态机。

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

除登录外，命令都从 stdin 读取一个 UTF-8 JSON 对象，stdout 返回 JSON；`short.agent.watch`
返回 JSONL。例如：

```powershell
'{}' | uv run --package inkforge-cli inkforge auth.whoami
'{"storyLengthProfile":"short_medium"}' |
  uv run --package inkforge-cli inkforge short.list
```

## 写作边界

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
