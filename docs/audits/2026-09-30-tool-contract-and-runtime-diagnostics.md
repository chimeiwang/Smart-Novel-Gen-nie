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

本次没有为消除这些环境失败修改无关部署脚本或测试夹具。Linux CI 的完整部署脚本回归仍需后续发布门禁完成。
本地应用回归与本记录不代表真实供应商或生产部署验收；jOOQ／PostgreSQL 版本兼容仍为独立事项。

## 生产发布授权与待验收项

2026-09-30 用户明确要求“提交到main，并部署”。本次通过 main push 触发现有 GitHub Actions
CI 和生产部署，继续保留视频关闭、数据库结构冻结及 V2 manifest 不变的边界。
生产部署完成后补记实际镜像版本、健康状态、只读结构核验、日志与 Nginx 边界检查；
推送或流水线受理本身不代表生产完成，不以健康检查替代真实模型写作验收。
