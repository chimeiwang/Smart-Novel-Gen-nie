# DeepSeek 模型响应等待 300 秒临时修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 DeepSeek V4 非流式模型响应读取等待从 60 秒临时提高到 300 秒，同时保持其他传输边界和无自动重试语义不变。

**Architecture:** 只修改 `DeepSeekV4Provider` 自建 `httpx.AsyncClient` 的显式四项超时，不把临时数值扩散到业务 Operation 或工作流。通过真实客户端 timeout 对象测试锁定 connect/read/write/pool，部署后只读核验生产容器实际代码。

**Tech Stack:** Python 3.12、httpx 0.28、pytest、Ruff、Mypy、GitHub Actions、Docker Compose

---

### Task 1: 用失败测试锁定四项超时

**Files:**
- Test: `apps/agent-service/tests/providers/test_deepseek_v4.py`

- [x] **Step 1: 写入默认客户端超时测试**

在 `_provider()` helper 后新增：

```python
@pytest.mark.asyncio
async def test_default_client_waits_up_to_300_seconds_for_response() -> None:
    provider = DeepSeekV4Provider(_settings())
    try:
        timeout = provider._client.timeout
        assert timeout.connect == 10
        assert timeout.read == 300
        assert timeout.write == 60
        assert timeout.pool == 60
    finally:
        await provider.aclose()
```

- [x] **Step 2: 运行测试并确认按预期失败**

Run:

```powershell
uv run pytest apps/agent-service/tests/providers/test_deepseek_v4.py::test_default_client_waits_up_to_300_seconds_for_response -q
```

Expected: `FAIL`，失败点为当前 `timeout.read == 60`，而期望值是 `300`。

### Task 2: 最小修改 DeepSeek 默认客户端

**Files:**
- Modify: `apps/agent-service/src/inkforge_agents/providers/deepseek_v4.py:41`
- Test: `apps/agent-service/tests/providers/test_deepseek_v4.py`

- [x] **Step 1: 显式设置四项超时**

把默认客户端构造改为：

```python
self._client = client or httpx.AsyncClient(
    timeout=httpx.Timeout(connect=10, read=300, write=60, pool=60)
)
```

- [x] **Step 2: 运行单测并确认通过**

Run:

```powershell
uv run pytest apps/agent-service/tests/providers/test_deepseek_v4.py::test_default_client_waits_up_to_300_seconds_for_response -q
```

Expected: `1 passed`。

- [x] **Step 3: 运行 DeepSeek Provider 全量测试**

Run:

```powershell
uv run pytest apps/agent-service/tests/providers/test_deepseek_v4.py -q
```

Expected: 全部通过，且 HTTP 错误、timeout 分类和单次请求测试无回归。

- [x] **Step 4: 运行静态检查**

Run:

```powershell
uv run ruff check apps/agent-service/src/inkforge_agents/providers/deepseek_v4.py apps/agent-service/tests/providers/test_deepseek_v4.py
uv run mypy apps/agent-service/src/inkforge_agents/providers/deepseek_v4.py
```

Expected: 两条命令均退出 0。

### Task 3: 提交、推送、部署和生产只读验收

**Files:**
- Create: `docs/specs/2026-08-24-deepseek-response-timeout-hotfix.md`
- Create: `docs/superpowers/plans/2026-08-24-deepseek-response-timeout-hotfix.md`

- [x] **Step 1: 检查差异只包含本次临时修复**

Run:

```powershell
git status --short
git diff --check
git diff -- apps/agent-service/src/inkforge_agents/providers/deepseek_v4.py apps/agent-service/tests/providers/test_deepseek_v4.py docs/specs/2026-08-24-deepseek-response-timeout-hotfix.md docs/superpowers/plans/2026-08-24-deepseek-response-timeout-hotfix.md
```

Expected: 只有两个代码/测试文件和两个文档文件，无空白错误、无其他工作树内容。

- [x] **Step 2: 提交**

Run:

```powershell
git add apps/agent-service/src/inkforge_agents/providers/deepseek_v4.py apps/agent-service/tests/providers/test_deepseek_v4.py docs/specs/2026-08-24-deepseek-response-timeout-hotfix.md docs/superpowers/plans/2026-08-24-deepseek-response-timeout-hotfix.md
git commit -m "修复：延长 DeepSeek 模型响应等待"
```

Expected: 创建一个只包含本次临时修复的提交。

- [ ] **Step 3: 推送到 main 触发部署**

Run:

```powershell
git push origin HEAD:main
```

Expected: fast-forward 更新 `origin/main`；若远端已前进则安全失败，先重新同步和复验，不强推。

- [ ] **Step 4: 等待 GitHub Actions 构建与生产部署完成**

Run:

```powershell
$commitSha = git rev-parse HEAD
$runs = gh run list --commit $commitSha --limit 20 --json databaseId,status,conclusion,workflowName,url | ConvertFrom-Json
$runs | Format-Table workflowName,databaseId,status,conclusion,url
foreach ($run in $runs) {
    gh run watch $run.databaseId --exit-status
}
```

Expected: 构建、测试和部署相关 job 均为 `success`；不能用 push 成功代替部署完成。

- [ ] **Step 5: 生产只读验收**

通过已有 SSH 受信主机连接只读确认：

```text
Agent 容器 running/healthy
DeepSeekV4Provider timeout = connect 10 / read 300 / write 60 / pool 60
Agent readiness 正常
Core 公共 readiness 正常
```

Expected: 运行镜像包含本次提交，且不执行真实付费模型请求、不修改生产数据。
