> 状态：历史归档，不作为当前实现依据。当前事实以 `DOCS.md`、`AGENTS.md`、`src/agents/AGENTS.md`、代码和 schema 为准。

# LangGraph State 分层重构审计记录

## 初步发现

- src/agents/graph/graph-definition.ts 已引入 StateSchema、ReducedValue、UntrackedValue。
- conversationHistory、controlEvents、agentOutputs 已使用 reducer。
- novelData、runtime、streamCallbacks、eventCallbacks 已使用 UntrackedValue。
- src/agents/graph/state.ts 已新增 OperationStep、ArtifactReviewState、WritingRuntimeContext、agentOutputs 相关 helper。
- src/agents/AGENTS.md 已有 v8.34 State 分层说明。
- 仍有旧兼容字段广泛存在：activeArtifactId、artifactMode、固定 agent output 字段、generatedContent 等，需要判断哪些只是 facade，哪些仍被当作权威状态。

## 待验证

- 已验证 snapshot 不序列化 runtime-only callbacks 或 novelData。
- /resume 主路径已优先 artifactReview；旧 generatedContent 只保留兼容 fallback。
- quality-check/studio input 已改为复用 createBaseGraphState。
- controlEvents reducer 已改成 undefined 不清空旧事件，避免并行/多节点写入覆盖。
- 旧 acceptGeneratedContentAction 已加保护：awaiting_user_review 或 generatedContent 等于当前 artifactId 时拒绝直接写章节。
