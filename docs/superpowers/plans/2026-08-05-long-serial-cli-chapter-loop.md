# 长篇 CLI 章节闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把现有单文件 CLI 重构为行为可验证的命令注册表，并交付长篇查询、watcher 和安全章节闭环命令，同时保持全部 `auth.*`、`short.*` 外部契约不变。

**Architecture:** `registry.py` 是唯一能力表，`cli.py` 只启动和分派，`runtime.py` 统一认证、输入输出与异常；`commands/short` 保留 manifest/dirty/version 语义，`commands/long` 只调用 Core 公共 API，不维护任何本地业务状态。长篇 watcher 以持久 outcome 为权威并使用 SSE 作为过程流。

**Tech Stack:** Python 3.12、httpx、argparse、Windows Credential Manager、JSON/JSONL、原子 UTF-8 文件 I/O、pytest、Ruff、Mypy

---

## 执行前提

- Task 1–4 可与服务端计划并行；Task 5 注册全部只读命令前，控制面计划 Task 11 必须通过，且运行安全计划 Task 6 必须已交付 Artifact 列表与 `sourceBindingStatus`；Task 6 watcher 依赖控制面计划 Task 8 的稳定 outcome。
- Task 7–10 的写命令只有在 [运行安全计划](./2026-08-05-long-serial-runtime-safety.md) 全部通过后才能注册。
- 当前已验证 CLI 基线为 85 个测试通过；重构过程中每个小步骤都先跑 characterization tests。
- 任何 `long.*` 模块不得导入 short snapshot/manifest 代码。
- 强制 TDD 节奏：每个含“写失败测试”或新增边界断言的 Task，在测试编辑完成后、执行任何实现步骤前，立即运行该 Task 已列出的精确 pytest 命令并记录 RED；失败必须来自目标能力缺失。若意外通过先修正测试。实现后重复同一命令确认 GREEN，再允许提交。纯行为保持重构的 Task 3 先跑 characterization tests 为绿，再小步移动并持续保持绿。

### Task 1：用注册表描述现有命令而不改变行为

**Files:**

- Create: `tools/inkforge-cli/src/inkforge_cli/registry.py`
- Create: `tools/inkforge-cli/src/inkforge_cli/json_types.py`
- Create: `tools/inkforge-cli/src/inkforge_cli/runtime.py`
- Modify: `tools/inkforge-cli/src/inkforge_cli/cli.py`
- Create: `tools/inkforge-cli/tests/test_registry.py`
- Create: `tools/inkforge-cli/tests/test_runtime.py`
- Modify: `tools/inkforge-cli/tests/test_cli.py`

- [ ] 先保存基线：

```powershell
uv run pytest tools/inkforge-cli/tests -q
```

预期：85 passed。

- [ ] 写失败测试覆盖命令名唯一、未知命令、login argv_tty、普通命令单个 JSON、watch JSONL、metadata 与 handler 不一致 fail fast。
- [ ] 定义：

```python
type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]

InputMode = Literal["argv_tty", "json"]
OutputMode = Literal["json", "jsonl"]
FileOutputKind = Literal["none", "data_json", "primary_text"]
type JsonStream = Generator[JsonObject, None, int]
type CommandResult = JsonObject | JsonStream
CommandHandler = Callable[["CliRuntime", JsonObject], CommandResult]

@dataclass(frozen=True, slots=True)
class FileOutputSpec:
    kind: FileOutputKind
    field: str | None = None
    media_type: str | None = None

@dataclass(frozen=True, slots=True)
class CommandSpec:
    name: str
    handler: CommandHandler
    inputMode: InputMode
    outputMode: OutputMode
    fileOutput: FileOutputSpec
    mutation: bool
    requiresIdentity: bool
    requiresClientRequestId: bool
```

- [ ] 上面三个递归 JSON 类型放在无运行时依赖的 `json_types.py`，registry、runtime、io 和各 command 模块只从该文件导入，不引入 Pydantic，也不各自复制 `Any` 别名。
- [ ] runtime 以 `dict` 区分普通结果；流结果必须手动 `next()` 到 `StopIteration.value`，逐帧写 JSONL 并把整数 return value 作为进程退出码。生成器隐式返回 None、返回非整数或输出非 JsonObject 时 fail fast；不允许靠最后一帧文本猜退出码。
- [ ] 失败测试覆盖流在已经输出若干帧后分别 return 0/5/130，CLI 必须保留既有帧并准确返回终态退出码。

