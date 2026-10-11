# V1 作家编辑原则与引擎退役验收

日期：2026-10-11。状态：代码已提交并部署；真实写作试跑受 Keychain 阻塞，用户随后反馈朱雀检测特征升高，文风效果未通过验证。

## 范围

用户授权作家提示词改进，并明确选择完整移除 V2 引擎、迁移仍依赖的功能，完成后提交部署。
实施于独立工作树 `codex/v1-writer-natural-retirement`，基于 `9abb98c`；原工作树 Operator 和文档的未提交改动保留。

- 作家初稿和返工共享六项编辑原则，不新增 Agent、模型轮次、检测器或检测分数门禁。
- 删除 Core 调度器、Agent execution 包、专属注册表资产与单 Step 回调；新任务使用 V1。
- Episode 四操作迁入普通视频队列及 Core 业务检查点。冻结来源、范围外保留、候选采用、正式确认分离。
- 保留历史结构、来源、候选、版本、账号与账务；本次无数据库 DDL 或历史行清理。
- 历史结构开关独立为 `HISTORICAL_WORKFLOW_SCHEMA_READY`，兼容旧环境配置，不启用旧执行器。
- 首次退役发布保存旧镜像、Compose 及配置依赖、数据库与旧日志备份；排空不完整时不切换。

## 已取得的验证

- Python Agent／共享契约／鉴权及专项架构测试 2308 项通过；Mypy 与 Ruff 通过。
- Web 测试、typecheck、lint 和 build 通过；普通 CLI 全套 147 项通过。
- PostgreSQL 视频任务和候选采用回归通过，包括完整／局部修订、范围外逐字保留、重复完成、取消和检查点。
- 部署脚本的镜像传输、锁、失败回滚、历史结构和退役备份专项测试通过；新预检在 Python 3.10 与 3.12 各通过 28 项测试，覆盖生产 Python 3.10.12。
- `npm run api:check` 无漂移；公共操作仍 182 个，内部操作为 25 个。
- 全量 Python 2813 项通过（242.16 秒）；之后补充 Episode 权威终态日志，11 项相关回归、Ruff 与 Mypy 再次通过。
- 全量 Maven verify 通过，Core 3 项既有环境跳过；最后补充的历史幂等回归 4/4 通过并重新打包。
- 最终 fatjar 离线探针：`engineRetired=true`、`legacySchemaSupported=true`；不含旧执行器、注册表和 execution 资产。

## 发布前生产只读核对

通过严格 SSH 核对：Web／Core／Agent 仍运行 `25c2e099178540579ca6f83309c9ff26db9e08be`，六个现有容器健康。
当前旧路由 off、V1 fresh=true、video=false；权威 PostgreSQL 非终态 V2 Run 为 0，旧日志 active 索引为 0。
上述不是完整退役预检，实际切换仍须检查 Step、全部回调和备份。

## 业务验证边界

生产 Operator `auth.whoami` 返回 `SECURE_CREDENTIAL_BACKEND_REQUIRED`，本机 Keychain 不可用。
因此暂未通过作者身份启动或回读新的生产写作任务；没有替换作者正文或自动采用候选。
生产运维和容器验证独立进行，不用离线提示词探针冒充真实生成质量。

普通 V1 的未知供应商调用没有持久化 grant 签发账本。Episode 保存完整 started 检查点并停止自动重调，
未知实际用量仍需对账；不能声称自动结算成功。历史 V2 的未知预留仍保留原对账入口。
所有冻结来源章节都已删除时，新的 Episode 任务明确要求重新选择来源，不绑定无关章节。

## 首轮发布与预检修正

首轮实现提交 `fde58adf6dd034ddf926945856f905ce3dc98003` 的 Python、Java、Web CI 与镜像发布通过，
工作流为 `38130596007`。生产直接拉取 GHCR 过慢，终止了经进程身份确认的镜像下载，自动部署在切换前结束；
暂存凭据已由原流程清理，生产服务仍使用原版本。

