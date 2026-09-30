# 工具契约与运行诊断验收

日期：2026-09-30。范围见[整改规格](../specs/2026-09-30-tool-contract-and-runtime-diagnostics.md)。

## 环境与范围

- 基线：`3307d464a5db4ca7048b8f6db703133dc7001d3f`。
- 工作树：`/Users/boqiangnie/.codex/worktrees/tool-contracts/inkforge`，分支 `codex/tool-contracts`。
- macOS、Python 3.12.10、JDK 21、Docker 28.1.1。Python 依赖按 `uv.lock` 安装到独立虚拟环境。
- 原主目录保留原有文档及未跟踪文件；本地验收阶段未修改生产环境、真实模型配置、数据库或正式作品。
- 未改公共 OpenAPI、数据库结构契约及 `contracts/agent-execution` 冻结资产；共享导出只更新
  `contracts/core/agent/read_tools/OutlineNodeArgs.schema.json` 与其摘要清单。

## 实现与兼容证据

- 定位字段的至少一个规则、普通产物／选区组合和复审组合进入模型 Schema；参数根级错误具有固定纠正说明。
- Operation Schema 在实际模型请求和工具预检共用，仍使用原注册对象和权限校验。预检按原契约省略
  可选 null 后复验，保留旧模型显式 null 与省略等价的行为；非空跨模式字段仍拒绝。
- 新模型 Beat Plan 输入不需要数量，由已校验数组派生；历史参数仍校验显式数量，不静默修正矛盾值。
- 实际 AgentRunner 回归覆盖 primary/reviser、正文／场景／两种选区；定位纠正覆盖整轮无副作用、
  独立授权和用量、二次失败停止。未增加纠正预算，未修改质量 strict 或 V2 Step 行为。
- 旧 V1 兼容定点 4 项通过：
  `test_long_serial_resume_reuses_snapshot_without_parent_classification`、
  `test_resume_writing_job_uses_flat_snapshot_and_continues_sequence`、
  `test_approve_resume_does_not_require_active_artifact_hydration`、
  `test_旧章节计划控制事件保留显式数量并形成草案`。
  这些是检查点恢复、作者决定及历史事件边界的受控测试，不宣称线上旧任务已经续跑。
- V2 生产 manifest 指纹仍为
  `08ed0e1a9d7d2f965a039c0aa37f875233f8314b3f59185891df86adb29633a9`。
- Core 真实 Spring Boot 控制台测试确认任务名、错误码、次数、退避、恢复及安全因果栈可见；
  合法 SQLState／整数厂商码可见，异常消息、假令牌、假 SQL 参数及非法 SQLState 不可见，因果循环有标记。
  这补齐诊断能力，不能反推出此前生产未知后台异常的具体根因。

## Nginx 隔离验证

使用生产同标签 `nginxinc/nginx-unprivileged:1.27-alpine`、独立临时网络和 Python 桩上游，未连接应用数据库。

| 场景 | 实测结果 |
| --- | --- |
| 普通 Web GET | 200 |
| Web POST 带 Next-Action | 404，由 Nginx 拦截 |
| Core POST 带同一请求头 | 200，仍转发至 Core 桩 |
| Core SSE | 两个事件完整返回，200 |
| 视频 API 上传 50 MiB 加 1 字节 | 200，完整转发 |
| 普通 API 上传相同大小 | 413，原限制保留 |

架构安全测试 27 项通过；隔离容器与网络已清理。该验证不替代线上发布后的流量检查。

## 验证命令与结果

- Agent Service 全目录、共享契约、服务鉴权、共享 Schema 导出基线与 Compose 安全检查：2836 项通过，
  1 条既有 Starlette TestClient 弃用提示，耗时 151.29 秒。
- 全仓 Ruff、131 个源文件的 Mypy、文档引用及 `git diff --check` 通过。
- Core 日志最终定点 JUnit 11 项通过。
- 最终代码的 `./mvnw verify` 全部模块构建成功，耗时 7 分 06 秒；服务身份 11 项、服务契约 5 项、
  Core 1221 项、CLI 147 项，均无失败或错误，Core 4 项外部环境用例跳过。

Java 外部环境用例的跳过范围为：未提供真实开发库地址的业务与结构验收、未设置临时跨语言 fixture
输出路径的用例，以及真实 FFmpeg 媒体链路用例。PostgreSQL 数据库行为由本次实际 Testcontainers
集成测试覆盖；未借用生产库或以 H2 替代。

```bash
uv sync --frozen --all-packages --group dev
uv run --frozen pytest apps/agent-service/tests packages/service-contracts/tests packages/service-auth/tests tests/architecture/test_agent_contract_schema_baseline.py tests/architecture/test_compose_security.py -q --tb=short
uv run --frozen ruff check .
uv run --frozen mypy apps/agent-service/src packages/service-contracts/src packages/service-auth/src
JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home PATH=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home/bin:$PATH ./mvnw verify
git diff --check
```

## 额外全仓 Python 检查的环境限制