- [ ] registry 构建时拒绝空名、重复名、jsonl+文件输出、primary_text 缺 field/mediaType、mutation 但无 identity 等无效组合。
- [ ] `requiresIdentity` 只表示 runtime 读取 profile、配置和凭据；不要让普通 CLI 自动对每个命令额外调用 whoami。生产 wrapper 的身份预检属于发布计划。
- [ ] `cli.py` 只做：取命令名 → registry 查找 → 读取对应输入模式 → 构造 runtime → 统一输出/异常。
- [ ] `auth.login` 不再靠命令名 if 分支决定输入方式；由 CommandSpec 的 argv_tty 驱动。
- [ ] 运行新测试和全量 characterization tests：

```powershell
uv run pytest tools/inkforge-cli/tests/test_registry.py tools/inkforge-cli/tests/test_runtime.py tools/inkforge-cli/tests/test_cli.py -q
```

- [ ] 提交：

```powershell
git add tools/inkforge-cli/src/inkforge_cli/registry.py tools/inkforge-cli/src/inkforge_cli/json_types.py tools/inkforge-cli/src/inkforge_cli/runtime.py tools/inkforge-cli/src/inkforge_cli/cli.py tools/inkforge-cli/tests/test_registry.py tools/inkforge-cli/tests/test_runtime.py tools/inkforge-cli/tests/test_cli.py
git commit -m "重构：建立 CLI 命令注册表"
```

### Task 2：拆分通用精确 I/O 与 short snapshot 业务

**Files:**

- Create: `tools/inkforge-cli/src/inkforge_cli/io.py`
- Create: `tools/inkforge-cli/src/inkforge_cli/commands/__init__.py`
- Create: `tools/inkforge-cli/src/inkforge_cli/commands/short/__init__.py`
- Create: `tools/inkforge-cli/src/inkforge_cli/commands/short/snapshots.py`
- Modify: `tools/inkforge-cli/src/inkforge_cli/files.py`
- Create: `tools/inkforge-cli/tests/test_io.py`
- Create: `tools/inkforge-cli/tests/test_architecture.py`
- Modify: `tools/inkforge-cli/tests/test_files.py`

- [ ] 写失败测试覆盖 80,000 字、CRLF、中文、emoji/组合字符尾部、单尾换行 JSON、原子替换和两套描述符。
- [ ] `read_utf8_text_exact()` 必须使用 `Path.read_bytes().decode("utf-8")`，避免 Windows 文本模式自动换行转换。
- [ ] `atomic_write_bytes(target: Path, payload: bytes) -> None` 在目标目录创建临时文件、flush+fsync 后 `os.replace()`；异常时清理临时文件。
- [ ] 内部通用结果使用 bytes 与 sha256；适配层分别输出：

```json
{"path":"...","bytes":123,"sha256":"...","mediaType":"text/plain; charset=utf-8"}
```

```json
{"path":"...","contentHash":"...","byteLength":123,"charCount":100}
```

- [ ] 把 `load_snapshot_manifest/ensure_snapshot_clean/export_snapshot/DirtySnapshotError` 迁入 `commands/short/snapshots.py`；`files.py` 暂留兼容 re-export，待 Task 3 清理调用方。
- [ ] 架构测试用 AST/import 扫描断言：

```text
commands/long/** 不导入 commands.short.snapshots
io.py 不出现 manifest、dirty、snapshot clean 业务符号
```

- [ ] 运行：

```powershell
uv run pytest tools/inkforge-cli/tests/test_io.py tools/inkforge-cli/tests/test_architecture.py tools/inkforge-cli/tests/test_files.py -q
```

- [ ] 提交：

```powershell
git add tools/inkforge-cli/src/inkforge_cli/io.py tools/inkforge-cli/src/inkforge_cli/commands/__init__.py tools/inkforge-cli/src/inkforge_cli/commands/short/__init__.py tools/inkforge-cli/src/inkforge_cli/commands/short/snapshots.py tools/inkforge-cli/src/inkforge_cli/files.py tools/inkforge-cli/tests/test_io.py tools/inkforge-cli/tests/test_architecture.py tools/inkforge-cli/tests/test_files.py
git commit -m "重构：隔离 CLI 通用文件与短篇快照"
```

