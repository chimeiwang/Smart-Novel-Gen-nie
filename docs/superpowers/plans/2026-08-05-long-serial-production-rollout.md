# 长篇生产发布与操作 Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将已验证的长篇控制面和 CLI 安全发布到生产，创建独立生产长篇操作 Skill，并通过只读与单章写入冒烟证明部署结果，而不是只证明代码已推送。

**Architecture:** 仓库代码通过 `main` 的 GitHub Actions CI/Deploy 发布；个人 Skill 在本机独立安装，固定调用同一仓库 CLI、`production` profile 和 `https://inkforge.cn`，使用显式 policy 授权。中短篇与长篇 Skill 共用生产身份配置和 Credential Manager Cookie，但保持不同业务规则和命令授权；生产发布与冒烟以已批准的 HTTPS 改造完成为前置条件，不回退到公网 IP 明文 HTTP。

**Tech Stack:** Git/GitHub Actions、gh CLI、Docker Compose CI/CD、PowerShell 5.1、Codex personal skills、InkForge CLI、HTTPS Core API

---

## 执行前提

- 控制面、运行安全和 CLI 三份计划的完成门槛全部通过。
- `git rev-parse --verify refs/codex/long-serial-plan-base` 必须成功，且该本地 ref 仍指向总体计划记录的实施起点。
- 当前仓库已批准 `docs/specs/2026-08-05-production-https.md` 与 `docs/plans/2026-08-05-production-https.md`。Task 1 可在 HTTPS 最终验收前同步仓库文档；Task 2–10 开始前必须先完成该 HTTPS 计划 Task 7 的最终验证，确认 `https://inkforge.cn`、Secure Cookie、Compose loopback 绑定和中短篇生产 Skill schema v3 均已生效。
- HTTPS 前置未完成时，只能完成本计划 Task 1，不得迁移或创建生产 Skill、推送生产或进行线上冒烟，也不得回退到 `http://124.71.85.180` 或恢复任何不安全 HTTP 开关。
- 生产 Skill 不登录服务器、不使用 SSH、不直连数据库、Agent Service 或 `/internal/v1/**`。CI/CD 自身的受控部署 SSH 不等同于操作 Skill，仍由现有 GitHub workflow 执行。
- 个人 Skill 目录不属于 InkForge Git 仓库；仓库 push 不会发布这些本机文件。
- 实施 Skill 前必须先读取并使用 `skill-creator` 与 `writing-skills`；如果其规则要求暂停或额外验证，按技能规则执行并在进度更新中说明。

### Task 1：同步架构、写作与审核权威文档

**Files:**

- Modify: `apps/agent-service/AGENTS.md`
- Modify: `docs/requirements/03-ai-writing-and-agents.md`
- Modify: `docs/requirements/04-review-quality-and-workflow.md`
- Modify: `docs/specs/2026-08-05-long-serial-cli-control-plane.md`

- [ ] 记录显式长篇 Operation 只开放 plan/write/review chapter，历史自然语言 classifier 仍兼容。
- [ ] 记录 target/scope/sourceBindings 的稳定快照边界、当前 jobId 写门禁、cancel tombstone 和取消后不发 fail callback。
- [ ] 记录 Artifact expectedRevision、sourceBindingStatus、legacy fail-closed 和统一事务锁序。
- [ ] 记录 CLI 无本地业务状态、watch 与 cancel 分离、Stage C 写命令未开放。
- [ ] 核对规格中的生产入口和生产 Skill 约束保持当前权威事实：唯一 origin 是 `https://inkforge.cn`，依赖 HTTPS 计划完成，不保留公网 IP HTTP 兼容路径。
- [ ] 把规格状态更新为“实现完成/待生产验证”时，必须以测试结果为依据；未通过的条目保持未完成，不写乐观状态。
- [ ] 运行文档术语扫描：

```powershell
rg -n "long_form|long_serial|sourceBindings|jobId|cancelled|expectedRevision" apps/agent-service/AGENTS.md docs/requirements/03-ai-writing-and-agents.md docs/requirements/04-review-quality-and-workflow.md docs/specs/2026-08-05-long-serial-cli-control-plane.md
```

- [ ] 提交：

```powershell
git add apps/agent-service/AGENTS.md docs/requirements/03-ai-writing-and-agents.md docs/requirements/04-review-quality-and-workflow.md docs/specs/2026-08-05-long-serial-cli-control-plane.md
git commit -m "文档：同步长篇 CLI 控制面实现"
```

