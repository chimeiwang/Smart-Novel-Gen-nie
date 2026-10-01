# DeepSeek 默认 strict 实现与生产验收

日期：2026-10-01。环境：本地 macOS 工作区、GitHub Actions Ubuntu runner、现有生产服务器。

## 结果

已完成 [默认 strict 规格](../specs/2026-10-01-deepseek-default-strict.md) 的实现、测试和生产发布。
生产容器内已验证默认工具请求走 Beta strict；未调用真实 DeepSeek，不能以本记录证明供应商实际返回。

- `deepseek_v4` 与 `generic` 下的 DeepSeek 工具请求均默认使用 Beta 端点及全部函数 `strict: true`。
- 45 个注册工具的 wire Schema 通过子集检查；HTTP 替身覆盖读取、正文、复审、节拍、质量报告，以及多工具、显式关闭和混用拒绝。
- 省略、null、空串、动态 JSON 与工具历史保持可逆；正文完整保留；条件字段组合、派生计数、原业务 Schema 校验继续生效。
- 非 DeepSeek、纯文本、既有 JSON Output、视频与 V2 质量执行回归通过。
- 保留任务开始前已有的 `docs/README.md` 代理入口、未跟踪代理规格、`.vscode/` 与代理配置文件。

## 验证命令

当前 shell 未提供 `uv`，因此使用现有虚拟环境内的等价工具入口，没有安装或改动依赖。

| 命令 | 结果 |
| --- | --- |
| `.venv/bin/pytest apps/agent-service/tests -q --tb=short` | 1890 通过；1 条既有 Starlette/httpx 弃用提示 |
| `.venv/bin/ruff check .` | 通过 |
| `.venv/bin/mypy apps/agent-service/src packages/service-contracts/src packages/service-auth/src` | 132 个源文件通过 |
| `git diff --check` | 通过 |
| 本次新增文档相对链接检查 | 通过 |

质量执行 HTTP 替身已修正为按既有 wire 返回空字符串，再由 Provider 归一化为业务 null；
业务终态结果断言不变。未放宽本地校验，也未增加自动模型重试。

## 生产发布

- 发布提交：`b9dcb1da04b01eebc65e352c89ac67f9fb0e4c58`。
- 来源运行：[36840581396](https://github.com/chimeiwang/Smart-Novel-Gen-nie/actions/runs/36840581396)。
  完整 CI 成功，耗时 12 分 50 秒；其中 Java verify 为 6 分 45 秒，Python 为 4 分 10 秒，
  Python 全仓结果为 3730 通过、2 跳过。镜像发布成功，耗时 1 分 30 秒。
- 自动部署在拉取 Web 镜像时持续低速，20 秒采样约 69.2 KiB/s。在确认当前容器健康、发布锁
  空闲和精确进程身份后停止本轮拉取，临时 GHCR 认证目录及子进程已清理。该自动运行结论是失败。
- 按用户“提交并部署”授权执行本机中转：从成功构建日志取得固定 digest 与 image ID，本机按
  digest 拉取 linux/amd64 镜像，并核对实际 ID、revision 标签与架构。清单制品下载未成功，
  因此使用这些证据重建并校验清单，未声称下载到了原 artifact。
- 中转私有脚本副本仅关闭按源码未变复用旧镜像的分支，确保部署本轮 CI 精确镜像；原容量、
  严格 SSH、逐镜像归档、远端 SHA-256、独立导入和清理门禁保留，仓内上传脚本未改。
  Web、Core、Agent 归档分别为 108848909、386389284、94391833 字节，上传分别约 75、292、72 秒。
- 使用仓内源码 bundle 与部署脚本完成切换，2026-10-01 09:38 UTC 前已结束，退出码为 0；
  schema guard、Compose 健康与编排冒烟通过。此前两次只读核对未收敛 Task、Command、V2 Run 均为 0。
  未执行 DDL；结构指纹为 `ea1df9ad015cd8d811d6ab250a7098870aa2befcf0afa3273b845255a0ac11b2`。
- 生产三项功能开关保持 schemaReady=true、route=off、V1 fresh=true；视频开关保持 false。
  备份校验通过，回退标签精确保留上一生产 `2ee71460bb80253d38f9c869725a77417c9b2f91` 的镜像 ID。
  发布后源码 bundle 与临时镜像目录已清理，发布锁空闲。

### 不可变镜像身份

| 服务 | 摘要 | 实际镜像 ID |
| --- | --- | --- |
| Web | `sha256:c2d5e3728b5bfa7d0be7a52d66282c86cfb5714992b697a739ed677bf55911b2` | `sha256:ba2b93bae95f03285a79384648f7a44f0c8b41b7d2031db4091bd7c14bcca5bc` |
| Core | `sha256:3566c9822a8e0eaadafe271d43a995460e92d5ab17d91b2bbbe963f844982ede` | `sha256:3d38a2de73772e19fda090a5d8222dabc0e6833be3dd9990f19574fe414374b9` |
| Agent | `sha256:0cb3118d56e10e31b3ca3ba54784a28476a25844ea0d5c591fefaa9d30987aac` | `sha256:03b46ca15dfcbd721ec585e006275fcda58af7a5206b390004a65aa7fa659b86` |

### 已部署代码验证与观察

在实际 Agent 容器中，以 HTTP 替身执行 45 个注册工具的默认请求，得到 `strictDefault=true`、
`endpointPath=/beta/chat/completions`、`realProviderCalls=0`。这验证部署代码的请求构造，
没有产生真实模型调用、费用或业务内容写入。

公开 readiness 返回 HTTP 200 且所有检查正常，六个容器均健康，业务镜像与上述 CI 身份一致。
从 09:38:19 UTC 开始每约 45 秒采样源码、镜像、健康、内存、重启、OOM、错误日志及公开 readiness；
至 10:08:22 UTC 共记录 39 次采样，观察跨度 30 分 3 秒，全部健康、零重启、无 OOM、无上述
业务错误日志，公开 readiness 均为 ready。30 分钟稳定观察通过；本次没有业务负载，
未验证 CRUD P95、SSE 首事件或模型延迟。

同日后续 [并行 CI 发布](2026-10-01-parallel-ci-jobs.md) 已将生产标签更新至 `e86b98b`，
三张应用镜像的全部文件层与本版本完全一致；后续生产身份和观察结果以该发布记录为准。