### Task 3：模块化 auth 与 short 命令并保持外部契约

**Files:**

- Create: `tools/inkforge-cli/src/inkforge_cli/commands/auth.py`
- Create: `tools/inkforge-cli/src/inkforge_cli/commands/short/documents.py`
- Create: `tools/inkforge-cli/src/inkforge_cli/commands/short/versions.py`
- Create: `tools/inkforge-cli/src/inkforge_cli/commands/short/agents.py`
- Modify: `tools/inkforge-cli/src/inkforge_cli/cli.py`
- Modify: `tools/inkforge-cli/src/inkforge_cli/registry.py`
- Modify: `tools/inkforge-cli/tests/test_cli.py`
- Modify: `tools/inkforge-cli/tests/test_files.py`

- [ ] 按 auth → documents → versions → agents 顺序逐组移动；每移动一组都运行：

```powershell
uv run pytest tools/inkforge-cli/tests/test_cli.py tools/inkforge-cli/tests/test_files.py tools/inkforge-cli/tests/test_credentials.py tools/inkforge-cli/tests/test_api.py -q
```

- [ ] 保持以下精确行为：login 仅真实 TTY 隐藏读取密码；Cookie/密码不进入 stdout；short create 的 caller ID 要求不变；manifest/dirty gate 不变；Diff 和 version 文件要求不变；short watcher 失败终态仍按现状退出 0。
- [ ] short 的 `path/contentHash/byteLength/charCount` 不改名；short 普通传输异常仍走原退出 1 语义。
- [ ] 删除 `cli.py` 中已迁移的大型 `_dispatch` 分支，但不要做无关格式重写。
- [ ] 提交：

```powershell
git add tools/inkforge-cli/src/inkforge_cli/commands/auth.py tools/inkforge-cli/src/inkforge_cli/commands/short/documents.py tools/inkforge-cli/src/inkforge_cli/commands/short/versions.py tools/inkforge-cli/src/inkforge_cli/commands/short/agents.py tools/inkforge-cli/src/inkforge_cli/cli.py tools/inkforge-cli/src/inkforge_cli/registry.py tools/inkforge-cli/tests/test_cli.py tools/inkforge-cli/tests/test_files.py
git commit -m "重构：模块化现有 CLI 命令"
```

### Task 4：按命令族稳定映射传输异常和文件输出

**Files:**

- Modify: `tools/inkforge-cli/src/inkforge_cli/api.py`
- Modify: `tools/inkforge-cli/src/inkforge_cli/runtime.py`
- Modify: `tools/inkforge-cli/src/inkforge_cli/registry.py`
- Modify: `tools/inkforge-cli/tests/test_api.py`
- Modify: `tools/inkforge-cli/tests/test_runtime.py`
- Create: `tools/inkforge-cli/tests/test_long_output_files.py`

- [ ] 用参数化失败测试固定长篇完整退出码：输入/命令/422 → 2；401、凭据缺失、预期用户名不匹配 → 3；版本/幂等/来源/目标占用 409 → 4；403、5xx、HTTP transport → 5；本地文件错误 → 6；未预期异常 → 1。所有服务端错误都完整保留 code/message/details/requestId；同一 transport error 在现有 short 仍返回 1。
- [ ] `api.py` 把普通 HTTP 的 `httpx.TransportError` 包装为不含 header/cookie 的 `CoreTransportError`；SSE 继续使用 `SseConnectionError`。
- [ ] runtime 根据 CommandSpec 而不是全局改变退出码；长篇使用上表，现有 auth/short 的全部映射保持 characterization tests 当前结果，不借机统一。
- [ ] 实现 long `outputFile`：