只读预检发现真实 psql 14 在多语句 `-c` 中只回报末条 COMMIT，统计 JSON 为空。
修正为单条 SELECT 的一致快照，会话只读约束保持不变。新增隔离 PostgreSQL 14 回归，验证真实输出、
写操作被拒及数据不变；22 项预检测试在 Python 3.10 和 3.12 均通过，Ruff 与 diff 检查通过。
修正后通过生产只读查询确认活跃 V2 Run、未完成 V2 Step、未结算预留均为 0。
为保持提交、镜像和运行代码一致，原提交的本地中转上传在切换前停止，修正提交重新走 CI 与镜像发布。


## 冒烟与旧日志实测补充

复核发现冒烟仍调用已移除的 execution-redis，且回滚冒烟固定使用新 Compose。
已删除退役服务探针，并让部署显式传递当前编排路径；保留真实上传／日志目录创建清理及连续 Agent 就绪检查。
新增新栈／回滚编排回归，以及回滚后全部冒烟命令使用冻结旧编排的断言。
旧日志备份另使用 Redis 7.4、旧配置、只读根目录、用户 999:999 和独立命名卷实测：
Lua 排空、RDB 导出、redis-check-rdb、docker cp 和临时文件清理均成功，原测试数据保留。
部署、冒烟及 Compose 安全回归合计 92 项通过，Ruff、shell 语法和 diff 检查通过。
当前隔离 schema 探针已在生产旧 Core 上执行成功，指纹为
`ea1df9ad015cd8d811d6ab250a7098870aa2befcf0afa3273b845255a0ac11b2`，未修改数据库。

## 最终发布身份与传输

