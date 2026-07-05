# LLM 正文写作流程优化

## 目标

实现 Reviewer 上下文去重、Beat Plan 显式前置检查、`submit_evaluation` 同轮终止、推理预算隔离和结构化 LLM 日志。

## 阶段

- [x] 阶段 1：核对现有 runtime、上下文、日志与测试入口。
- [x] 阶段 2：实现 Reviewer 上下文与 Beat Plan guard。
- [x] 阶段 3：实现 terminal control tool 与 profile/reasoning 隔离。
- [x] 阶段 4：实现 summary/full/off JSONL 日志。
- [x] 阶段 5：补充测试、文档并完成 typecheck/lint/build。

## 约束

- 保留 LangGraph、ReviewArtifact、工具注册表和双 Reviewer。
- 不修改数据库、SSE 或前端公共契约。
- 不实施此前建议 1、2。

## 错误记录

| 错误 | 尝试 | 处理 |
| --- | --- | --- |
| `python` 命令不存在 | 运行 planning-with-files session catchup | 改用 `python3` 成功执行 |
| `TS18046: total is unknown` | 首次运行 `npm run typecheck` | 为 `unknown[]` 的 reduce 显式指定 `number` 泛型 |

## 验证结果

- 相关 Node 测试：69 tests / 15 suites，全通过。
- `npm run typecheck`：通过。
- `npm run lint`：0 error；保留 1 个既有 React Hook warning。
- `npm run build`：通过；保留 Next.js middleware 弃用和 Turbopack NFT 既有警告。
- `git diff --check`：通过。