```python
class FileDescriptor(TypedDict):
    path: str
    bytes: int
    sha256: str
    mediaType: str

def write_bytes(output_file: str, payload: bytes,
                media_type: str) -> FileDescriptor:
    target = Path(output_file).expanduser().resolve()
    atomic_write_bytes(target, payload)
    return {
        "path": str(target),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "mediaType": media_type,
    }

def write_data_json(output_file: str, data: JsonValue) -> FileDescriptor:
    payload = (
        json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    return write_bytes(output_file, payload, "application/json; charset=utf-8")

def write_primary_text(output_file: str, data: JsonObject, field: str,
                       media_type: str) -> JsonObject:
    value = data.get(field)
    if not isinstance(value, str):
        raise CoreResponseContractError(f"响应缺少文本字段：{field}")
    descriptor = write_bytes(output_file, value.encode("utf-8"), media_type)
    result = dict(data)
    del result[field]
    result[f"{field}File"] = dict(descriptor)
    return result
```

- [ ] `CoreResponseContractError` 是远端响应契约错误，long 退出 5；`atomic_write_bytes` 的 OSError/权限/磁盘失败包装为本地文件错误并退出 6。文件描述符 path 始终为绝对路径。
- [ ] data_json 写未包装 `data` 的完整格式化 JSON；stdout 的 data 变为 `{"resultFile": descriptor}`。
- [ ] primary_text 把原字段替换成 `<field>File`，其余 metadata 原样保留；不按大小自动切换。
- [ ] `profile/outputFile/outputDirectory/*File` 等本地字段只有明确 handler 消费时才移除，绝不发送给 Core。
- [ ] 运行：

```powershell
uv run pytest tools/inkforge-cli/tests/test_api.py tools/inkforge-cli/tests/test_runtime.py tools/inkforge-cli/tests/test_long_output_files.py tools/inkforge-cli/tests/test_cli.py -q
```

- [ ] 提交：

```powershell
git add tools/inkforge-cli/src/inkforge_cli/api.py tools/inkforge-cli/src/inkforge_cli/runtime.py tools/inkforge-cli/src/inkforge_cli/registry.py tools/inkforge-cli/tests/test_api.py tools/inkforge-cli/tests/test_runtime.py tools/inkforge-cli/tests/test_long_output_files.py
git commit -m "功能：统一长篇 CLI 输出与传输错误"
```

### Task 5：注册全部长篇只读命令

**Files:**

- Create: `tools/inkforge-cli/src/inkforge_cli/commands/long/__init__.py`
- Create: `tools/inkforge-cli/src/inkforge_cli/commands/long/read.py`
- Create: `tools/inkforge-cli/src/inkforge_cli/commands/long/knowledge.py`
- Modify: `tools/inkforge-cli/src/inkforge_cli/registry.py`
- Create: `tools/inkforge-cli/tests/test_long_read_commands.py`
- Modify: `tools/inkforge-cli/tests/test_architecture.py`

- [ ] 参数化写失败测试，固定命令到路由映射；`long.task.get` 对 review_chapter 的 `reviewReport` 默认完整内联，显式 outputFile 时完整写入且不截断：

```text
long.novel.list             GET /api/v1/novels?storyLengthProfile=long_serial
long.novel.get              GET /api/v1/novels/{novelId}
long.chapter.list           GET /api/v1/novels/{novelId}/chapters
long.chapter.get            GET /api/v1/chapters/{chapterId}
long.session.list           GET /api/v1/writing/sessions?novelId=...&chapterId=...
long.session.get            GET /api/v1/writing/sessions/{sessionId}
long.planning.get           GET /api/v1/novels/{novelId}/workspace/planning
long.lore.get               GET /api/v1/novels/{novelId}/workspace/lore
long.resources.get          GET /api/v1/novels/{novelId}/workspace/resources
long.outline-node.list      GET /api/v1/novels/{novelId}/outline-nodes
long.foreshadowing.list     GET /api/v1/novels/{novelId}/foreshadowings
long.task.list              GET /api/v1/writing/runs
long.task.get               GET /api/v1/writing/runs/{taskId}
long.artifact.list          GET /api/v1/review-artifacts
long.artifact.get           GET /api/v1/review-artifacts/{artifactId}
long.quality.get            GET /api/v1/quality-checks/{checkId}
```

- [ ] stdin 字段白名单与 CommandSpec 固定如下；所有命令都额外允许本地 `profile`（默认 `default`）和可选 `outputFile`，两者不得发给 Core，表外字段一律退出 2：

