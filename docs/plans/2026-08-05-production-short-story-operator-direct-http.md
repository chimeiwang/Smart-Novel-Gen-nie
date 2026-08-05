# 生产环境中短篇操作员固定 HTTP 直连实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 移除生产 Skill 的 SSH 隧道，通过显式精确放行让本机 CLI 固定直连 `http://124.71.85.180`。

**Architecture:** CLI 默认继续拒绝远程 HTTP；生产 wrapper 只对子进程设置精确 origin 放行变量，并固定 `production` profile。Skill 配置记录用户已接受明文 HTTP，不再保存 SSH 字段。

**Tech Stack:** Python、pytest、PowerShell 5.1、InkForge CLI、Codex Skills

---

### Task 1: CLI 精确放行远程 HTTP

**Files:**
- Modify: `tools/inkforge-cli/src/inkforge_cli/credentials.py`
- Modify: `tools/inkforge-cli/tests/test_credentials.py`
- Modify: `tools/inkforge-cli/README.md`

- [ ] **Step 1: 写失败测试**

在 `test_credentials.py` 增加测试：默认拒绝远程 HTTP；环境变量
`INKFORGE_CLI_ALLOW_INSECURE_HTTP_ORIGIN=http://124.71.85.180` 时只允许该规范化 origin，其他
地址、路径和通配值继续拒绝。

- [ ] **Step 2: 验证 RED**

Run: `uv run pytest tools/inkforge-cli/tests/test_credentials.py -q`
Expected: 新增精确放行测试失败，既有测试通过。

- [ ] **Step 3: 最小实现**

在 `validate_core_origin()` 完成现有结构校验和规范化后，仅当远程 HTTP 与环境变量值完全一致时
放行；未设置或不一致时保留现有异常。

- [ ] **Step 4: 验证 GREEN**

Run: `uv run pytest tools/inkforge-cli/tests/test_credentials.py tools/inkforge-cli/tests/test_api.py tools/inkforge-cli/tests/test_cli.py -q`
Expected: 全部通过。

### Task 2: 简化生产配置和 wrapper

**Files:**
- Modify: `C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator\scripts\configure.ps1`
- Modify: `C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator\scripts\operator.ps1`
- Modify: `%TEMP%\inkforge-production-operator-tests\operator.tests.ps1`

- [ ] **Step 1: 把集成测试改成直连契约并验证 RED**

测试 schema v2、`-AcceptInsecureHttp`、固定 origin、固定放行变量、身份预检、环境恢复、JSON/JSONL
和退出码；断言测试 PATH 中即使存在 fake SSH 也不会调用。

Run: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:TEMP\inkforge-production-operator-tests\operator.tests.ps1"`
Expected: SSH 版脚本不满足新契约，测试失败。

- [ ] **Step 2: 实现 schema v2 配置**

配置只保存 `schemaVersion=2`、`repositoryRoot`、`expectedUsername` 和
`acceptedInsecureHttp=true`；缺少 `-AcceptInsecureHttp` 时拒绝写入。

- [ ] **Step 3: 实现直连 wrapper**

删除 SSH、主机键、端口和隧道代码。固定 origin 和 profile，在调用 uv 前保存原环境变量、设置
精确生产 origin，并在 `finally` 恢复。保留命令白名单、PowerShell 管道输入、身份预检和流输出。

- [ ] **Step 4: 验证 GREEN**

Run: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:TEMP\inkforge-production-operator-tests\operator.tests.ps1"`
Expected: 0 failed，fake SSH 调用数为 0。

### Task 3: 更新 Skill 说明

**Files:**
- Modify: `C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator\SKILL.md`
- Modify: `C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator\references\cli-contract.md`
- Modify: `C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator\references\recovery.md`
- Verify: `C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator\agents\openai.yaml`

- [ ] **Step 1: 替换 SSH 说明**

明确固定公网 HTTP、用户已接受明文风险、不使用 SSH、不允许覆盖地址；保留中短篇业务、Diff、确认
和恢复边界。

- [ ] **Step 2: 校验 Skill**

Run: `python -X utf8 C:\Users\niebo\.codex\skills\.system\skill-creator\scripts\quick_validate.py C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator`
Expected: `Skill is valid!`。

### Task 4: 全量验证和只读生产查询

**Files:**
- Verify only.

- [ ] **Step 1: 运行代码检查**

Run: `uv run ruff check tools/inkforge-cli/src tools/inkforge-cli/tests`
Expected: 0 errors。

Run: `uv run mypy tools/inkforge-cli/src`
Expected: 0 errors。

- [ ] **Step 2: 配置并登录**

使用固定仓库、用户提供的 InkForge 用户名和 `-AcceptInsecureHttp` 写入 schema v2。`auth.login` 必须
由用户在真实 TTY 输入密码。

- [ ] **Step 3: 只读查询**

依次执行 `auth.whoami` 和 `short.list`，只统计当前用户的 `short_medium` 项目，不执行写操作。
