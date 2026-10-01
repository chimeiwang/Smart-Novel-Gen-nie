# Java、Python 与 Web 并行 CI

状态：已提交 main，仓内验证、GitHub Actions 三路并行全量验证、生产切换及 30 分钟稳定观察通过；见
[验收记录](../audits/2026-10-01-parallel-ci-jobs.md)。用户在本轮发布耗时分析后要求“改成并行 job”。

## 背景与目标

发布运行 `36840581396` 的完整 CI 用时 12 分 50 秒，其中 Java verify 为 6 分 45 秒，Python
全仓测试为 4 分 10 秒；三镜像构建发布仅 1 分 30 秒。当前串行 CI 是主要可优化环节之一。

- 将完整验证拆为互不依赖的 `ci-java`、`ci-python`、`ci-web`，不减少测试、不按文件过滤。
- 保留稳定的 `ci` 汇总检查及既有镜像发布、制品重试和生产部署门禁。
- 本次不改变默认镜像构建方式、生产下载路径、发布观察规则、业务代码、数据库或功能开关。

## 设计

1. Java job 仅安装 JDK 21 并复用 Maven 缓存，执行原完整 `./mvnw verify` 与失败诊断。
2. Python job 安装 Python 3.12、uv 和 Node 22，执行原依赖同步、全仓 pytest、Ruff、Mypy。
   Node 用于 Python 架构测试内的 `build_core_openapi.mjs --check`；不依赖 Java job 的产物。
3. Web job 安装 Node 22、执行 `npm ci`，保留 API 客户端检查、Web/API 测试、类型检查、lint 和构建。
4. 三个验证 job 与汇总 job 使用不同的 job 级并发组，同分支新提交可取消各自旧验证，不互相取消。
   不引入 workflow 级取消，生产发布继续使用不可取消的独立队列。
5. `ci` 依赖上述三个 job，以 `always()` 运行并逐一要求结果为 `success`。失败、取消、跳过或
   未知结果均返回非零；`publish-images` 继续依赖 `ci`，不能凭被跳过的检查放行。
6. 发布重试继续核对 `ci` 和 `publish-images`；如果原运行出现任一并行验证 job，还必须核对三个
   分支最近实际执行的结果均成功，防止旧汇总成功掩盖新分支失败。历史串行运行保持兼容。

## 验收

- 检查 DAG、工具链与完整命令覆盖；三个验证 job 之间没有 `needs` 依赖。
- 实际执行汇总 shell，覆盖三个分支全部成功及单分支失败、取消、跳过、未知结果。
- 重试解析覆盖并行分支缺失、重复、失败、部分重跑和旧串行运行。
- 运行相关架构测试、Compose 安全检查、Ruff、工作流语法检查与 `git diff --check`。
- 新流水线真实墙钟耗时必须以 GitHub Actions 实测为准，不能用三个耗时的最大值冒充已验证结果。

依据：[GitHub job 依赖规则](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-jobs)。