| 命令 | 必填业务字段 | 可选业务字段/查询 | Core 查询 | fileOutput |
| --- | --- | --- | --- | --- |
| `long.novel.list` | 无 | 无 | 固定 `storyLengthProfile=long_serial` | `data_json` |
| `long.novel.get` | `novelId` | 无 | 无 | `data_json` |
| `long.chapter.list` | `novelId` | 无 | 无 | `data_json` |
| `long.chapter.get` | `chapterId` | 无 | 无 | `primary_text(content)` |
| `long.session.list` | `novelId` | `chapterId` | 同名映射 | `data_json` |
| `long.session.get` | `sessionId` | 无 | 无 | `data_json` |
| `long.planning.get` | `novelId` | 无 | 无 | `data_json` |
| `long.lore.get` | `novelId` | 无 | 无 | `data_json` |
| `long.resources.get` | `novelId` | 无 | 无 | `data_json` |
| `long.outline-node.list` | `novelId` | 无 | 无 | `data_json` |
| `long.foreshadowing.list` | `novelId` | 无 | 无 | `data_json` |
| `long.task.list` | `novelId` | `chapterId, writingSessionId, operation, outcome, cursor, limit` | 可选字段同名映射 | `data_json` |
| `long.task.get` | `taskId` | 无 | 无 | `data_json` |
| `long.artifact.list` | `novelId` | `chapterId, taskId, status, kind, cursor, limit` | 可选字段同名映射 | `data_json` |
| `long.artifact.get` | `artifactId` | 无 | 无 | `data_json` |
| `long.quality.get` | `checkId` | 无 | 无 | `data_json` |

- [ ] 所有 ID 使用 `quote(value, safe="")`；API client 仍拒绝非 `/api/v1/**` 和任何 `/internal/**`。
- [ ] GET 结果不缓存、不建本地绑定、不比较 mtime/hash。
- [ ] `long.chapter.get` 声明 primary_text(content)；Artifact 固定 data_json；其他命令按返回结构声明 data_json 或无文件输出。没有 outputFile 时全部完整内联。
- [ ] `long.novel.list` 固定 server query `storyLengthProfile=long_serial`，调用方同名字段不能覆盖。
- [ ] 运行：

```powershell
uv run pytest tools/inkforge-cli/tests/test_long_read_commands.py tools/inkforge-cli/tests/test_long_output_files.py tools/inkforge-cli/tests/test_architecture.py -q
```

- [ ] 提交：

```powershell
git add tools/inkforge-cli/src/inkforge_cli/commands/long/__init__.py tools/inkforge-cli/src/inkforge_cli/commands/long/read.py tools/inkforge-cli/src/inkforge_cli/commands/long/knowledge.py tools/inkforge-cli/src/inkforge_cli/registry.py tools/inkforge-cli/tests/test_long_read_commands.py tools/inkforge-cli/tests/test_architecture.py
git commit -m "功能：增加长篇 CLI 查询命令"
```

### Task 6：实现持久 outcome 驱动的长篇 watcher

**Files:**

- Create: `tools/inkforge-cli/src/inkforge_cli/commands/long/tasks.py`
- Modify: `tools/inkforge-cli/src/inkforge_cli/registry.py`
- Modify: `tools/inkforge-cli/src/inkforge_cli/runtime.py`
- Create: `tools/inkforge-cli/tests/test_long_task_watch.py`

- [ ] 用可注入 monotonic clock/backoff 写失败测试，覆盖首次 snapshot、Last-Event-ID、无事件但 Core 可达、断线 GET、waiting_user、全部终态、review_chapter terminal 帧含完整 reviewReport、连续不可达 300 秒、Ctrl+C 130 和绝不调用 cancel。
- [ ] 输出帧固定为：

```json
{"type":"snapshot","data":{}}
{"type":"event","id":"...","event":"...","data":{}}
{"type":"waiting_user","taskId":"...","artifactId":"...","data":{}}
{"type":"terminal","data":{}}
```

