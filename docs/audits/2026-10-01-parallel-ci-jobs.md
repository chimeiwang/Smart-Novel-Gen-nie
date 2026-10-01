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
后续 Ubuntu 完整运行通过，详见下方实际运行结果。

## 耗时基线

上一串行运行 [36840581396](https://github.com/chimeiwang/Smart-Novel-Gen-nie/actions/runs/36840581396)
的 `ci` 为 12 分 50 秒，Java verify 为 6 分 45 秒、Python 测试为 4 分 10 秒，镜像发布为
1 分 30 秒。并行后的时长必须以实际运行记录比较，不把理论最大分支耗时记为实测。

## GitHub Actions 实际运行

提交 `e86b98b062838a6c6d8956bea98bc6e1ac5ec31a` 已推送 main，运行
[36846267961](https://github.com/chimeiwang/Smart-Novel-Gen-nie/actions/runs/36846267961)
的三路验证与稳定汇总均成功。

| Job | 开始时间（UTC） | 完成时间（UTC） | 耗时 | 结果 |
| --- | --- | --- | --- | --- |
| `ci-web` | 09:59:33 | 10:00:39 | 1 分 6 秒 | 376 项测试、API 检查、类型检查、lint、构建通过 |
| `ci-java` | 09:59:34 | 10:06:21 | 6 分 47 秒 | Maven 全量 verify 通过 |
| `ci-python` | 09:59:34 | 10:05:16 | 5 分 42 秒 | 3763 通过、2 跳过；Ruff、Mypy 通过 |
| `ci` | 10:06:24 | 10:06:26 | 2 秒 | 三路全部成功，允许发布 |

从最早验证 job 启动到汇总完成的墙钟时间为 **6 分 53 秒**，相比上一串行 CI 的 12 分 50 秒
减少 **5 分 57 秒，约 46%**。本轮 Python 测试本身耗时 5 分 4 秒，长于上一轮；总验证耗时仍因
独立并行明显缩短。该比较只覆盖 CI 验证，不包含镜像发布、生产拉取和发布后观察。

## 镜像发布与生产中转

镜像发布 job 于 10:06:29–10:07:19 UTC 成功，耗时 50 秒。生产队列中的来源复核已同时验证
三个并行分支及稳定汇总，证明新发布重试门禁可以读取真实 GitHub job 结果。

自动部署再次受生产服务器访问 GHCR 的速率影响，20 秒接收采样约 274 KiB/s，Web 拉取持续数分钟。
在核对 bootstrap 代码哈希、父子进程身份、原容器健康与发布锁后停止本轮拉取；
GitHub 运行整体结论为失败，不能把 CI 与镜像发布成功写成自动部署成功。

本次采用一次性人工差分中转完成镜像准备，没有修改仓内默认下载或上传脚本：

1. 根据成功 CI 日志的固定 digest 拉取三张 linux/amd64 镜像，核对 image ID、revision 与架构。
2. 核对三张镜像的全部文件层与线上 strict 版本 `b9dcb1d` 完全一致。
3. 容量检查后，在私有临时目录导出完整新镜像归档，并以服务器已有旧镜像归档作为 rsync 差分基础；
   SSH 严格主机校验保持启用。完整远端归档 SHA-256 与本机相同后才执行 `docker load`。
4. 导入后再次核对 CI 精确 image ID、revision、架构和文件层，逐项清理本地与远端归档。

| 服务 | 完整归档字节 | 实际发送字节 | 差分传输耗时 | 含导出、校验、导入总耗时 |
| --- | --- | --- | --- | --- |
| Web | 287776256 | 110305 | 4.16 秒 | 27.30 秒 |
| Core | 836760064 | 181437 | 26.97 秒 | 99.92 秒 |
| Agent | 269442048 | 99141 | 6.06 秒 | 30.34 秒 |

这里的实际发送字节来自 rsync 统计，不包含 SSH 和 TCP 的协议开销，也不等于完整归档大小。
三个完整归档的 SHA-256 分别为：

- Web：`52bf847708a5fa91ce65e0109a13871d010c81b91ecf4ca0fe77163490e8f086`。
- Core：`505dc20a68427ad3af3cd2e2e29f11c3e2347642c3b264ec5fb6f7de84acb89a`。
- Agent：`b2de5a5623b6b6e7f6e9bc30d7d737b95dd0a229206d7587ba44b31a3cc9a4b1`。

## 生产切换与回读

原 `scripts/upload-deploy-source.sh` 上传目标提交 bundle，原 `scripts/deploy-production.sh`
执行生产切换，退出码为 0；2026-10-01 10:22 UTC 前已完成 schema guard、Compose 健康和编排冒烟。
切换前只读核对未收敛 Task、Command、V2 Run 均为 0。未执行 DDL，结构指纹仍为
`ea1df9ad015cd8d811d6ab250a7098870aa2befcf0afa3273b845255a0ac11b2`。

| 服务 | CI 摘要 | 生产实际镜像 ID |
| --- | --- | --- |
| Web | `sha256:afdcbf8ef2471ba2f4313cc1505abf191df4a5d3ae9c8446cdaa07c11cc6cbe0` | `sha256:972c64ac1c96eaf78c009f6b547878cbae204eb258aae4bf1e3070deb5f91811` |
| Core | `sha256:9ca17845ae528bdf9fd2be53477ebe70204066ac203f8051423a844aa97271ac` | `sha256:76c4d6509e20433f1ed24aeaa83f7fa1845aab342e1f5b3081b44ade8d2a2f9f` |
| Agent | `sha256:6d080743ea0e2c3790d613b162c2631d5e50ca94c9fbb291dc4081cbd713bb96` | `sha256:5c934bf62940b97c0c27cab0fbaf0beb57e34ec8847e479430b0a0db53708644` |

生产源码 HEAD 与三业务容器标签均为 `e86b98b062838a6c6d8956bea98bc6e1ac5ec31a`，
公开 readiness 为 HTTP 200 且六项检查正常。回退标签精确保留上一版 `b9dcb1d` 的三个镜像 ID。
Core 容器 schemaReady=true、route=off、V1 fresh=true，部署 `.env` 中视频开关继续为 false；
源码 bundle、GHCR 临时认证和差分归档目录已清理，发布锁空闲。

实际 Agent 容器内的 HTTP 替身复验再次得到 `strictDefault=true`、45 个工具、
`/beta/chat/completions`、零真实供应商调用。发布后于 10:22:31–10:52:32 UTC 完成独立稳定观察，
跨度 30 分 1 秒，共 40 次有效采样：六个容器均健康、源码和镜像身份一致、零重启、无 OOM、
无采样规则匹配的业务错误日志；公开 readiness 均为 HTTP 200、ready。
未以本次无业务负载的健康检查代替模型实测、CRUD P95、SSE 或队列延迟验收。

观察期间追加了 PostgreSQL 连接、空闲事务及本轮新增失败 Task／Command／V2 Run 的只读计数。
追加时采样脚本曾因 `psql -c` 批量命令的结果输出方式解析失败，改为 stdin SQL 后恢复；
这是采样脚本问题，未修改业务或数据库。此后健康、镜像身份及新增数据库指标继续独立核对。
数据库指标共记录 30 次，连接数为 2–4（含采样连接，上限为 100），空闲事务及本轮新增失败
Task、Command、V2 Run 均为 0。观察结束时 Core 内存为 343.3 MiB / 448 MiB，
Agent 为 134.5 MiB / 640 MiB，Web 为 79.41 MiB / 320 MiB。