生产代码提交：`1bbf509b858e8b4f4788fdd4eb2a623f2075f906`。
[CI 工作流 38132464893](https://github.com/chimeiwang/Smart-Novel-Gen-nie/actions/runs/38132464893)
的 Java、Python、Web、汇总 CI 与三镜像发布均通过。
清单 artifact `11699348288`，ZIP SHA-256 为
`cded117543e62366c55a3b16bc3b8b38f0b4b3e23f7d8b0206099a76230427bf`，已重新下载并校验。

自动 deploy 在拉取首张镜像时因速度问题受控终止。终止前核对了 Docker pull 的完整 digest、父进程和
远端引导代码 SHA-256；原引导程序正常失败退出并清理临时 GHCR 凭据。该 deploy job 保持 failure，
不能记为自动发布成功。之后仅运行一条手动中转路径，复用本次 CI 的可信镜像，没有服务器现场构建。

本地按 digest 拉取，逐一校验 image ID、OCI source revision、linux/amd64 和 RepoDigests；
传输沿用严格 SSH、容量检查、归档 SHA-256、逐镜像导入与临时文件清理。
生产 docker load 后以可信清单 image ID 为权威，不以不存在的 RepoDigests 冒充摘要验证。

| 服务 | CI digest | CI image ID |
| --- | --- | --- |
| web | `sha256:487712fc7e4ecd14bd74f4b7e62cc7be13ffb235a686d9f1aab96d7231d19cd4` | `sha256:cd8e4385b30d821861d73d44879947696167d8bd4cee4c35049fe07c5ccc1bd8` |
| core-api | `sha256:060d566d27a8b30ef225def722561fd2625715857cedd9de42b51c32304d1eac` | `sha256:db8fc7b10f5a8b44973e01510870981ed263e3ec01a56f792ae2249b3ca12f5c` |
| agent-service | `sha256:926dd5a3af121c837426455c3a6d98bd210cee57d1ebbb3092d1a2b773df0fa1` | `sha256:3ca6e5b1db897bb7e8314cac1046a6f7b822d4908b45bf6696c93b8483badf85` |

## 实际切换与恢复点

最终部署脚本退出码为 0，生产源码 HEAD 与 Web／Core／Agent 三张运行镜像均绑定 `1bbf509b`。
公网 HTTPS readiness 返回 ready，各依赖检查均 ok；Compose 冒烟的公共页面、内部接口隔离、连续 Agent 就绪、
上传及人工日志目录真实 mkdir/rmdir 均通过。当前五个常驻容器健康，旧 execution Redis 正常退出（exit 0），
旧容器和命名卷保留，当前栈不依赖该服务。

切换前后真实 schema 指纹均为
`ea1df9ad015cd8d811d6ab250a7098870aa2befcf0afa3273b845255a0ac11b2`。
没有执行数据库 DDL、删除历史行、自动采用候选或替换小说正文。
历史结构读取开关在运行 Core 中为 true，V1 fresh=true；生产编排未注入视频开放开关，视频仍按默认 false 拒绝调度。

恢复目录：`/srv/inkforge-backups/retirement-1bbf509b858e8b4f4788fdd4eb2a623f2075f906-20261011T105216Z`。
目录权限 0700，备份文件 0600；重新读取文件并计算 SHA-256 验证一致：

| 文件 | 字节数 | SHA-256 |
| --- | --- | --- |
| database.dump | 27681760 | ce56edb997069affb9e98ea36b69144d837f826a58587a8457345d5299c4db57 |
| execution-journal.rdb | 222 | 9637ce30f4712a9e116ab72bf611a78dcee431cbfade5b605770128f92feb40a |
| facts.json | 315 | bf31afa695318427dd1cd7b03cbfa1472687825c7c68f4a287223916e9da1c9d |

备份事实：activeV2Runs=0、nonterminalV2Steps=0、unsettledReservations=0，旧日志 active/pending/leased/rejected 均空，未隔离。
三个 `rollback-1bbf509b858e8b4f4788fdd4eb2a623f2075f906` 镜像仍精确对应原生产 `25c2e099`；
冻结旧 Compose、Redis 与 Nginx 配置依赖完整保留。此次未触发实际生产回滚；回滚逻辑通过专项测试，不能写成已做真实回滚演练。
源码 bundle、GHCR 临时凭据与镜像上传临时目录已清理，部署锁已释放。

上线后再次通过固定生产 Operator 调用 auth.whoami，仍为 SECURE_CREDENTIAL_BACKEND_REQUIRED。
没有绕过 Keychain，通过 SSH／数据库创建写作任务；新正文质量、CRUD P95、SSE 首事件及真实任务延迟仍没有本次业务实测证据。

## 上线后的文风反馈与待定位问题

用户于同日反馈，使用改动后生成的文章在朱雀检测中的 AI 特征反而更明显。该反馈记录为效果回归，
不能用 CI、容器健康或发布成功替代生成质量验证。当前尚未收到此次检测对应的新正文、任务身份和逐轮候选，
不能判定哪条提示词、哪轮返工或哪种检测切分导致变化；本次没有据此自动重改或回滚生产提示词。

只读代码核对确认：六项原则是作家固定 system 要求，没有携带此前被认可的具体修改对照样例；
reviser 的执行 brief 同时仍要求“完整重写”，与作者提示中的保护有效内容存在解释张力。
作品文风画像需要实际调用 get_style_profile，正文初始上下文不自动注入；正文返工默认只带权威草案、
修改要求等输入，不自动重放此前读取的画像。两位 reviewer 的局部 patch 可直接进入候选，未经过作家。
上述后续改稿和资料读取行为原本就存在，不能仅凭代码可能性认定它们造成此次检测上涨。
后续需要对照同次任务的初稿、reviewer 修改要求、patch／返工稿及最终检测文本，定位首次变化环节。

## 稳定性观察结果

北京时间 18:54:36—19:23:47 完成 31 次稳定采样，跨度 29 分 10 秒。
会话中断后，20:38:41 再次回读运行状态，20:41:09—20:43:29 又完成 7 次采样，跨度 2 分 20 秒。
两段采样窗口合计超过 30 分钟；中间存在观察空档，不能写成连续 30 分钟采样。

所有上述稳定采样的三服务镜像均与 CI 清单一致，五个常驻容器健康，readiness 全部通过，
容器重启计数均为 0，无 OOM，无 Core／Agent 新错误关键词命中。数据库连接 1–4；
一次采样出现空闲事务，随后只读 pg_stat_activity 复查无持续事务，后续采样恢复为 0。
等待队列始终为 0，期间处理中最多 1 项任务，最终 ready/processing 均为 0。
队列归零不能替代作者身份下的任务、候选和正文权威回读，因此不据此宣称写作质量验证通过。

原工作树已有未提交改动完整保留；本次代码、补充修复与文档位于独立工作树。
本审计及规格状态更新只记录事实，使用文档提交，不重新发布镜像；生产代码仍为 `1bbf509b`。