- [ ] 建连前先 GET `/writing/runs/{taskId}`；只读取 `response.outcome.state`，不看 phase、event 名或 Agent 文本猜终态。
- [ ] queued/running 连接 SSE；保存本进程最新非空 event id。断线后立即 GET；仍运行时按 0.5/1/2/5/10 秒封顶退避重连。
- [ ] 只有连续 Core 不可达累计超过 300 秒才退出 5；Core 可达但没有过程事件会重置不可达预算。
- [ ] watcher handler 返回 `JsonStream`：waiting_user/succeeded 在最后一帧后 `return 0`；failed/cancelled/inconsistent `return 5`。
- [ ] Ctrl+C 最后一帧返回 `WATCH_INTERRUPTED`、taskId、lastEventId，明确“仅停止观察，服务端任务未取消”，然后生成器 `return 130`；runtime 使用 Task 1 固定的 `StopIteration.value` 通道取得该退出码。
- [ ] 不把 lastEventId 持久化到文件；进程重启标准恢复是 task.list → task.get → watch。
- [ ] 运行：

```powershell
uv run pytest tools/inkforge-cli/tests/test_long_task_watch.py tools/inkforge-cli/tests/test_api.py -q
```

- [ ] 提交：

```powershell
git add tools/inkforge-cli/src/inkforge_cli/commands/long/tasks.py tools/inkforge-cli/src/inkforge_cli/registry.py tools/inkforge-cli/src/inkforge_cli/runtime.py tools/inkforge-cli/tests/test_long_task_watch.py
git commit -m "功能：增加可恢复的长篇任务观察"
```

## 写命令开放检查点

继续 Task 7 前必须重新运行运行安全计划 Task 12 的全部命令，并记录通过输出。若其中任一失败，停在只读 CLI；不得注册空 handler、feature flag 后门或返回 `NOT_IMPLEMENTED` 的写命令。

### Task 7：注册章节人工写入命令

**Files:**

- Create: `tools/inkforge-cli/src/inkforge_cli/commands/long/chapters.py`
- Modify: `tools/inkforge-cli/src/inkforge_cli/registry.py`
- Create: `tools/inkforge-cli/tests/test_long_chapter_commands.py`

- [ ] 写失败测试覆盖 route/body、CAS 字段、content/contentFile XOR、CRLF/尾部无损、local fields 不外发、文件错误退出 6。
- [ ] `long.chapter.save`：读取 chapterId/title/expectedUpdatedAt；content 与 contentFile 恰好一个；PATCH `/chapters/{id}`。
- [ ] `long.chapter.status`：读取 chapterId/status/expectedUpdatedAt；PATCH `/chapters/{id}/status`。
- [ ] `long.chapter.progress.save`：读取 chapterId/content/expectedUpdatedAt（首次显式 null）；PUT `/chapters/{id}/progress`。
- [ ] 三个命令均 `mutation=true`、requiresIdentity=true；它们是 CAS 写，不错误要求 clientRequestId。
- [ ] contentFile 只为本次请求读取，不创建 manifest、hash gate 或绑定。
- [ ] 运行：

```powershell
uv run pytest tools/inkforge-cli/tests/test_long_chapter_commands.py tools/inkforge-cli/tests/test_io.py -q
```

- [ ] 提交：

```powershell
git add tools/inkforge-cli/src/inkforge_cli/commands/long/chapters.py tools/inkforge-cli/src/inkforge_cli/registry.py tools/inkforge-cli/tests/test_long_chapter_commands.py
git commit -m "功能：增加长篇章节人工写入命令"
```

### Task 8：注册长篇 Agent、resume 与 cancel

**Files:**

- Modify: `tools/inkforge-cli/src/inkforge_cli/commands/long/tasks.py`
- Modify: `tools/inkforge-cli/src/inkforge_cli/registry.py`
- Create: `tools/inkforge-cli/tests/test_long_task_commands.py`