### Task 2：把中短篇生产授权迁入单一 policy

**Skills:** `skill-creator`、`writing-skills`

**Files outside repository:**

- Create: `C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator\policy.json`
- Modify: `C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator\scripts\operator.ps1`
- Modify: `C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator\references\cli-contract.md`
- Create: `C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator\tests\test-operator.ps1`
- Verify: `C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator\SKILL.md`
- Verify: `C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator\agents\openai.yaml`

- [ ] 先在 `tests/test-operator.ps1` 写不依赖 Pester 的 PowerShell 5.1 测试夹具，使用临时 LOCALAPPDATA、fake uv 与假仓库，精确记录当前 16 条授权命令；迁移前后集合必须完全相等：

```json
{
  "schemaVersion": 1,
  "commands": [
    "auth.login", "auth.whoami", "auth.logout",
    "short.list", "short.create", "short.pull", "short.draft.save",
    "short.version.preview", "short.version.submit", "short.version.list",
    "short.version.get", "short.version.diff", "short.version.adopt",
    "short.version.restore", "short.agent.start", "short.agent.watch"
  ]
}
```

- [ ] `Read-CommandPolicy` 严格拒绝未知顶层字段、schemaVersion 错误、空命令、重复命令、`*`/前缀通配和非数组。
- [ ] 删除 `$script:AllowedCommands`；wrapper 只从与自身相邻的 `policy.json` 读取授权。
- [ ] 以 HTTPS 计划完成后的中短篇生产 Skill schema v3 wrapper 为迁移基线：保持 Read-OperatorConfig、固定 HTTPS origin/profile、whoami 预检、manifest、dirty gate、stdout/stderr 和退出码行为一致；不得重新加入 `acceptedInsecureHttp`、`-AcceptInsecureHttp`、`INKFORGE_CLI_ALLOW_INSECURE_HTTP_ORIGIN` 或相关环境变量恢复分支。
- [ ] 用 CLI registry 的 Python API 校验 policy 每项均已注册；该测试是能力一致性，不把 registry 当生产授权来源。
- [ ] cli-contract 命令代码块与 policy 精确比对，避免文档复制漂移。
- [ ] 运行现有与新增 wrapper 测试，再验证 Skill：

```powershell
python -X utf8 C:\Users\niebo\.codex\skills\.system\skill-creator\scripts\quick_validate.py C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator
```

- [ ] 用 fake uv 验证 `auth.whoami`、`short.list`、`short.agent.watch` 的 JSON/JSONL、Unicode、stderr 和退出码完全透传。
- [ ] 运行离线测试：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator\tests\test-operator.ps1
```

- [ ] 记录这些文件属于本机、不会进入仓库 commit。

### Task 3：创建独立生产长篇操作 Skill

**Skills:** `skill-creator`、`writing-skills`

**Files outside repository:**

- Create: `C:\Users\niebo\.codex\skills\inkforge-production-long-novel-operator\SKILL.md`
- Create: `C:\Users\niebo\.codex\skills\inkforge-production-long-novel-operator\agents\openai.yaml`
- Create: `C:\Users\niebo\.codex\skills\inkforge-production-long-novel-operator\policy.json`
- Create: `C:\Users\niebo\.codex\skills\inkforge-production-long-novel-operator\scripts\operator.ps1`
- Create: `C:\Users\niebo\.codex\skills\inkforge-production-long-novel-operator\scripts\smoke.ps1`
- Create: `C:\Users\niebo\.codex\skills\inkforge-production-long-novel-operator\scripts\watch-process-host.py`
- Create: `C:\Users\niebo\.codex\skills\inkforge-production-long-novel-operator\scripts\watch-cli-child.py`
- Create: `C:\Users\niebo\.codex\skills\inkforge-production-long-novel-operator\scripts\watch-interrupt-probe.py`
- Create: `C:\Users\niebo\.codex\skills\inkforge-production-long-novel-operator\references\cli-contract.md`
- Create: `C:\Users\niebo\.codex\skills\inkforge-production-long-novel-operator\references\recovery.md`
- Create: `C:\Users\niebo\.codex\skills\inkforge-production-long-novel-operator\tests\test-operator.ps1`

- [ ] 使用 skill-creator 提供的初始化/验证脚本生成合法骨架，不手写遗漏 manifest/metadata。
- [ ] Skill description 只触发 production/online/remote/inkforge.cn（并可识别用户沿用的旧 IP 称呼）下的 long_serial 操作，与本地长篇和生产中短篇触发描述不重叠；实际 wrapper 始终只连接 HTTPS 域名。
- [ ] policy 精确包含共享 auth、16 条查询、watch 和安全计划开放的 12 条写命令：

```text
auth.login
auth.whoami
auth.logout
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
long.artifact.list
long.artifact.get
long.quality.get
long.task.watch
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

