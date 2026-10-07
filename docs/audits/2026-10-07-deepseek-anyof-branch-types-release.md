# DeepSeek anyOf 分支类型兼容修正发布审计

本轮修复代码为 `25c2e099178540579ca6f83309c9ff26db9e08be`，规格先行提交为 `51189d4`。
依据为[平铺规格](../specs/2026-10-07-deepseek-flat-wire-study.md)的“供应商 anyOf 兼容修正”。
状态：代码已推送 main 并发布生产，完整 CI、独立回读及容器离线探针通过；真实任务仍待用户重试确认。

## 问题与修改

上轮用户真实重试任务 `cmuy6deofem44jww4b71ormtg` 在 137 毫秒内收到 HTTP 400：
`Invalid tool parameters schema : field anyOf: missing field type`。
写作 24 工具的 nullable、可选字段及根条件属性合并产生了直接嵌套的无 type 联合分支；
通用 JSON Schema 接受该形状，不能证明供应商接受。

本轮仅把只有 anyOf 和 description 的纯联合等价展开，保留字段、分支说明与全部约束。
带 type/properties 的条件对象继续保留完整条件，不给标量联合伪造 object 类型。
请求准备时预检 anyOf 直接分支，只接受 object/string/number/integer/boolean/array；
预检失败沿用准备阶段错误诊断，并在已生成时保存完整 wireSchema。
正常值平铺、省略/null 标记、碰撞判别、历史业务参数重新编码和最终业务校验不变；质量 wire 不变。

专项回归覆盖 45 工具、12 Operation 和写作 24 工具，以及展开前后有效值、说明保留、
条件对象约束、非法分支类型与历史往返。最终四 Provider 文件 396 项通过；
更广 Provider/Runtime 在追加类型白名单用例前为 727 项通过。全仓 Ruff、Mypy 134 文件和差异检查通过。

## CI 与固定镜像

[CI 37635382578](https://github.com/chimeiwang/Smart-Novel-Gen-nie/actions/runs/37635382578)
的 Python、Java、Web、汇总及镜像发布均通过。Python 为 3960 passed、2 skipped、1 warning，
耗时 256.5 秒；Ruff 和 134 个源文件的 Mypy 通过。Java 作业 `112840096711` 为
BUILD SUCCESS，耗时 6 分 44 秒；Web 作业 `112840096507`、发布作业 `112843594435` 成功。

发布 artifact 为 `11490325612`，ZIP SHA-256 为
`373aac963901e997782018e4e2c2dd6365a4da69e1a594f361cdb3df14f9ffec`。
原 CI 清单 `inkforge-release-25c2e099178540579ca6f83309c9ff26db9e08be-37635382578.json` 经
ZIP digest 与仓库 load_manifest 校验。来源 main push、仓库、工作流、run/SHA 及唯一有效 artifact 均核对。
本机按固定 digest 预加载 Web、Core、Agent，分别耗时 9.5、9.9、19.2 秒；
已核验 digest、imageID、revision、linux/amd64 与 RepoDigests。

## 自动拉取受控停止与恢复准备

自动部署作业 `112844597888` 的生产拉取缓慢。102.9 秒采样显示整机接收约 105.1 KiB/s，
这是整机网络速率，不能作为镜像精确吞吐。只读核验固定唯一拉取 PID `140270`、
父进程 `140044`，当时旧 `f0f1fda` 的三服务健康，尚无本轮部署 bundle。
随后仅对已确认的拉取进程发送 SIGTERM：拉取记录 242.8 秒，退出 143，自动作业受控失败，
upload/SSH 步骤均 skipped。父进程与临时认证目录 `o7di1pu8` 已消失。

独立 relay 使用 16 MiB 分片、最多三条严格 SSH 连接，保留逐镜像容量和逐片/完整归档 SHA-256 门禁。
Core 部分分片曾传输失败，经有界重试后全部成功；三镜像串行导入并全部通过身份复验后，才统一打新 SHA 标签，
最后再次确认全部目标标签的镜像 ID。relay 退出 0，没有并发运行自动与手动版本切换。

## 真实任务验证边界

生产 Operator 的 `whoami` 身份预检再次返回 `SECURE_CREDENTIAL_BACKEND_REQUIRED`。
本轮未通过该入口触发模型调用，不能声称真实重试成功；原 HTTP 400 任务也没有被恢复为成功。
离线 Schema 回归和后续 canary 只能证明各自范围内的行为，不能替代用户真实写作任务结果。

## 生产部署与独立验证

原 `upload-deploy-source.sh` 上传同一 SHA 的源码 bundle，原 `deploy-production.sh` 以 githubUser 身份执行，
退出 0；全部编排健康及冒烟检查通过。部署前确认发布锁空闲与旧三服务健康，没有执行 DDL 或修改运行配置。
用户已有未提交改动没有进入提交、镜像或源码 bundle。

| 服务 | 生产镜像 ID |
| --- | --- |
| web | `sha256:26fa562878d8107145f83123ff4d199f9c4f796ce542e9b868705c1ec65a0ffd` |
| core-api | `sha256:624740fe40405cffeecf1985019f7d029b58e5741f7f2513cc7111188b7da4fa` |
| agent-service | `sha256:c2dd597bf499bf36974ca52579e9b562e8b3a2d9994ead8dab653a4f49b1579c` |

独立回读确认生产 HEAD、三服务标签、镜像 ID、OCI revision、linux/amd64 与本轮可信清单一致；
三服务健康、重启计数为 0、无 OOM，公网 readiness 六项检查全部 ok。
`rollback-25c2e099178540579ca6f83309c9ff26db9e08be` 的三张回滚镜像均为前版 f0f1fda 的原镜像。

数据库结构指纹仍为 `ea1df9ad015cd8d811d6ab250a7098870aa2befcf0afa3273b845255a0ac11b2`；
环境文件 SHA-256 仍为 `a3ae0d5fad3d4c8ffbe1d852413ee9cff1cea81513333c2725b3869604ab396a`，
视频开关保持 false。没有数据库迁移、正式内容写入或真实供应商调用。

在实际新 Agent 容器的原非 root 身份运行纯编译探针，独立递归检查 anyOf 直接分支的具体类型，
没有复用新增方言校验器作自证。45 注册工具、12 操作收窄结果、写作 24 工具、5 个根联合、
7 个代表性三态及常用字段往返与非法条件拒绝全部通过。
质量专用 wire 的 SHA-256 为 `4727bd537e1eb5c584242ebf29a50b3a35a0e789d890aee4e10ee8b3bbae8633`，
保持不变。该探针 provider/Core/database 调用均为 0，不能代替真实供应商接受或业务任务完成的证据。

原脚本已清理源码 bundle。三个中转目录在核对固定目录范围、所有者、0700 权限、文件集合和完整归档哈希后清理；
Docker 数据目录剩余可用空间为 3437932544 字节，没有删除镜像、卷或业务数据。
自动部署受控失败与本次手动部署成功分别保留；本审计和规格状态以独立 `[skip ci]` 文档提交保存。