- [ ] 写失败测试覆盖三个 Operation、target/scope 原样传递、clientRequestId 16..128、selectedAgents 拒绝、resume 不接受 Artifact decision、cancel 空 body 身份、409 详情。
- [ ] `long.agent.start` POST `/writing/runs`，固定加入 `workflow=long_serial`；仅允许 plan_chapter/write_chapter/review_chapter，要求 chapter target 与 chapter scope 的 ID 一致。
- [ ] 不让 CLI 推导 Agent/reviewers/artifact kind，也不发送 selectedAgents。
- [ ] `long.task.resume` POST `/writing/runs/{taskId}/resume`，只发送 clientRequestId/writingSessionId/userMessage。
- [ ] `long.task.cancel` POST `/writing/runs/{taskId}/cancel`，只发送 clientRequestId；不和 watch 中断混用。
- [ ] 三个命令都要求 caller 提供稳定 ID；CLI 不自动生成，也不在 transport error 后自动换 ID 重试。
- [ ] 运行：

```powershell
uv run pytest tools/inkforge-cli/tests/test_long_task_commands.py tools/inkforge-cli/tests/test_long_task_watch.py -q
```

- [ ] 提交：

```powershell
git add tools/inkforge-cli/src/inkforge_cli/commands/long/tasks.py tools/inkforge-cli/src/inkforge_cli/registry.py tools/inkforge-cli/tests/test_long_task_commands.py
git commit -m "功能：增加长篇任务控制命令"
```

### Task 9：注册 Artifact decision 命令

**Files:**

- Create: `tools/inkforge-cli/src/inkforge_cli/commands/long/artifacts.py`
- Modify: `tools/inkforge-cli/src/inkforge_cli/registry.py`
- Create: `tools/inkforge-cli/tests/test_long_artifact_commands.py`

- [ ] 写失败测试覆盖 expectedRevision、editedContent/file XOR、revise 必须 userMessage、discard 禁止编辑、legacy/not-supported 规则、source conflict 详情。
- [ ] approve/revise 在 POST 前 GET Artifact：

```text
verified          -> 允许继续
legacy_missing    -> CLI 本地拒绝 approve/revise，退出 4
not_yet_supported -> CLI 本地拒绝 approve/revise，退出 4
```

discard 不受 sourceBindingStatus 限制，但仍发送 expectedRevision。
- [ ] approve 的 editedContent 与 editedContentFile 至多一个；两者都无时使用服务端 Artifact 当前候选。
- [ ] revise 必须提供非空 userMessage；discard 不接受 editedContent、editedContentFile、selectedUpdateRefs。
- [ ] 注册 `long.artifact.approve`、`long.artifact.revise`、`long.artifact.discard`；三者均为 mutation 且要求 caller-owned clientRequestId，POST `/review-artifacts/{artifactId}/decision`，body 固定包含 clientRequestId、expectedRevision、decision 和合法可选字段。
- [ ] 文件按原始 UTF-8 字节读取，不更改换行或尾部；不把 artifact GET 结果保存为本地权威状态。
- [ ] 运行：

```powershell
uv run pytest tools/inkforge-cli/tests/test_long_artifact_commands.py tools/inkforge-cli/tests/test_long_output_files.py -q
```

- [ ] 提交：

```powershell
git add tools/inkforge-cli/src/inkforge_cli/commands/long/artifacts.py tools/inkforge-cli/src/inkforge_cli/registry.py tools/inkforge-cli/tests/test_long_artifact_commands.py
git commit -m "功能：增加长篇草案决策命令"
```

### Task 10：注册质量命令

**Files:**

- Create: `tools/inkforge-cli/src/inkforge_cli/commands/long/quality.py`
- Modify: `tools/inkforge-cli/src/inkforge_cli/registry.py`
- Create: `tools/inkforge-cli/tests/test_long_quality_commands.py`

- [ ] 写失败测试覆盖 run 稳定 ID、skip/reset CAS、Core 错误保留、local profile 不外发。
- [ ] `long.quality.run` POST `/quality-checks/{checkId}/run`，发送 clientRequestId、可选 taskId/message。
- [ ] `long.quality.skip` PATCH 同一 check，发送 status=skipped、resetResult=false、expectedUpdatedAt。
- [ ] `long.quality.reset` PATCH 同一 check，发送 status=pending、resetResult=true、expectedUpdatedAt。
- [ ] run 要求 clientRequestId；skip/reset 是 CAS 写，不要求 clientRequestId。
- [ ] 运行：

```powershell
uv run pytest tools/inkforge-cli/tests/test_long_quality_commands.py -q
```

- [ ] 提交：

