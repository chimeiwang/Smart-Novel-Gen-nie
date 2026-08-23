# 正式库视频结构晋升审计

日期：2026-08-23
状态：前向迁移已验证并执行；因现网旧镜像不兼容，正式库已精确回滚并恢复健康

## 1. 最终结论

迁移 SQL 本身正确，隔离库和正式库执行后都与开发 contract 精确一致；但现网 Core 镜像
`c6d6960edcaf4e86df3385d9792ac6cd6925d7c0` 只包含 44 表 contract，且没有
`without_video_preview` schema profile。正式 DDL 执行后，该旧镜像把新增视频对象判为结构漂移，
`/api/v1/health/ready` 的 `check_database_schema` 返回失败。

为避免把生产服务留在不健康状态，在确认所有新视频表为空、历史审核关联为空后，使用已在隔离库
验证的精确反向脚本恢复迁移前结构。最终正式库与迁移前结构指纹完全一致，Core readiness 全项为
`ok`，原有业务行计数未改变。

因此本次结果不能表述为“正式库视频结构已上线”。正确后续顺序是：先发布兼容迁移前后两种结构的
Core 版本，再重新执行同一个前向脚本；视频功能开关继续保持关闭。

回滚后用当前工作树 profile 对真实正式库基线复核时，进一步发现名单遗漏 5 张视觉稳定性表；该问题
已在 `schema_guard.py` 修正并增加 checked-in contract 回归测试。修正后 69 表 full contract 的
`without_video_preview` 投影恰为 44 表，与正式库基线 0 项差异。此修正尚未部署，不改变上述最终状态。

## 2. 结构差异

| 指标 | `novelwriterdev` | 正式库迁移前/回滚后 | 正式库前向迁移后（短暂状态） |
| --- | ---: | ---: | ---: |
| 表 | 69 | 44 | 69 |
| 视频表 | 25 | 0 | 25 |
| 枚举类型 | 22 | 22 | 22 |
| `ReviewArtifact` 视频字段 | 3 | 0 | 3 |
| 视频枚举值 | 2 | 0 | 2 |
| 规范化结构指纹 | `36904c220803175dbb65dc38329f29b8d41f1386cac46f4992d8f77ad6653f40` | `ecd541a96eba65d43fba66f59834f53987818b03ea10298f981a3ab965002fbe` | `36904c220803175dbb65dc38329f29b8d41f1386cac46f4992d8f77ad6653f40` |

具名差异清单和范围见
`docs/specs/2026-08-23-production-video-adaptation-schema-promotion.md`。`TokenUsage` 在两库中已经一致，
没有重复迁移。开发库中的测试项目、镜头、图片和提示词均未复制到正式库。

## 3. 迁移产物

| 产物 | SHA-256 |
| --- | --- |
| `20260823_production_video_adaptation_domain.sql` | `43e9e3ed6bea7f56d8611f374fb801d5f39adfa61e81b231f98ce8d8b851362e` |
| `20260823_production_video_adaptation_domain.rollback.sql` | `666e82db97a2ccbe3c2dc996e4580dcf8f4b37c6089317637156a8d4706ed42d` |

前向脚本要求数据库名精确为 `novelwriter` 和版本绑定确认值，按四个事务阶段使用 advisory lock；
反向脚本要求精确数据库名、独立确认值、全部视频表为空、全部视频审核关联为空，并验证枚举依赖仍为
迁移前已知范围。两个脚本都拒绝其他数据库，原有四个开发迁移仍只允许 `novelwriterdev`。

## 4. 备份证据

迁移前完整 custom-format 备份：

```text
/srv/backups/inkforge/inkforge-20260823T064401Z/database.dump
```

- 大小：18,090,268 字节；
- SHA-256：`cc5f1564e07b908407c0fb18b8e5d8f9475d8402c2cc0212251720249fcf9d88`；
- `sha256sum -c`：通过；
- `pg_restore --list`：通过；
- 完整恢复到一次性数据库：通过；
- 恢复后计数：小说 192、章节 221、审核记录 215；
- 恢复验证数据库和日志已按精确名称删除，备份保留。

同目录保留受限权限的前向与反向执行日志：

| 日志 | SHA-256 |
| --- | --- |
| `migration-20260823.log` | `4c09e0f608191d243a7dc1393ac0e20d9dc59a69dfdd82c1c2ee61b5b55385e6` |
| `rollback-20260823.log` | `9f353d48879a768636476ac8edad50e0efdbeaf4c8c1410669515945b25e3d24` |

文档和日志均未记录数据库密码、SSH 密钥或服务密钥。

## 5. 隔离演练证据

以正式库 schema-only 导出创建一次性 PostgreSQL 数据库，完成：

1. 前向首次执行成功；
2. 前向重复执行成功；
3. 迁移后导出为 69 表，指纹与当前 full contract 精确一致；
4. 空视频域反向执行成功；
5. 反向后只保留两个枚举值时，其余结构与基线一致；
6. 修正精确枚举恢复后，反向结构与迁移前正式库指纹完全一致；
7. 回滚后再次前向执行成功；
8. 人工插入一组隔离测试项目后，反向脚本按预期拒绝非空视频域；清理精确测试行后无残留。

所有一次性数据库、远端临时 SQL 和临时日志均已按精确名称删除。

仓库验证：Python 全量 3119 项通过、2 项按环境条件跳过；Ruff 全仓通过；Mypy 249 个源文件通过；
迁移/profile 相关定向测试 39 项通过；`git diff --check` 通过。

## 6. 正式执行与恢复证据

正式执行前：

- 视频开关：关闭；
- 长事务：0；无效索引：0；
- 表 44，视频表 0；
- 小说 192、章节 221、审核记录 215。

前向执行后：

- 表 69，视频表 25，视频表总行数 0；
- 历史审核视频关联行数 0；
- 无效索引 0，未验证视频约束 0，长事务 0；
- 小说 192、章节 221、审核记录 215；
- 当前仓库 full schema guard：`ready=True`、0 项差异；
- 现网旧镜像 readiness：只有 `check_database_schema=failed`，其他检查均为 `ok`。

精确反向执行后：

- 表 44，视频表/字段/枚举值均为 0；
- 结构指纹恢复为迁移前值，逐项比较一致；
- 小说 192、章节 221、审核记录 215；
- 无效索引 0，长事务 0；
- 现网 readiness：`status=ready`，database、schema、Redis、background tasks 和 writing outbox
  全部为 `ok`。

## 7. 后续门禁

再次执行正式迁移前必须同时满足：

1. 兼容 Core 镜像已部署，镜像内 contract 为当前 69 表版本并提供已覆盖全部 25 张视频表的
   `without_video_preview` profile；
2. 该镜像在当前 44 表正式基线上 readiness 为 `ready`；
3. `VIDEO_PREVIEW_ENABLED` 仍为关闭；
4. 再次确认无长事务并复核备份；
5. 执行前向脚本后，full contract、运行中镜像 readiness 和原有业务计数同时通过。
