# 2026-10-07 模型错误诊断发布记录

状态：两轮修补均已发布生产；用户重试已确认空对象 Schema 原因并完成修复，修复后真实模型调用尚待复验。

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
611 项回归、最终 strict 专项 43 项、全仓 Ruff 与 133 源文件 Mypy 通过；正式 CI 和第二轮发布结果见下文。
生产 CLI 身份预检仍返回安全凭据后端错误，不能通过该入口执行修复后真实模型重试。

## 第二轮提交与发布

- 修复提交：`8423e37bd198e234b75c0aa3ef313f4df1f8c9dd`，已推送 `main`。
- [CI 37593756907](https://github.com/chimeiwang/Smart-Novel-Gen-nie/actions/runs/37593756907) 的
  Java、Python、Web、汇总与镜像发布全部成功。Python 共 3809 项通过、2 项跳过、1 条警告，耗时
  258.04 秒；Ruff 通过，Mypy 检查 133 个源文件通过。
- 原发布清单 artifact ID 为 `11470586282`；原 ZIP 的 SHA-256 为
  `0a3dc93ab618b173f402f265227fdb2ad4de99b92710889f2ff7605394deb9f4`，与 GitHub artifact digest
  一致，仓库 `load_manifest` 精确验证 SHA、run ID、仓库和服务集合。
- 自动部署停留在首个 Web 镜像的慢速拉取。核对唯一 pull PID、固定摘要、旧版三容器和不存在的源码
  bundle 后，人工仅对该 pull 客户端发送 SIGTERM。该步骤在 471.7 秒后以 143 退出，自动 job 失败，
  后续源码上传和部署步骤均跳过；父进程、pull 进程和临时 GHCR 认证目录均已清理。
  这是受控结束缓存拉取，不是自然网络错误，也没有取消正在执行的版本切换或回滚。
- 在新的发布临时目录按同轮固定 digest 拉取三镜像，复验 CI image ID、linux/amd64、OCI revision
  和 RepoDigests。使用上一轮相同的 16 MiB 分片、最多三个严格 SSH 连接、容量和哈希门禁中转，
  每镜像串行导入后精确复验；未现场构建、复用旧发布状态或改动发布默认流程。
- 三镜像齐备后，由原 `upload-deploy-source.sh` 上传同 SHA bundle，以 `githubUser` 运行原
  `deploy-production.sh`，退出 0。自动 Actions 的失败结论与本次人工恢复成功分别保留。

| 服务 | 第二轮生产镜像 ID |
| --- | --- |
| Web | `sha256:e714ece1b8a35a756a3495d044497088c8d98df811f67597a7818c5786ddb8bd` |
| Core | `sha256:67ce7bcbd025445f22c4188d6672d785157750f0ad845965ca90cff0bfab6371` |
| Agent | `sha256:1ecf5c15a25fed9cfb76b1e6bcc792c65bdf95c6d6472400d4d6c56b683f56d7` |

## 第二轮生产独立回读

- 生产 Git HEAD、三服务标签、镜像 ID 和 OCI revision 均对应上述修复提交及 CI 清单。
  三服务 healthy，重启数均为 0，无 OOM；其余常驻容器健康。
- 原脚本的实时结构指纹与第一轮相同，编排冒烟通过；公网 readiness 返回 ready，六项检查均为 ok。
- `.env` SHA-256 与第一轮相同，运行中视频开关保持 false；未执行 DDL，未改模型额度和计费配置。
- 旧版三镜像保留在 `rollback-8423e37bd198e234b75c0aa3ef313f4df1f8c9dd`，精确对应第一轮运行镜像；
  本轮三个远端中转目录与源码 bundle 已清理，没有清理业务数据、卷或生产镜像。
- 新 Agent 容器内纯编译 `write_chapter` 实际 24 个工具，空对象 Schema 节点数为 0，没有请求供应商。
  用户的修复前重试已提供根因证据；修复后真实调用、任务完成和候选生成尚未验收，不能由上述检查代证。
- 本段是发布后的纯文档补记，单独以 `[skip ci]` 提交，不触发重复构建和再次部署。
