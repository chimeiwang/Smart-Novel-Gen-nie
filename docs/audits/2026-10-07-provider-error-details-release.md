# 2026-10-07 模型错误诊断发布记录

状态：第一轮日志修补已发布生产；用户重试已复现 HTTP 400 并确认空对象 Schema 原因，根因修复与第二轮发布进行中。

规格：[完整错误诊断](../specs/2026-10-07-provider-error-details.md)。

## 提交与验证

- 修补提交：`35213d96d0498d3197bf3c53be0dd60ae4f9a106`，已普通推送 `main`。
- 本地相关测试、Ruff、Mypy 与文档检查见规格记录。
- [CI 37576137684](https://github.com/chimeiwang/Smart-Novel-Gen-nie/actions/runs/37576137684)
  的 Java、Python、Web、汇总与镜像发布全部成功。
- 自动部署失败在镜像拉取入口的 SSH 建连阶段：`Connection reset ... port 22`、`PULL_REMOTE_FAILED`。
  此时没有上传源码 bundle 或切换容器；不能把该次失败解释成已证实的 GHCR 下载错误。

## 已验证制品与人工恢复

- 原始发布清单 artifact ID：`11462679895`，绑定上述 SHA 和 CI run。通过已连接 GitHub 工具取得
  原 ZIP，校验 SHA-256 为 `10a9a4f99b88548ee1452aac20704eb06653653671a919cc7aa85f7b865f902a`，
  并通过仓库 `load_manifest` 的固定仓库、服务集合、SHA、run ID 和字段校验。
- 本机按三个固定摘要拉取，复验 CI image ID、`linux/amd64`、OCI revision 与 RepoDigests。
  本机和 Runner 的 Docker 逻辑大小存在少量口径差异，容量预检使用实际值与清单值中的较大者，
  镜像身份仍要求精确匹配。
- Web 使用原归档传输流程完成导入。Core 的长连接上传降速后结束了本轮精确传输，原脚本清理其临时文件。
  服务器按固定摘要直接拉取也较慢，结束本轮精确拉取客户端后，Core/Agent 改为一次性分片中转。
- 分片为 16 MiB、最多三个严格 SSH 连接，各片有界超时、有限重试、独立 SHA-256；合并后再次
  校验完整归档哈希。每镜像预检包括两倍逻辑大小、两倍归档大小与 512 MiB 余量；导入串行且有界，
  导入后再次核对同一 CI 身份。中间三个分片首次失败后重试成功，未绕过校验或替换镜像来源。
- 三图齐备后，经原 `upload-deploy-source.sh` 上传同 SHA bundle；使用 `githubUser` 执行原
  `deploy-production.sh`。临时中转没有成为新的默认发布入口，原 Actions 自动部署结论仍为失败。

| 服务 | 生产运行镜像 ID |
| --- | --- |
| Web | `sha256:084f379414d0f7d6787803ec5be5a9acb4b863fd928461a850a742181992d2d3` |
| Core | `sha256:283fdf8d40ddca7ada9a2f86c0f8d207aa8d79322f3f465955765cc4074db33c` |
| Agent | `sha256:868bb03118435a656ed27171b11797a0417d5377ec99df7c6f0590da836a7b9e` |

## 生产独立回读

- 原部署脚本退出 0，编排 smoke 通过；实时结构指纹为
  `ea1df9ad015cd8d811d6ab250a7098870aa2befcf0afa3273b845255a0ac11b2`。
- 生产 Git HEAD 和三服务标签均为 `35213d96d0498d3197bf3c53be0dd60ae4f9a106`，三运行镜像 ID
  精确匹配原 CI 清单，全部 healthy，重启数均为 0，无 OOM；其余常驻容器同样健康。
- 公网 `/api/v1/health/ready` 返回 ready，database、database_schema、agent、redis、background_tasks
  和 writing_outbox 全部为 ok。
- `.env` 发布前后 SHA-256 相同；没有 DDL、数据库恢复或配置开关调整。精确旧镜像保留于
  `rollback-35213d96d0498d3197bf3c53be0dd60ae4f9a106`。
- 本轮两个分片目录与部署 bundle 已清理，未清理任何生产镜像、卷或业务数据。

## 未完成边界

本次生产 Operator 的 `auth.whoami` 仍返回 `SECURE_CREDENTIAL_BACKEND_REQUIRED`。只读系统检查发现
默认钥匙串锁定，尚未取得成功的作者身份预检；已请求用户解锁。按 Operator 恢复规则停止业务命令，
未通过 SSH、数据库、内部接口或明文令牌绕过登录重试作品任务。

初次发布后检查尚无新的供应商失败日志；该时点尚未复现，后续证据如下。本审计与根因修复一并提交。

## 用户重试与根因

- 用户通过 Web 手动重试，任务为 `cmuxtoeay3d51uct1g5ft786i`；北京时间 2026-10-07 16:05:13
  的 Agent 服务日志捕获 HTTP 400，耗时 227ms，4 条消息、24 个工具，输出上限仍为 384000。
- 原始错误说明为 `An object with no properties is not allowed.`，类型与 code 均为
  `invalid_request_error`，请求 ID 为 `9ea04109-4ce2-47bf-ade9-81357e686d15`。
  失败地址为 `https://api.deepseek.com/beta/chat/completions`。
- 离线编译当前章节写作工具集合，17 个工具包含共 32 个空属性对象，十个来自无参根对象，其他来自
  可选字段缺省及 null 表示。与服务端返回的 Schema 校验原因一致，不需要猜测 max_tokens 或禁用 strict。
- 本次只读日志诊断不通过业务登录绕过写入；修复设计见[空对象兼容规格](../specs/2026-10-07-deepseek-strict-empty-object.md)。
- 同一错误也已从人工工作流日志的可信 `model_failure` 正文完整回读，文件为
  `/data/agent-logs/2026-10-07/ebab08d062b4fc8d.log`；结束帧时间为 08:05:13.862064 UTC，状态为“错误”。
  服务日志和持久人工日志均确认第一轮采集修补生效。

## 根因修复本地验证

固定标记仅替换供应商层的无属性对象，保留原业务类型、strict、模型、额度及调用次数。Provider/Runtime
611 项回归、最终 strict 专项 43 项、全仓 Ruff 与 133 源文件 Mypy 通过；尚待本次 CI 和第二轮发布。
生产 CLI 身份预检仍返回安全凭据后端错误，不能通过该入口执行修复后真实模型重试。
