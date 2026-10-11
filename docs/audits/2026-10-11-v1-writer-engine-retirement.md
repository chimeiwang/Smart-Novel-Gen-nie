# V1 作家编辑原则与引擎退役验收

日期：2026-10-11。状态：代码和本地验证完成，待 CI 与生产发布。

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
