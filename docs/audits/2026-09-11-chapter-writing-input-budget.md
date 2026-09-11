# 正文输入预算调整本地验收

日期：2026-09-11。环境：Windows 本地工作区；以下为提交前验收，未部署、未执行生产任务或变更数据库。
变更范围见 [输入预算规格](../specs/2026-09-11-chapter-writing-input-budget.md)。

## 结果

- `write_chapter` 生成与两类复审的新 v2 Step 输入及冷缓存输入预算均为 100,000，Run 两项累计预算均为
  600,000。保留旧 v1 与场景改写原预算。
- 原 30,000 冻结请求首次派发的兼容测试先在旧实现明确失败；增加精确历史预算映射后通过。
  新预算可用完整约 40,000 字符上下文完成 Fake Provider 生成及双复审；超过新旧上限均拒绝且不裁切。
- `uv run pytest apps/agent-service/tests/execution tests/architecture/test_agent_operation_catalog.py -q`：
  647 passed、1 skipped。保留现有 Starlette 弃用警告；首次还有 Windows 子进程编码警告，
  设置 `PYTHONUTF8=1` 后单独重跑执行资产派生检查，1 passed 且无该警告。
- Java `ExecutionRegistryTest`：16 tests、0 failures、0 errors，使用 Maven Surefire 3.5.6 单独执行目标测试。
  常规 Maven 编译仍被现有视频 OpenAPI 生成模型不一致阻断；该结果不代表完整 Maven verify 或生产验收。
- 提交前另执行根目录 `mvnw.cmd verify`，在 service-auth 的 `Ed25519PrivateKeyLoaderTest` 创建符号链接时，
  因 Windows 当前进程缺少所需权限而失败（11 tests、1 error），未进入后续 Core 编译。
  本次未更改鉴权源码、测试或系统权限；完整 Maven 门禁仍未通过。
- `uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src`：
  310 个源码文件通过。
- `uv run ruff check apps packages tests scripts tools`、执行资产派生 `--check` 和 `git diff --check` 通过。
  `uv run ruff check .` 在已有 `.codex-tmp`、`tmp` 临时脚本报 74 项问题，未修改这些用户文件。
- 执行资产 JSON 固定 LF，只有 Catalog 和 Step Budget 两项 manifest 哈希变化；资产指纹为
  `aa9d1838a436ea5588ae034e4097fde419ca9e8300324443fb55a1f90c1d1fec`。

## 生效边界

本地代码和测试已调整，生产仍使用旧部署。发布后新 Run 才使用新预算；已有 Run 保持冻结预算，
失败任务需要由用户重新发起新任务才能采用新额度。当前输入估算仍按字符数执行，本次未替换为 tokenizer。
