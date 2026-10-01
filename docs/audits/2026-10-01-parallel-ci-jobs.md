# Java、Python 与 Web 并行 CI 验收

日期：2026-10-01。对应 [并行 CI 规格](../specs/2026-10-01-parallel-ci-jobs.md)。

## 仓内结果

Java、Python、Web 已拆为互不依赖的完整验证 job，保留原检查命令、失败诊断与依赖缓存。
`ci` 汇总仅在三项结果全部为 `success` 时放行镜像发布；生产发布队列保持独立且不可取消。
发布重试同时核对并行分支最近实际执行的结果，兼容原串行运行。

| 验证 | 结果 |
| --- | --- |
| 工作流、发布重试、Compose 安全相关测试 | 95 项通过 |
| Core 契约生成及 Agent 契约基线测试 | 8 项通过 |
| Ruff 全仓检查 | 通过 |
| Agent、共享协议与鉴权 Mypy | 132 个源文件通过 |
| actionlint 1.7.12 检查三个发布工作流 | 通过 |
| `git diff --check` | 通过 |

汇总门禁测试实际执行工作流中的 Bash，覆盖全成功和三个分支分别失败、取消、跳过、空值、
未知结果。发布重试覆盖缺失、重复、分支重跑失败、仅重跑部署及历史串行运行。

额外尝试 macOS 全仓 pytest，因现有部署测试夹具的 Linux 路径假设中止：5 项失败来自硬编码
`/usr/bin/dd`，1 项失败来自 `tempfile.gettempdir()` 与固定 `/tmp` bundle 路径不一致；
中止时 126 项通过、6 项失败。相关夹具及部署脚本本次未修改，不将本机全仓测试记为通过。
Ubuntu 完整运行及并行墙钟耗时待 GitHub Actions 验证。

## 耗时基线

上一串行运行 [36840581396](https://github.com/chimeiwang/Smart-Novel-Gen-nie/actions/runs/36840581396)
的 `ci` 为 12 分 50 秒，Java verify 为 6 分 45 秒、Python 测试为 4 分 10 秒，镜像发布为
1 分 30 秒。并行后的时长必须以实际运行记录比较，不把理论最大分支耗时记为实测。