- [ ] policy 不得出现 Stage C 保留命令和任何通配符。
- [ ] `references/cli-contract.md` 按 CLI 计划 Task 5、7–10 逐命令记录允许/必填字段、query/path 映射和可复制 JSON 示例；测试从文档代码块提取命令名并与 policy/registry 精确比对。`smoke.ps1` 只用这些已测试字段构造 PowerShell hashtable 后 `ConvertTo-Json -Depth 12 -Compress`，不拼接 JSON 字符串。
- [ ] wrapper 固定：

```text
origin  = https://inkforge.cn
profile = production
config  = %LOCALAPPDATA%\InkForge\production-codex-operator\config.json
```

- [ ] 复用 HTTPS 计划落地后的 schema v3 production config（仅 `schemaVersion`、`repositoryRoot`、`expectedUsername`）与 Credential Manager Secure Cookie；不创建第二份 config、登录凭据或 snapshot 目录。
- [ ] 每轮接管先调用 `auth.whoami`；每个业务命令前 wrapper 再执行一次身份预检。auth.login 保持真实 TTY 交互。
- [ ] SKILL.md 明确：一次 start 只启动一个 Operation；没有用户对具体动作的明确授权时，不自动 approve、revise、discard、cancel、quality run/skip/reset 或完成章节。
- [ ] recovery 说明网络结果不确定时保留原 clientRequestId/taskId/artifactId；watch 中断不等于 cancel；401 停止写入并要求真实 TTY 登录。
- [ ] 不加入 SSH、数据库、internal API 或服务器账号说明。
- [ ] `scripts/smoke.ps1` 是可重复验收器，参数固定为 `-Mode ReadOnly|ChapterLoop -OutputDirectory <绝对目录>`，ChapterLoop 另要求 `-NovelId`、`-ChapterId` 和显式 `-ConfirmMutations`。所有 API 调用都经相邻 `operator.ps1`；watcher 中断探针经相邻 `watch-interrupt-probe.py` 启动同一个 operator。脚本捕获每次完整 stdout/stderr/退出码到 OutputDirectory，stdout 自身只返回一个 receipt JSON；没有 `-ConfirmMutations`、ID 为空、作品标题不是 `CLI 长篇验收` 或身份不匹配时在首个写请求前失败。
- [ ] `operator.ps1` 对 `long.task.watch` 走专用 `watch-process-host.py`：外层 PowerShell 用已解析的 uv 和 repositoryRoot 执行 `uv run --directory <repo> --package inkforge-cli python <host>` 取得已安装 inkforge-cli 的仓库 Python 3.12，且整层留在原进程组。host 不再启动第二层 uv，而是用自己的 `sys.executable` 加固定相邻 `watch-cli-child.py` 和固定命令 `long.task.watch` 创建新的内层进程组；child 在导入 CLI 前用 `ctypes.windll.kernel32.SetConsoleCtrlHandler(None, False)` 恢复新进程组默认忽略的 Ctrl+C 处理，失败则在联网前非零退出，然后只执行 `from inkforge_cli.cli import main; raise SystemExit(main())`。host 原样代理 stdin/stdout/stderr，并把 Python child 的 returncode 原样返回给 operator；其他命令不走该 host。
- [ ] operator 只在 `long.task.watch` 且存在私有环境变量 `INKFORGE_WATCH_CONTROL_FILE` 时，把一个已由调用方创建、位于完全限定临时目录中的空控制文件路径传给 host；host 以原子替换写入 `{schemaVersion:1,processGroupId:<Python child pid>}`。该变量和路径不得进入 CLI payload、stdout、policy 或长期配置；非 watch 命令出现该变量时联网前拒绝。
- [ ] `watch-interrupt-probe.py` 启动普通外层 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File <相邻 operator.ps1> long.task.watch`，设置唯一控制文件并把输入 JSON 写入 stdin；观察到首个完整 JSONL snapshot/event 且读到内层 processGroupId 后，仅对该内层组调用 `os.kill(processGroupId, signal.CTRL_C_EVENT)`。外层 PowerShell 不接收控制事件；probe 完整保存 stdout/stderr，要求 10 秒内整条 operator→host→Python CLI 链退出且最终 returncode=130。超时只终止本次精确 PID 树并非零失败，不按进程名清理。
- [ ] ReadOnly 模式依次执行 whoami、novel.list，按标题精确选择作品，再执行 chapter.list 并选择第一章，然后执行 chapter.get、task.list、artifact.list。`checkId` 只在 chapter.get 已有 `qualityChecks` 时读取，否则写 null；写入 `read-only-receipt.json`，至少包含 novelId/chapterId/chapterUpdatedAt/checkId/transcriptDirectory，不把响应缓存当写权限。
- [ ] ChapterLoop 模式从 Core 重新 GET 校验 receipt 中的 IDs，按 Task 9 固定序列执行。每个 start/resume/cancel/decision/quality.run 使用脚本为本轮生成后保持不变的 clientRequestId；每一步从上一份 JSON/JSONL 解析 taskId/artifactId/revision/updatedAt，不从日志文本猜测。脚本写 `chapter-loop-receipt.json`，包含每步命令、ID、outcome、错误 code 和证据文件路径，不含 Cookie/Token/密码。
- [ ] `tests/test-operator.ps1` 使用隔离临时目录和 fake uv，覆盖 policy、固定 HTTPS origin/schema v3 config、whoami 预检、JSON/JSONL/Unicode/stderr/退出码透传及 invalid policy 联网前失败；脚本任何断言失败都以非零退出。
- [ ] 同一测试还覆盖 smoke ReadOnly 的 novel→chapter.list→chapter.get ID 解析、nullable checkId、ChapterLoop 缺 `-ConfirmMutations` 的联网前拒绝、每个请求复用正确 ID、receipt 完整写入，以及 fake uv 返回 401/409/422/5 时停止后续 mutation；离线中断测试跑 operator→watch-process-host→Python 夹具 child 的真实进程边界，断言 PowerShell/外层 uv 未收到 CTRL_C、只有已调用 `SetConsoleCtrlHandler(None, False)` 的内层 Python 组收到事件并最终传播 130。Task 9 再用真实 `watch-cli-child.py` 与生产 Core 跑完整 operator→host→inkforge_cli 链；两层证据缺一不可。

### Task 4：离线验证两个 policy、wrapper 和长篇 Skill

**Files outside repository:** Task 2–3 的全部个人 Skill 文件

- [ ] 用隔离的临时 LOCALAPPDATA、fake uv 和假仓库运行 PowerShell 集成测试，覆盖：

```text
policy 与 registry 一致
short policy 与迁移前 16 条集合一致
每个 policy 内无重复、无通配、无 Stage C 命令；允许共享 3 条 auth，short.* 与 long.* 不交叉
policy 与 cli-contract 命令清单一致
固定 HTTPS origin 与 production profile 不可覆盖
wrapper 只接受 schema v3 config，且子进程不存在任何 insecure HTTP 环境变量
业务命令执行一次 whoami 预检
JSON/JSONL、Unicode、stderr、退出码原样透传
invalid policy 在业务联网前失败
```

- [ ] 运行 quick validation：

```powershell
$env:PYTHONUTF8='1'
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator\tests\test-operator.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\niebo\.codex\skills\inkforge-production-long-novel-operator\tests\test-operator.ps1
python C:\Users\niebo\.codex\skills\.system\skill-creator\scripts\quick_validate.py C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator
python C:\Users\niebo\.codex\skills\.system\skill-creator\scripts\quick_validate.py C:\Users\niebo\.codex\skills\inkforge-production-long-novel-operator
```

- [ ] 执行 writing-skills 要求的 forward test：只读生产提示应选择长篇 Skill；要求绕过身份、直连 internal 或自动 approve 的提示应被拒绝。
- [ ] 披露个人 Skill 修改的绝对路径和验证结果；不要执行 `git add`。

### Task 5：执行仓库发布前全量验证

**Files:** whole repository, read-only verification

- [ ] 先检查 worktree 和生成文件：

```powershell
git status --short --branch
npm run api:generate
git diff -- apps/web/next-env.d.ts packages/api-client/src/generated
```

- [ ] 如果 `next-env.d.ts` 只含 dev/build 生成噪声，运行正式 build 后重新检查，不把无关生成漂移混入提交。
- [ ] 执行完整验证：

```powershell
npm run api:check
npm run test:web
npm run typecheck
npm run lint
npm run build
uv run pytest -q
uv run ruff check .
uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src
uv run pytest tests/architecture/test_compose_security.py -q
```

- [ ] schema 只读验证：

```powershell
uv run pytest apps/core-api/tests/db/test_schema_guard.py apps/core-api/tests/db/test_model_metadata.py -q
git diff --exit-code refs/codex/long-serial-plan-base..HEAD -- apps/core-api/src/inkforge_core/db/schema-contract.json apps/core-api/src/inkforge_core/db/models.py scripts/migrations
git diff --cached --exit-code -- apps/core-api/src/inkforge_core/db/schema-contract.json apps/core-api/src/inkforge_core/db/models.py scripts/migrations
git diff --exit-code -- apps/core-api/src/inkforge_core/db/schema-contract.json apps/core-api/src/inkforge_core/db/models.py scripts/migrations
$untrackedSchemaPaths = git ls-files --others --exclude-standard -- apps/core-api/src/inkforge_core/db/schema-contract.json apps/core-api/src/inkforge_core/db/models.py scripts/migrations
if ($LASTEXITCODE -ne 0) { throw "无法检查未跟踪 schema 文件" }
if ($untrackedSchemaPaths) { $untrackedSchemaPaths; throw "发现未跟踪 schema 或迁移文件" }
```

- [ ] 若本机 Docker 可用，再运行：

```powershell
docker compose --env-file .env.example -f infra/compose.yaml build web core-api agent-service
docker compose --env-file .env.example -f infra/compose.yaml up -d --wait
docker compose --env-file .env.example -f infra/compose.yaml ps
```

- [ ] 确认所有实现都已由所属 Task 精确提交，验证阶段没有残留或暂存差异；若生成/测试暴露修正，回到所属 Task 按其 Files 范围提交后重跑本 Task：

```powershell
git diff --check
git diff --cached --check
git diff --cached --quiet
if ($LASTEXITCODE -eq 1) { git diff --cached; throw "发布前仍有暂存差异" }
if ($LASTEXITCODE -gt 1) { throw "无法检查暂存差异" }
$repositoryChanges = git status --porcelain
if ($LASTEXITCODE -ne 0) { throw "无法检查工作树" }
if ($repositoryChanges) { $repositoryChanges; throw "发布前工作树必须干净" }
```

### Task 6：披露完整发布范围并推送 main

- [ ] 刷新远端并确认没有隐藏分叉：

```powershell
git fetch origin
git status --short --branch
git log --oneline --decorate origin/main..HEAD
git log --oneline --decorate HEAD..origin/main
```

- [ ] 在推送前向用户披露 `origin/main..HEAD` 的全部提交，不只描述最后一个 commit；确认工作树干净、`HEAD..origin/main` 为空。
- [ ] 如果实现使用 `codex/long-serial-cli-control-plane` 分支，先在验证后的本地 main 做非交互 fast-forward/merge，再重新运行上面的 ahead/behind 检查；不得把部分计划推到会自动部署的 main。
- [ ] 推送：

```powershell
git push origin main
```

- [ ] 记录本地 HEAD、远端 `refs/heads/main` 和 push 输出；push 成功只表示发布已触发。

### Task 7：监控 GitHub Actions 到部署终态

- [ ] 定位刚才 main commit 的 `CI and Deploy` run：

```powershell
$headSha = git rev-parse HEAD
$runId = $null
for ($attempt = 1; $attempt -le 12 -and [string]::IsNullOrWhiteSpace($runId); $attempt++) {
    $runId = gh run list --workflow build.yml --branch main --commit $headSha --limit 1 --json databaseId --jq '.[0].databaseId // empty'
    if ($LASTEXITCODE -ne 0) { throw "无法查询 GitHub Actions" }
    if ([string]::IsNullOrWhiteSpace($runId)) { Start-Sleep -Seconds 5 }
}
if ([string]::IsNullOrWhiteSpace($runId)) { throw "60 秒内未发现当前提交的 CI and Deploy run" }
gh run watch $runId --exit-status
$watchExitCode = $LASTEXITCODE
gh run view $runId --json status,conclusion,url,headSha,jobs
if ($LASTEXITCODE -ne 0) { throw "无法读取 GitHub Actions 终态" }
if ($watchExitCode -ne 0) { throw "CI and Deploy 未成功" }
```

- [ ] 只有 ci 与 deploy 都 success 才进入生产冒烟。失败时读取失败 job 日志，按证据修复并重新走全量验证；不要绕过 workflow 手工 SSH 部署。
- [ ] 报告 workflow URL、headSha、CI/Deploy conclusion。

### Task 8：生产只读冒烟与历史 Artifact 审计

**Files outside repository:**

- Verify: `C:\Users\niebo\.codex\skills\inkforge-production-long-novel-operator\scripts\operator.ps1`
- Verify: `C:\Users\niebo\.codex\skills\inkforge-production-long-novel-operator\scripts\smoke.ps1`

- [ ] 运行确定路径的只读验收器；它把每个完整响应保存到当前部署 SHA 对应的临时证据目录，并返回可供 Task 9 精确读取的 receipt：

```powershell
$headSha = git rev-parse HEAD
$smokeRoot = Join-Path ([System.IO.Path]::GetTempPath()) "inkforge-long-smoke-$headSha"
$readOnlyJson = & 'C:\Users\niebo\.codex\skills\inkforge-production-long-novel-operator\scripts\smoke.ps1' -Mode ReadOnly -OutputDirectory $smokeRoot
if ($LASTEXITCODE -ne 0) { throw "生产只读冒烟失败" }
$readOnlyReceipt = $readOnlyJson | ConvertFrom-Json
if ($readOnlyReceipt.novelId -eq $null -or $readOnlyReceipt.chapterId -eq $null) { throw "只读 receipt 缺少作品或章节 ID" }
$readOnlyReceipt | ConvertTo-Json -Depth 8
```

- [ ] 401 或 identity mismatch 时停止；只让用户在真实 TTY 执行同一 wrapper 的 auth.login，不接收密码文本。
- [ ] 从返回列表选择用户拥有的专用长篇测试作品；优先标题精确为 `CLI 长篇验收`。如果不存在，不用 CLI 创建，停止写入冒烟并请用户先通过 Web 创建该长篇和首章。
- [ ] 对选定 novel 执行 chapter.list/get、task.list/get、artifact.list、quality.get（若已有 check），核对完整 JSON、中文和正文尾部。
- [ ] 列出 `status=awaiting_user` 的 Artifact；对 `sourceBindingStatus=legacy_missing` 只报告并要求后续显式 discard/重新生成，不自动批准、丢弃或补造绑定。
- [ ] 确认所有请求只走固定公网 Core `/api/v1/**`，没有服务器登录或数据库查询。

### Task 9：在专用作品跑完整单章闭环

- [ ] 从 Task 8 的固定 receipt 路径重新读取目标。在执行前向用户披露 novelId、chapterId 和下列完整 mutation 序列；只有用户已对这一本专用测试作品明确授权本轮验收时才传 `-ConfirmMutations`，同一轮只确认一次。
- [ ] 运行可重复 ChapterLoop；脚本记录每个 caller-owned clientRequestId，网络结果不确定时只以相同 body 重放同一 ID，并保存全部 stdout/stderr/JSONL：

```powershell
$headSha = git rev-parse HEAD
$smokeRoot = Join-Path ([System.IO.Path]::GetTempPath()) "inkforge-long-smoke-$headSha"
$readOnlyReceipt = Get-Content -Raw -Encoding utf8 (Join-Path $smokeRoot 'read-only-receipt.json') | ConvertFrom-Json
$chapterLoopJson = & 'C:\Users\niebo\.codex\skills\inkforge-production-long-novel-operator\scripts\smoke.ps1' -Mode ChapterLoop -NovelId $readOnlyReceipt.novelId -ChapterId $readOnlyReceipt.chapterId -OutputDirectory $smokeRoot -ConfirmMutations
if ($LASTEXITCODE -ne 0) { throw "生产单章闭环失败" }
$chapterLoopReceipt = $chapterLoopJson | ConvertFrom-Json
$chapterLoopReceipt | ConvertTo-Json -Depth 12
```

- [ ] smoke 脚本内部按顺序执行：

```text
long.chapter.get
long.agent.start(operation=plan_chapter)
中断一次 long.task.watch，确认 task 仍运行
long.task.list -> long.task.get -> long.task.watch 恢复
读取 plan Artifact revision=R
对 waiting_user task 执行 long.task.cancel，返回 ARTIFACT_DECISION_REQUIRED；重新 GET 证明 task 与 Artifact 未变
用独立 clientRequestId 提交 expectedRevision=R+1 的 decision，返回 ARTIFACT_REVISION_CONFLICT，重新 GET 证明 Artifact 未变
long.artifact.revise 或 approve
long.agent.start(operation=write_chapter)
保存完整原章节到证据目录；用 long.chapter.save 写入“原文 + 本轮唯一来源冲突标记”并携带刚读取的 expectedUpdatedAt
旧 long.artifact.approve 返回 ARTIFACT_SOURCE_VERSION_CONFLICT
显式 discard 旧 Artifact，重新启动 write_chapter
approve 新正文
long.chapter.status -> review
long.agent.start(operation=review_chapter)
long.task.watch -> succeeded
long.task.get 返回完整 reviewReport，且没有新建可应用 Artifact 或修改正式正文
对已终态 review task 执行 long.task.cancel，返回 effective=false；再次 get 仍为 succeeded 且 reviewReport 字节完全一致
重新 long.chapter.get，从新建的 qualityChecks 取得非空 checkId
long.quality.run
long.quality.get 到终态
long.chapter.status -> completed
启动另一个 plan/write task
long.task.cancel
long.task.get 的 outcome 为 cancelled
```

- [ ] revision 冲突探针只使用独立 clientRequestId 和故意错误的 `expectedRevision=R+1`，断言 `ARTIFACT_REVISION_CONFLICT` 后 Artifact 的 revision/status/payload/sourceBindings 完全不变；随后真实 decision 使用刚读取的 R。其余每次 Artifact decision 都使用刚读取的 expectedRevision；来源冲突后不自动变基或覆盖。
- [ ] watcher Ctrl+C 必须由 `watch-interrupt-probe.py` 只向已恢复 Ctrl+C 处理的 Python child 进程组真实发送 CTRL_C_EVENT，返回 130 且 server task 仍可由 list/get 找回；不接受 kill/timeout 伪造。
- [ ] waiting_user 的 cancel 必须在固定序列中真实调用并返回 ARTIFACT_DECISION_REQUIRED；用显式 decision 处理，不把 cancel 当 discard。
- [ ] 来源冲突探针先把原章节全文保存为 UTF-8 证据，再用 `long.chapter.save` 的 contentFile 做确定性 CAS 修改；若新草案尚未 approve 就失败，recovery 按最新 GET 的 updatedAt 用原文件显式恢复并记录结果，冲突时停止而不强行覆盖。
- [ ] 核对最终章节全文末尾、Artifact payload/Diff、质量报告和错误 details/requestId 未截断。
- [ ] 再执行生产中短篇只读回归：auth.whoami、short.list；如果已有安全快照，可 short.pull 到既有专用目录，但不做写入。

### Task 10：最终交付记录

- [ ] 报告仓库 branch、最终 commit、远端 ref、GitHub Actions URL 与部署 conclusion。
- [ ] 报告生产只读和写入闭环每一步的 taskId/artifactId/outcome/error code，不披露 Cookie、Token 或密码。
- [ ] 报告个人 Skill 的本机绝对路径、policy 命令数、quick_validate 和 wrapper 测试结果，并明确它们未进入仓库 push。
- [ ] 报告仍未开放的 Stage C 结构写命令与原因。
- [ ] 若生产专用测试作品不存在，仓库/部署可以完成，但总体目标不能标记“生产闭环已验证”；明确唯一剩余阻塞是需要通过 Web 创建测试长篇和章节。

## 本计划完成门槛

- main push 对应的 CI 与 deploy 均成功，headSha 与本地 HEAD 一致。
- 生产 whoami、长篇列表、章节、任务和 Artifact 只读冒烟通过。
- 专用长篇完成 plan/write/review/quality/completed 与 cancel 实际闭环。
- 来源冲突、revision 冲突、waiting_user cancel 边界在生产按稳定错误 code 工作。
- 生产长篇 Skill 无 snapshot/manifest/SSH/DB/internal API，policy 无通配和 Stage C 命令。
- 中短篇 policy 迁移后授权集合和行为完全不变。
- 仓库 push 与本机 Skill 安装的发布边界已如实披露。
