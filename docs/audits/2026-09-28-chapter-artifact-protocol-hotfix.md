# 章节正文提交协议补丁本地验收

日期：2026-09-28。范围见 [规格](../specs/2026-09-28-chapter-artifact-protocol-hotfix.md)。

## 环境与结果

- 基线：`eda6fdd56ae36307f25f681977c0e11faa43a56a`，Windows、Python 3.12.13；使用锁文件安装依赖。
- 独立工作树：`C:/Users/niebo/.codex/worktrees/chapter-artifact-protocol-hotfix/inkForge`。
- 先执行新增回归，在旧实现中观察到 16 个预期失败：读取纠正消耗预算、缺少具体反馈，以及校验仍是通用 value_error。
- 修补后相关运行时、工具、Operation、图编排、写作和质量任务回归共 373 项通过。
- 仓库 Ruff 通过；Mypy 检查 131 个源文件通过；`git diff --check` 通过。
- 完整正文保留测试使用 21000 字符正文；坏响应的正文和工具包均不接受，额外调用独立授权和回报 usage。
- 已验证 primary/reviser 与 write_chapter/rewrite_scene 四种组合；二次正文失败终止、首个纠正未恢复或混有控制工具时不追加机会、选区不扩充预算。
- 隔离验收完成时，原主工作树仍为同一 HEAD 且无未提交改动。未修改 Core、数据库、模型配置或 ReviewArtifact 状态机。

## 验证命令

```powershell
uv run --frozen pytest apps/agent-service/tests/runtime apps/agent-service/tests/tools apps/agent-service/tests/operations apps/agent-service/tests/graph apps/agent-service/tests/jobs/test_quality.py apps/agent-service/tests/jobs/test_writing.py -q --tb=short
uv run --frozen ruff check .
uv run --frozen mypy apps/agent-service/src packages/service-contracts/src packages/service-auth/src
git diff --check
```

以上是受控 Provider 的本地回归，未执行真实供应商调用、生产部署或失败小说续跑。
共享 JSON Schema 的跨字段表达限制仍存在，本次通过明确提示、稳定校验原因和严格有界纠正缓解。
