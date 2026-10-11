# 2026-10-11 生产代码回滚审计

北京时间 22:47:23 独立回读确认成功。用户明确要求“先还原生产的代码吧”。

## 结果与范围

生产专用 Git 检出、Web、Java Core 和 Agent 全部恢复至本次发布前版本
`25c2e099178540579ca6f83309c9ff26db9e08be`。复用发布前冻结的精确镜像和旧 Compose，
没有重新构建镜像，没有执行 DDL、恢复数据库旧备份或编辑小说正文。新生成的候选、正文、版本和账务均保留。
Git main 中本次实现保留供定位，本次仅提交回滚规格、授权边界和审计，不触发新镜像发布。
原开发工作树已有未提交改动保留。

## 过程中的失败与修正

第一次尝试中，旧栈已健康、结构探针通过，但把完整冻结 Compose 叠加为旧冒烟 override 导致
`services.agent-service.security_opt items at 0 and 1 are equal`，冒烟退出 1。
保护流程自动恢复操作前 `1bbf509b` 新栈，schema、smoke 再次通过，并停止旧日志服务。
这次失败不能记为回滚成功。

第二次使用从旧提交提取的受保护冒烟副本，仅把四处基础 Compose 路径改为冻结文件路径，
不再合并两份完整编排。保留旧 execution Redis 持久化／写入探针、上传和日志目录真实写入探针、
公共入口、内部路由隔离与连续 Agent 就绪检查。第二次脚本退出 0，独立回读再次确认目标版本。

## 验证证据

| 服务 | 恢复后实际 image ID |
| --- | --- |
| web | `sha256:26fa562878d8107145f83123ff4d199f9c4f796ce542e9b868705c1ec65a0ffd` |
| core-api | `sha256:624740fe40405cffeecf1985019f7d029b58e5741f7f2513cc7111188b7da4fa` |
| agent-service | `sha256:c2dd597bf499bf36974ca52579e9b562e8b3a2d9994ead8dab653a4f49b1579c` |

三张镜像的 OCI revision 均为 `25c2e099`，实际容器使用冻结标签
`rollback-1bbf509b858e8b4f4788fdd4eb2a623f2075f906`。六个常驻容器均 healthy，重启计数 0，无 OOM。
公网 `https://inkforge.cn/api/v1/health/ready` 返回 ready，全部依赖检查 ok；部署锁已释放。

运行开关：旧 `DURABLE_AGENT_EXECUTION_SCHEMA_READY=true`、`DURABLE_AGENT_EXECUTION_ROUTE_MODE=off`、
`V1_FRESH_AGENT_STARTS_ENABLED=true`，生产视频关闭。没有重新开放 V2 新建路由。
`.env` 回滚前后哈希一致；旧日志使用原卷 `inkforge_execution_redis_data`，不恢复 RDB 覆盖原卷。
V1 ready/processing 均为 0，旧日志 active/pending/leased/rejected 均空且不在恢复隔离状态。

回滚前后 schema 指纹均为
`ea1df9ad015cd8d811d6ab250a7098870aa2befcf0afa3273b845255a0ac11b2`。
运行 Agent 内实际导入的作家 SYSTEM_PROMPT SHA-256 为
`4563b57543e2abafb98898ba8dc50c1b60852a22110331aa80d474309d3d98d7`，与旧提交计算结果一致，
本次六项新增编辑原则已经退出生产提示词。

回滚前另保存当前数据库 custom dump，pg_restore --list 可读、重新计算 SHA-256 一致：

- 目录：`/srv/inkforge-backups/application-rollback-20261011.iEp0LtkN`。
- 文件：`database-before-code-rollback.dump`，27924113 字节。
- SHA-256：`e706a9b652fb62a780a1490251bcde2b45dad51d6c1b9f07ef0c681180242e27`。

本次完成应用回滚的健康、schema、smoke 与提示词身份验收；没有创建新的真实写作任务，
没有把恢复旧代码宣称为已经验证朱雀检测结果改善。