额外尝试不限定目录的 `pytest`，在未修改的 `tests/architecture/test_deploy_scripts.py` 遇到 7 个失败，
随后停止该轮检查；未将它计为全仓通过。全部失败原因已在原始 main 单独复现：

- 5 项镜像上传用例的夹具硬编码 `/usr/bin/dd`；此 macOS 的系统 dd 在 `/bin/dd`，GNU dd 在 Homebrew
  路径，前置 PATH 无法修复夹具中的绝对路径。
- 2 项 bundle 用例在 `tempfile.gettempdir()` 创建文件，却传 `/tmp` 给脚本；macOS 的临时目录不同。
  仅为原始 main 的这两个用例设置 `TMPDIR=/tmp` 后，2 项均通过。

本次没有为消除这些环境失败修改无关部署脚本或测试夹具。后续 Linux CI 的全仓测试已通过，见下文。
本地应用回归与本记录不代表真实供应商或生产部署验收；jOOQ／PostgreSQL 版本兼容仍为独立事项。

## 生产发布授权与待验收项

2026-09-30 用户明确要求“提交到main，并部署”。本次通过 main push 触发现有 GitHub Actions
CI 和生产部署，继续保留视频关闭、数据库结构冻结及 V2 manifest 不变的边界。
生产部署完成后补记实际镜像版本、健康状态、只读结构核验、日志与 Nginx 边界检查；
推送或流水线受理本身不代表生产完成，不以健康检查替代真实模型写作验收。

## 生产发布前检查

- 修复提交 `e47474ddb64d10ca5d47b06582a7233a037ab9be` 已快进合入 main 并普通推送；
  [运行 36715544281](https://github.com/chimeiwang/Smart-Novel-Gen-nie/actions/runs/36715544281)
  于 2026-09-30 12:33:46 UTC 启动。
- 发布前源码和三业务镜像均为 `75bbadbd66da1bf0fed34a24eb688dd6a11d4c12`；六个服务 healthy，
  重启数 0、无 OOM，发布锁空闲，公开 readiness 为 ready，各检查项 ok。
- 生产检出无受跟踪代码差异；历史配置、备份、发布锁及辅助 Compose 文件作为未跟踪内容保留。
  根盘剩余 6.4 GiB，后续仍以镜像上传脚本对 Docker 数据目录和临时目录的容量门禁为准。
- 通过只读可重复读事务核对生产 `novelwriter`：V1 写作运行态、待作者审核、活动命令均为 0；
  V2 非终态为 0，终态 completed 58、failed 14、cancelled 1。
- 运行 Core 与服务器配置均保持 `schemaReady=true`、`route=off`、`V1 fresh=true`；
  `VIDEO_PREVIEW_ENABLED=false`。`.env` 和四个服务密钥文件存在、可读且非空，未读取输出秘密内容。
- 已有备份目录 `/srv/smart-novel-gen/.langgraph-rollback-backups/20260913.hIDwZ1`：
  `database.dump` 为 23197749 字节，数据库归档、execution Redis RDB 及校验清单存在。
  `sha256sum --check --status SHA256SUMS` 成功；`pg_restore --list database.dump` 成功读取
  688 个目录条目。该备份日期为 9 月 13 日，本次只验证完整性和归档可读性，没有执行恢复演练或恢复生产库。

## Linux CI 验收

上述运行的 CI job 成功，完整门禁没有跳过或重跑：

- Maven `verify` 成功；服务身份 11 项、共享契约 5 项、Core 1221 项、CLI 147 项，失败和错误均为 0，
  Core 5 项外部环境用例跳过。
- Python 全仓 3645 项通过、2 项跳过、1 条既有警告，耗时 228.63 秒；包含部署脚本回归。
- 生成客户端检查、Web/API 测试、Ruff、Mypy（131 个源文件）、类型检查、Lint 和应用构建全部成功。
- CI 成功后进入独立 deploy job，在 Runner 构建镜像并使用原上传及部署脚本发布。

## 首次上传失败与重试

首次 deploy job 在服务切换前失败：Core 压缩镜像 387428389 字节，2026-09-30 12:49:18 UTC
开始传输，13:09:18 UTC 达到 1200 秒上限，接收约 72 MB，退出码 124。
容量预检通过，需要约 2.58 GB、实际可用约 6.78 GB；没有进入哈希校验、Docker 导入或应用部署。
Web 构建输入未变化，已复用原镜像内容并添加目标标签；运行容器未切换。

期间主机只读采样显示 CPU 空闲 94–99%、I/O 等待 0%、无 swap 读写，网卡入站约 50.9 kB/s，
未见其他大流量下载。证据将本次故障定位于传输阶段，不能进一步认定发送端、网络或 SSH 中的具体根因。
上传日志未报告本次临时目录清理失败。

GitHub 集成的直接重试接口返回 Actions 写权限不足；因此通过本次审计文档提交触发现有 main push
流程重新发布同一份业务代码，仍执行完整 CI。未调整传输超时、网络配置、部署门禁或产品实现。
