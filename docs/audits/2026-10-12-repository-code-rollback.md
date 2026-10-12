# 2026-10-12 仓库代码回滚审计

状态：代码恢复与验证完成。依据[回滚规格](../specs/2026-10-12-repository-code-rollback.md)。

## 范围与来源

用户在生产恢复后明确要求“仓库也一起回滚一下”。本次恢复目标为
`25c2e099178540579ca6f83309c9ff26db9e08be`；远端操作前 main 为
`efb689bbfd402d0c67efaa17cdf782e1f31124b8`。

采用新增前向提交恢复文件，不改写历史。作家提示词增强和 V2 引擎退役实现一并撤回；
原有 V1 写作和 V2 兼容代码、契约、测试及编排恢复到该基线。相对基线只允许三个文档差异：
本审计、对应规格、`DOCS.md` 中新增的入口。

此前生产回滚的完整证据保存在
[历史提交中的生产回滚审计](https://github.com/chimeiwang/Smart-Novel-Gen-nie/blob/efb689bbfd402d0c67efaa17cdf782e1f31124b8/docs/audits/2026-10-11-production-code-rollback.md)。
被恢复的其他历史文档状态文字属于基线快照，不代表本次重新执行；本次结果以本审计为准。

## 未提交内容保护

原开发目录 `/Users/boqiangnie/inkforge` 在操作前位于 `9abb98cc5d74405106256fcff3f9ab88ada829a8`，
存在 8 个已修改的受控文件和 6 个未跟踪文件。本次使用隔离工作树完成回滚，原文件内容、权限、
未提交二进制补丁及状态另存于权限为 `0700` 的本机临时备份目录。

这些已修改文件在 `9abb98c` 与 `25c2e099` 中的基础内容一致；新入口只加入 `DOCS.md`，
避开正在修改的 `docs/README.md`。原 main 最后以快进方式同步，已有修改不纳入提交。

## 验证

- 全部运行代码、提示词、共享契约、数据库结构契约、生成客户端、配置和测试与目标基线逐 Git 对象一致。
- `npm run api:generate`、`npm run api:check` 通过，重新生成无代码差异。
- `npm run test:web` 通过（Web 373 项、API 客户端 3 项），`npm run typecheck`、`npm run lint` 通过。
- Java 21 执行 `./mvnw --batch-mode --no-transfer-progress clean verify` 通过，耗时 3 分 56 秒；
  JUnit 共 1384 项，失败 0、错误 0、跳过 4。数据库测试使用隔离 PostgreSQL Testcontainers。
- 本机完整 Python pytest 为 3955 通过、7 失败。失败全部在 `tests/architecture/test_deploy_scripts.py`：
  5 项依赖 macOS 不存在的 `/usr/bin/dd`，2 项来自夹具临时目录与脚本固定 `/tmp` bundle 路径不一致。
  同一部署脚本套件在只读挂载仓库的 Linux 容器中 73 项全部通过；本机其余 3889 项全部通过，
  包含 Compose 安全、共享协议及鉴权测试。两环境合计覆盖 3962 项，不声称本机一次全量全绿。
- Ruff 全通过；Mypy 134 个源文件通过。因本机没有 `uv` 命令，使用原环境中 pytest、Ruff、Mypy
  的绝对路径并显式设置本工作树的 `PYTHONPATH`，未修改依赖锁或源码。
- 规格与审计本地链接、`git diff --check` 和暂存差异检查通过。

本机验证日志：Java 为 `/tmp/inkforge-repository-rollback-java-verify.log`；Python 为
`/tmp/inkforge-repo-rollback-python-pytest.log`，Linux 部署脚本为
`/tmp/inkforge-repo-rollback-linux-deploy-pytest.log`。测试产生的临时数据库容器已清理。

## 提交与同步方式

将恢复结果作为原 main 后继提交保存，随后以 `--ff-only` 更新原工作区 main，再普通推送远端；
不使用 force push、hard reset、stash 或历史改写。最终核对本地 main、远端 main 和回滚工作树提交一致，
并逐文件哈希及完整二进制补丁确认上述 14 个本地文件和原未提交差异保持不变。

## 生产边界

本次只读核对生产源码及公共 readiness，没有构建或部署镜像，也没有写入数据库、执行迁移、恢复备份或修改正文。
生产源码只读回查为 `25c2e099178540579ca6f83309c9ff26db9e08be`；公共 readiness 为 `ready`，
Agent、数据库、Redis、后台任务、写作 Outbox 和结构检查均为 `ok`。
本次提交带 `[skip ci]`，避免推送 main 触发自动发布。
回滚后的新写作效果及外部检测分数未在本次任务中验证。
