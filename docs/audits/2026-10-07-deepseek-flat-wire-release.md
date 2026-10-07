# 2026-10-07 DeepSeek 工具参数平铺发布审计

状态：代码已推送并发布生产，完整 CI、镜像身份与新容器离线验收通过；用户随后通过 Web 重试，供应商拒绝新 Schema，尚未完成业务验收。

本轮按[平铺规格](../specs/2026-10-07-deepseek-flat-wire-study.md)实施。代码提交
`f0f1fda44fe386239e8fe6e54260fd8c2378805c` 已推送 `main`。

普通字段的正常值直接保持业务形状，省略与 null 使用不同状态标记；无参及真实空对象保留非空表示。
标记碰撞、JSON 字符串重叠或无法证明解码等价的联合保留最小判别。五个条件根联合直接表达业务字段，
完整分支条件保留；修正 nullable 父节点 const/enum 的投影，防止 Reviewer 的 patch/rewrite 条件在
模型可见 Schema 中丢失。历史业务参数按相同新 codec 重编码，原业务 Schema/Pydantic 仍完整复验。

两个 DeepSeek 适配器的重复 JSON 键拒绝静默覆盖。字段描述与合法形状示例依据实际 codec 生成；纠正提示
仅使用模型已见 Schema 的受约束字段路径、类型及固定示例，不回放坏参数或完整诊断。保持 strict、权限、
纠正预算、计费和业务规则；质量专用 wire 的独立哈希核对保持一致。

本地排除 macOS 不可用的部署脚本套件后，3860 项测试通过，1 个 warning，耗时 289.35 秒。
新核心测试 22 项、两适配器集成 345 项、运行时与提示 helper 65 项通过；独立复验 912 个合法样例全部
往返一致，45 工具、12 Operation 与章节写作 24 工具的离线核对通过。Ruff 与 Mypy 通过，Mypy 检查
134 个源码文件。被排除的部署脚本套件不能算作本地通过，须由完整 Linux CI 验证。

