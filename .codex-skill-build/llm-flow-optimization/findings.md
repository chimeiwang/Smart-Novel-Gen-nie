# 调研记录

- Reviewer 初始消息通过 `buildConversationHistoryText()` 携带完整作家草案，随后又读取 Artifact，存在正文重复。
- 作家目前无 preGuard；显式要求 Beat Plan 但计划缺失时仍继续生成。
- control tool 默认都非 terminal，`submit_evaluation` 后会追加一个模型轮次。
- `ensureReasoningEffortPrompt()` 与 `llm-wrapper` 都会注入要求完整思考过程的全局提示。
- 模型单轮日志与 Agent 聚合日志都使用 `RESPONSE`，造成最终文本重复。
- 现有环境配置没有 LLM payload 日志模式。
- Reviewer 模式可由 `activeArtifactId + pendingAgentCall.toAgent` 可靠识别；当前 Operation 主责 Agent 可作为草案生产者标识。
- Beat Plan guard 可复用 `AgentDefinition.preGuard`，不会创建 Artifact，也不会进入后续 Reviewer 节点。
- terminal control 需要在纯工具调用时从 `submit_evaluation.summary/requiredChanges` 生成确定性可见报告，不能返回早期过程文本。
- 日志可以保持原 logger 单例，对 LLM 专用部分改写为 JSONL；默认 summary 不序列化完整 messages，但始终记录 `serializedChars`。
- `AgentDefinition.preGuard` 的非空 skipMessage 会进入普通 text artifact fallback；必须由 executor 在 `errorMessage` 分支直接回复，才能保证阻断不创建草案。
- “完整请求总字符数”必须包含 tools 定义，不能只统计 messages；日志同时保留 messages/tools 分项便于定位膨胀来源。
- `submit_evaluation` 与其他工具被模型同轮并列调用时，terminal 工具之后的调用也必须停止执行，才符合立即终止语义。
- Beat Plan 关键词检测需要排除“不需要/无需/即使没有也继续”等明确否定表达。