```powershell
git add tools/inkforge-cli/src/inkforge_cli/commands/long/quality.py tools/inkforge-cli/src/inkforge_cli/registry.py tools/inkforge-cli/tests/test_long_quality_commands.py
git commit -m "功能：增加长篇质量控制命令"
```

### Task 11：固定 registry、文档清单和未开放命令边界

**Files:**

- Modify: `tools/inkforge-cli/tests/test_registry.py`
- Modify: `tools/inkforge-cli/tests/test_architecture.py`
- Modify: `tools/inkforge-cli/README.md`

- [ ] registry 精确断言当前 auth、short、long 命令集合；命令名不得重复。
- [ ] 断言所有 long mutation 都属于本计划明确的 12 条写命令；`long.task.watch` 必须 mutation=false/outputMode=jsonl。
- [ ] 断言下列 Stage C 名称不存在于 registry：outline save/node mutation、foreshadowing mutation、lore mutation、reference mutation/reindex、style mutation。
- [ ] 文档命令清单由 registry 导出或测试精确比对，不维护手写通配授权。
- [ ] 运行：

```powershell
uv run pytest tools/inkforge-cli/tests/test_registry.py tools/inkforge-cli/tests/test_architecture.py -q
```

- [ ] 提交：

```powershell
git add tools/inkforge-cli/tests/test_registry.py tools/inkforge-cli/tests/test_architecture.py tools/inkforge-cli/README.md
git commit -m "测试：固定长篇 CLI 能力边界"
```

### Task 12：完成 CLI 总回归

- [ ] 全量测试：

```powershell
uv run pytest tools/inkforge-cli/tests -q
```

- [ ] 静态检查：

```powershell
uv run ruff check tools/inkforge-cli
uv run mypy tools/inkforge-cli/src
```

- [ ] 检查没有长篇本地状态与危险路径：

```powershell
uv run pytest tools/inkforge-cli/tests/test_architecture.py tools/inkforge-cli/tests/test_registry.py -q
$localStateHits = rg -n "commands\.short\.snapshots|load_snapshot_manifest|ensure_snapshot_clean|DirtySnapshotError|DATABASE_URL|/internal/" tools/inkforge-cli/src/inkforge_cli/commands/long
if ($LASTEXITCODE -gt 1) { throw "rg 执行失败" }
if ($LASTEXITCODE -eq 0) { $localStateHits; throw "长篇命令引用了本地业务状态或危险路径" }
$stageCHits = rg -n "long\.(outline|foreshadowing|lore|reference|style).*\.(save|create|update|delete|reindex|apply|clear)" tools/inkforge-cli/src/inkforge_cli/registry.py
if ($LASTEXITCODE -gt 1) { throw "rg 执行失败" }
if ($LASTEXITCODE -eq 0) { $stageCHits; throw "registry 提前注册了 Stage C 命令" }
```

预期：架构/注册表测试通过，两项精确扫描都正常完成且没有命中；watcher 合法的 `snapshot` 帧不会被误报。

- [ ] 运行与服务端契约的联合测试：

```powershell
uv run pytest tools/inkforge-cli/tests apps/core-api/tests/writing/test_run_queries.py apps/core-api/tests/writing/test_cancel.py apps/core-api/tests/reviews/test_artifact_list.py apps/core-api/tests/quality/test_quality_state.py -q
```

- [ ] 若总回归失败，回到引入问题的 Task，按该 Task 的精确 Files 范围修复、重新走 RED/GREEN 并提交；本 Task 不使用目录级 `git add`，全部通过时不创建空提交。

## 本计划完成门槛

- 现有 auth/short 测试全部通过，外部 JSON、文件描述符和退出码未变。
- 全部长篇查询命令与 watcher 可在无本地状态下恢复任务。
- watcher 首帧为持久 snapshot，失败/cancelled/inconsistent 返回 5，Ctrl+C 返回 130 且不取消服务端任务。
- 所有写命令只调用 `/api/v1/**`，稳定 ID 由调用方提供。
- 80,000 字以上正文、Artifact、Diff、中文和 Unicode 尾部无截断或换行改写。
- long 模块不导入 manifest/dirty/snapshot 逻辑。
- Stage C 结构写命令没有注册，也没有生产授权入口。
