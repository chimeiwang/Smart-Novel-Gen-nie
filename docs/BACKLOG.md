# 后续能力备忘

> 状态：备忘，不是当前实现承诺。执行前必须重新按 `DOCS.md` 核对项目事实，并为具体变更补 spec 或更新当前需求文档。

## LangGraph / LangChain 后续能力

### 1. LangGraph `Send` 并行质量检查

- 一章完成后并行执行一致性校验、商业性评审、技法评审、设定同步建议。
- 多章节批量检查时，用动态 worker 分发章节，再汇总报告。
- 需要先为并行结果字段补 reducer，避免多个节点覆盖同一状态字段。

### 2. PostgreSQL 持久化 Checkpointer

- 当前 `MemorySaver` 只支持当前进程内 `interrupt/resume`。
- 当写作任务需要跨服务重启、热更新、多实例或长时间挂起恢复时，接入 LangGraph 持久化 checkpointer。
- `WritingTask` 继续保存业务状态；Graph checkpoint 负责恢复图执行位置，两者职责不要混淆。

### 3. Retrieval / RAG

- 当前 `search_lore` / `find_similar_lore` 不是完整向量检索。
- 后续为长篇小说上下文补 embeddings / retriever / vector store：
  - 章节历史召回
  - 角色经历召回
  - 伏笔上下文召回
  - 文风样本召回
  - 参考资料召回
- 检索结果必须标明来源与时间范围，不能把召回片段当成正式设定覆盖数据库。

### 4. LangSmith 评估集

- 为 Agent 路由、工具调用、草案质量、编辑评分、返工收敛建立评估样本。
- 用固定样本回归测试 prompt、tool schema、AgentDefinition 和模型 runtime 改动。
- 追踪不仅看日志，还要沉淀 pass/fail 指标。

### 5. Graph State Reducer 精细化

- 为未来并行节点补 reducer：
  - `conversationHistory`
  - `controlEvents`
  - quality check results
  - artifact evaluations / revisions
  - workflow event summaries
- 当前串行路径可以覆盖式更新；并行化前必须先明确合并策略。

### 6. 章节生产 UI 编排

- 让用户能显式启动“章节目标 → Beat Plan → 写作 → 审核 → 返工 → 应用”的受控流程。
- 当前子图已承载 Agent 执行 / 审核 / 返工循环，但 UI 仍以聊天入口为主。
- 后续可在工作台提供流程状态条、跳过/重跑/确认按钮和阶段报告入口。

### 7. 创作操作图后续增强

- 当前已完成创作操作入口、创作操作图、正文草案化、待审核草案确认链路和前端中文状态展示。
- 后续可继续增强：
  - 自动连续生成多章或整卷流程。
  - 更稳定的结构化审核结论，减少从自然语言审核报告推断“通过/返工”。
  - 显式 `pendingArtifactId` / `pendingActionType` 字段，替代 `WritingTask.generatedContent` 的兼容标记。
  - 为创作操作分类建立 LangSmith / fixture 评估集，避免 prompt 调整后退回“只按 Agent 关键词分类”。
