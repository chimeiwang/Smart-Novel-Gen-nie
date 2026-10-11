# 单引擎发布与首次退役

适用规格：[2026-10-11 作家能力与执行器退役](specs/2026-10-11-v1-writer-and-execution-retirement.md)。
本手册定义步骤，不证明任何一次生产发布已完成；本次证据记录到 `docs/audits/`。

生产状态更新：2026-10-11 用户要求恢复旧代码，现网已回到 `25c2e099`，写作仍走 V1、V2 fresh 路由 off。
当前仓内退役实现保留待后续定位，不能据本手册认定生产已运行新栈。见[回滚审计](audits/2026-10-11-production-code-rollback.md)。

## 前置核对

- 源码、Java／Python／Web CI、不可变镜像清单必须绑定同一提交；服务器不构建镜像。
- `VIDEO_PREVIEW_ENABLED=false`，旧引擎新建路由为 off。生产既有表、历史来源与账务不删除，不执行 DDL。
- 新镜像离线验证：Core `RetiredEngineProbe` 证明历史结构与来源可读、执行器类不存在；Agent 不含 execution 包，普通队列与 Episode handler 可导入。
- 私钥、数据库连接、文件权限、服务器容量与严格 SSH 身份校验继续沿用生产部署门禁。

## 切换

1. `scripts/deploy-production.sh` 取得服务器互斥锁，冻结实际运行三容器的不可变镜像 ID，并保存旧编排及其配置依赖。
2. 只读验证实时 PostgreSQL 精确匹配结构契约；所有旧引擎 Run/Step 已终态、执行日志与回调已排空。查询错误、索引损坏或仍有在途任务时停止，不删记录、不伪造终态。
3. 保存受权限保护的 PostgreSQL custom dump、旧执行日志快照、排空计数和 SHA-256。未知账务保持挂账，在发布结果中明确报告。
4. 三张 CI 镜像均验证后，使用 `compose up --no-build -d --wait` 切换，刷新 Nginx，再验证健康、实时 schema 以及 Agent 日志目录写入。
5. 新栈通过后停止旧执行日志服务；保留容器、卷和备份用于首次退役回滚，后续运行不再依赖它。

## 回滚

任何切换、schema 或 smoke 失败时，恢复冻结镜像与其旧编排，不用新编排强行启动旧 Agent。
再次验证健康、schema 与 smoke，保留原发布失败退出码。回滚不删除卷、不回退 DDL、不改小说内容。

首次退役后的普通版本回滚只允许兼容历史来源和账务的新栈。旧引擎恢复点只用于本次受控发布失败恢复，
不能用它重新开放已经移除的新建功能。历史 `DURABLE_AGENT_V2_ROLLOUT.md` 中的 rollout gate、manifest、
联合 drain、旧任务 archive 和 execution journal 恢复步骤均已退役，不作为当前栈的运维入口。
仓库中的旧恢复脚本仅供历史追溯；不能在新栈调用依赖已删除 execution Redis 配置的脚本。
本次应用失败恢复使用被冻结的旧编排和原卷；数据库或日志灾难恢复须另行确定目标及恢复方案。

## 验收记录

分别记录提交／CI、镜像传输、容器切换、readiness、schema、恢复点、真实 V1 业务任务回读。
提示词变化需另用新生成文本判断文风；测试或部署成功不代表已通过任何第三方 AI 检测。
视频迁移只做隔离验证，生产仍关闭，不发起真实 Seedance。
