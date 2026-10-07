# 2026-10-07 模型与工具完整失败诊断发布记录

状态：代码已提交并发布生产，完整 CI、生产独立回读与离线日志验收通过；真实任务重试受作者身份预检阻断。

规格：[完整失败诊断](../specs/2026-10-07-complete-failure-diagnostics.md)。

## 问题与变更

任务 `cmuxxmplitdiyfz9s9ydp2r3g` 在 HTTP 成功后，两轮工具参数校验均失败，最终为
`MODEL_TOOL_PROTOCOL_RECOVERY_FAILED`。旧日志只留下工具名、分类和字符数，原参数无法恢复，
不能据此确认具体缺失字段。本轮补全后续诊断，不声称该业务问题已修复或真实重试成功。

失败诊断覆盖 HTTP、连接、超时、HTTP 200 响应协议、工具 JSON 与恢复前后数据、wire/业务/Pydantic
校验、授权与计费回报、工具执行、Core 回调、工作流降级、队列与 V2 执行。保留原参数、预期 Schema、
完整校验发现和无局部变量的异常链/调用栈；通用 ValidationError 同样保存完整结构，避免异常文本裁剪。

完整详情进入服务单行 JSON 和适用的 V1 帧正文，不进入公共错误、Core 回调、SSE、journal、快照、
正式内容或模型纠正提示。凭据、敏感数字和 URL 认证信息脱敏，推理内容排除；已脱敏异常与请求地址缓存
保护上层重复采集。附属诊断使用 D 序号，不计作真实模型尝试，并关联已有供应商响应和计费请求 ID。
日志设备或诊断序列化故障不替代原结果；strict、纠正预算、计费规则、业务 Schema 和终态逻辑不变。

## 提交与验证

- 代码提交：`f16eb34466798fffac2a41b8ce05590d13a2b6c0`，已普通推送 `main`，保留原有无关未提交改动。
- 本地除部署脚本套件外的全仓测试 3804 项通过；macOS 的 `/usr/bin/dd` 等环境差异未当作通过。
  最终 helper/DeepSeek/strict 163 项、AgentRuntime 61 项、计费与人工日志 69 项、Core 回调 36 项等专项通过；
  后续完整 Linux CI 验证实际提交，包含本机排除的部署套件。Ruff、Mypy 与文档检查通过。
- [CI 37610123022](https://github.com/chimeiwang/Smart-Novel-Gen-nie/actions/runs/37610123022) 的
  Java、Python、Web、汇总与镜像发布全部成功。Python：3882 passed、2 skipped、1 warning，193.06 秒；
  Ruff 通过，Mypy 检查 133 个源文件通过。Java verify 为 BUILD SUCCESS，耗时 5 分 46 秒。

## 已验证制品与发布

- 原发布清单 artifact ID：`11477202782`；原 ZIP SHA-256：
  `7fd6741b750f81f1dd17078f6a44226d0268cc4bf3e1bc2d2d583c31804d7fc1`，与 GitHub artifact digest 一致。
  仓库 `load_manifest` 精确验证 SHA、run ID、仓库及三服务集合。
- 本机只从固定 digest 拉取同轮 CI 三镜像，复验 image ID、linux/amd64、OCI revision 和 RepoDigests。
  未本机构建或生产现场构建，未用源码相同替代镜像身份验证。
- 自动部署进入 Web 拉取后，45.1 秒采样增加 5,598,934 字节，约 124 KB/s。核对唯一 pull PID、
  固定 digest、旧版三服务 healthy 和源码 bundle 不存在后，仅对该客户端发送 SIGTERM。
  自动日志记录 164.0 秒后以 143 退出，job 失败，源码上传及部署步骤均跳过；拉取父进程与临时
  GHCR 认证目录已清理。这是受控结束缓存拉取，不是自然网络错误，未取消版本切换或回滚。
- 随后在新私有目录执行 16 MiB 分片、最多三条严格 SSH 连接中转；每片及完整归档校验 SHA-256，
  每镜像保留容量预检和独立串行导入，导入后再次匹配 CI image ID。未复用旧发布状态。
- 经原 `upload-deploy-source.sh` 上传同 SHA bundle，由 `githubUser` 执行原 `deploy-production.sh`，
  退出 0，编排冒烟通过。自动 Actions 失败与手动恢复成功分别记录，不把后者改写为自动发布成功。

| 服务 | 生产镜像 ID |
| --- | --- |
| web | `sha256:a6af729ce483449c697c0ef1f8f548cf0d87ae952333f9c634382e5c34c3534e` |
| core-api | `sha256:5a2963708199b110c25cb1c534a1e5802660e328f2887dc7ec2054d5036efc7d` |
| agent-service | `sha256:36bff2d74d412e35461b434002f9d2709348f8176c2b6f65e08245c3c26ec088` |

## 生产独立验证

- 生产 Git HEAD、三服务标签、镜像 ID 和 OCI revision 精确对应代码提交与原 CI 清单。
  三服务 healthy，重启数均为 0，无 OOM；其余三容器健康。公网 readiness 为 ready，六项检查全部 ok。
- 原部署脚本实时结构指纹为
  `ea1df9ad015cd8d811d6ab250a7098870aa2befcf0afa3273b845255a0ac11b2`，与部署前一致。
- `.env` SHA-256 保持
  `a3ae0d5fad3d4c8ffbe1d852413ee9cff1cea81513333c2725b3869604ab396a`，运行中视频开关仍为 false。
  没有执行 DDL、改变模型预算、修改配置或操作业务内容。
- `rollback-f16eb34466798fffac2a41b8ce05590d13a2b6c0` 的三镜像精确对应上一版 `8423e37` 的运行镜像。
  本轮三个分片目录在核对目录权限、归档哈希后清理，部署 bundle 已清理；没有删除生产镜像、卷或数据。
- 在新 Agent 容器、正式非 root 身份下运行离线日志 canary：ModelRuntime 经真实日志 helper 和
  HumanWorkflowLog 写入独立临时目录。超过 64 KiB 的错误参数与 Schema 完整保留，人工日志共
  302851 字节；2 个 D 帧，真实模型调用为 0，下一模型尝试序号仍为 1。凭据和 reasoning 未泄露，
  伪造帧文本不能改变结构，普通序列化/repr 不含详情；临时目录已自动清理。
- canary 未访问供应商、Core、数据库或队列，不产生计费。它证明新容器的日志行为，不代替真实任务验收。

## 尚未完成的业务验证

本轮生产 Operator `auth.whoami` 仍返回 `SECURE_CREDENTIAL_BACKEND_REQUIRED`。按其恢复规则停止业务命令，
未通过 SSH、数据库、内部接口或明文令牌绕过身份预检重试任务。用户后续通过 Web 重试时，新失败将保留
完整诊断；不能把此次日志补全等同于上一任务已完成或候选已生成。

本审计及规格状态为发布后文档补记，以独立 `[skip ci]` 提交保存，不触发重复构建与部署。