[CI 37628917230](https://github.com/chimeiwang/Smart-Novel-Gen-nie/actions/runs/37628917230) 的 Java、Python、Web、ci 汇总与镜像发布全部成功。Python 为
3931 passed、2 skipped、1 warning，耗时 262.54 秒；Ruff 和 Mypy 通过，Mypy 检查 134 个源码文件。
Java verify 为 BUILD SUCCESS，耗时 5 分 50 秒。

原发布清单 artifact ID 为 `11485678366`，ZIP SHA-256 为
`05c579bea25084cff21e612fe59c1d46b5150b2d9a38331b2199e3a87568ce42`，与 GitHub artifact digest 一致，
仓库 `load_manifest` 校验通过，清单保留于 release 目录。三服务镜像已在本机按固定 digest 拉取，
分别验证 image ID、OCI revision、linux/amd64 和 RepoDigests；未以源码相同替代镜像身份验证。

自动部署拉取 Web 时，64.7 秒采样显示整机接收约 37.8 KiB/s，该值不是镜像的精确吞吐。
核验唯一 pull PID `100535`、旧版 `f16eb344` 三服务 healthy 且尚无部署 bundle 后，仅对该 pull
客户端发送 SIGTERM。自动日志在 237.6 秒后以 143 退出，部署 job `112821669439` 为 failure，
源码上传与 SSH 部署步骤均跳过；这是受控结束拉取，不能记录成自然失败或自动发布成功。

确认父进程 `100300`、临时 GHCR 认证目录 `/tmp/inkforge-ghcr-q61nkiui` 已消失且部署锁空闲后，
开始新的独立中转：16 MiB 分片、最多三条 SSH 连接。三个镜像均通过逐片与完整归档 SHA-256、逐镜像容量预检、串行导入与导入后 CI 身份复验。

本轮真实重试前的生产 Operator 身份预检再次返回 `SECURE_CREDENTIAL_BACKEND_REQUIRED`。
没有绕过预检调用供应商或受理任务，不能宣称真实任务重试成功。生产历史失败参数的分析说明了包装层级
缺失；离线与替身测试不能替代供应商接受新 Schema 或任务完成的真实证据。


## 生产发布与独立回读

镜像缓存齐备后，经原 `upload-deploy-source.sh` 上传同一代码 SHA 的源码 bundle，以 `githubUser`
执行原 `deploy-production.sh`，退出 0，编排冒烟通过。没有并发自动与手动版本切换，自动 Actions
失败结论与本次手动恢复成功分别保留。用户原有未提交文件没有进入镜像或源码 bundle。

| 服务 | 生产运行镜像 ID |
| --- | --- |
| web | `sha256:70585c02a08420494c85d8ca87041e2cf26108df4f565ab9075a24c558e86295` |
| core-api | `sha256:c4f2f8d69f04cffa95c4d9e219690a44ebf3aa23800072fb8f745e6458af78c0` |
| agent-service | `sha256:46fe0edb00f471492fb7eb07bb9790d70bcfe683678cd9253f036696ef00b110` |

- 生产 HEAD、三服务标签、实际镜像 ID、OCI revision 与同轮 CI 清单精确匹配，架构为 linux/amd64。
  三服务 healthy，重启数均为 0，无 OOM；六个常驻容器全部健康，公网 readiness 的六项检查全部 ok。
- 原脚本的实时数据库结构指纹为
  `ea1df9ad015cd8d811d6ab250a7098870aa2befcf0afa3273b845255a0ac11b2`，与部署前一致。
- `.env` SHA-256 保持
  `a3ae0d5fad3d4c8ffbe1d852413ee9cff1cea81513333c2725b3869604ab396a`，运行中的视频开关仍为 false。
  没有执行 DDL、修改模型配置与计费预算、迁移业务历史或操作正式内容。
- `rollback-f0f1fda44fe386239e8fe6e54260fd8c2378805c` 的三张回滚镜像精确对应前版 `f16eb344`。
  本轮三个分片目录在确认所有权、权限与归档哈希后清理，源码 bundle 已清理，未删除生产镜像、卷或业务数据。

## 新容器离线验收

实际新 Agent 容器在正式非 root 身份下，离线编译 45 个注册工具与 12 个 Operation，章节写作保持
24 个工具；所有 wire 对象闭合、全必填、无空属性对象。7 个代表性往返覆盖 count 的正常值/省略/null、
大纲索引直接字段、多定位字段和构建器的继承/false。五个根联合均为直接业务对象，非法复审模式、
正文/选区冲突和缺失定位在 wire 阶段被拒绝。

质量报告专用 wire 的 SHA-256 为
`4727bd537e1eb5c584242ebf29a50b3a35a0e789d890aee4e10ee8b3bbae8633`，与改造前一致。
该探针没有调用供应商、Core、数据库或队列，也没有写入业务文件或产生计费；它证明新镜像的表示与
兼容行为，不证明真实供应商已经接受新 Schema，也不证明上一任务已完成。

## 用户重试后的供应商拒绝

用户通过 Web 重试后，2026-10-07 22:00:35（北京时间）的 Agent 日志确认任务
`cmuy6deofem44jww4b71ormtg` 在首次请求收到 HTTP 400，供应商请求耗时 137 毫秒，暴露 24 个工具。
完整错误为 `Invalid tool parameters schema : field anyOf: missing field type`，供应商 request_id 为
`f3c2f574-6ca0-48f8-b967-6ec3b93231bb`。端点为官方 `/beta/chat/completions`，模型为 `deepseek-v4-flash`。

这是供应商在模型生成之前拒绝请求 Schema，与前次 HTTP 成功后参数包装不匹配属于不同阶段。
新容器离线 Schema 和往返验证没有覆盖供应商对 anyOf 直接分支的实际解析限制，不能据此宣称修复完成。
操作员自身的安全凭据预检仍未通过；此次真实请求由用户在 Web 发起，没有绕过身份或计费。

本审计和规格状态以独立 `[skip ci]` 文档提交保存，不触发再次构建与部署；后续兼容修正另行验证发布。
