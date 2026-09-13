# LangGraph 兼容回退实施计划

> 执行方式：当前任务内并行核对与独立验证，遵循 test-driven-development 和 verification-before-completion；无需重复询问已确认的数据保护边界。

**目标：** 生产新写作恢复 8 月 29 日 LangGraph 流程，正式正文和大纲保持不变。

**架构：** 保留当前 V2-aware 后台与数据库，回退写作交互并开放 V1 新任务。历史 V2 只保留兼容能力，不回写其引擎身份，不执行 DDL。

**技术栈：** Next.js、Java Core、Python LangGraph、PostgreSQL、Redis、现有 Compose 发布流程。

## 任务一：写作入口回退

- [x] 在 `apps/web/src/features/writing/__tests__/writing-input-wiring.test.ts` 建立回归：默认发送旧请求，不调用 `buildNaturalRunRequest`，保留选区和 V1 观察。
- [x] 运行 `node --import tsx --test apps/web/src/features/writing/__tests__/writing-input-wiring.test.ts`，确认当前自然入口不能通过回退断言。
- [x] 从 `a37d8737` 恢复写作会话及其必要协作者；根据当前契约修正类型，不恢复旧视频接口。
- [x] 执行 `npm run test:web`、`npm run typecheck`、`npm run lint`、`npm run build`。

## 任务二：兼容数据库上的旧流程验证

- [x] 在 `RoutingWritingRunStarterTest` 及独立 Compose 验证中固定 `schemaReady=true/route=off/V1fresh=true`；断言新请求为 V1，既有 V2 仍按原身份查询与重放。
- [x] 验证真实 LangGraph 和 Core 读取工具网关，模型使用测试 Provider；草案采用只写独立测试小说。
- [x] 运行相关 Python 测试和完整 Maven verify，检查公共契约漂移。

## 任务三：生产备份、排空和发布

- [ ] 冻结候选提交与不可变镜像，记录上一组镜像。
- [ ] 完整备份 `novelwriter` 与 execution 日志，检查 SHA-256 和 `pg_restore --list`；采集作品保护表摘要。
- [ ] 在维护锁内关闭新任务并通过联合排空；保留全部数据和卷。
- [ ] 通过现有应用部署门禁切换兼容镜像，再开放 V1，实际回读配置。
- [ ] 验证登录、正文、大纲及新建任务的 V1/LangGraph 路径；正式作品摘要不变。记录删除数量，默认零删除。
- [ ] 更新需求入口、授权清单和审计，分别报告代码、测试、部署和作品保护结果。
