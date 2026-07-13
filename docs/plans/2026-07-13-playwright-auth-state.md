# Playwright 认证状态复用实施计划

> **供执行智能体使用：**必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，逐项实施本计划。步骤使用勾选框（`- [ ]`）跟踪进度。

**目标：**让六个本地 Playwright 主流程在不削弱 Core 注册限流的前提下，一次运行只注册一个用户，并修正文风创建后的过时定位器。

**架构：**认证用例作为 Playwright 依赖项目运行，完成注册、退出和重新登录后写入 `storageState`；Chromium 业务项目依赖认证项目并加载该状态。其余五个场景只创建各自业务数据，不再注册用户；文风场景按创建后自动展开的产品行为继续上传资料和生成画像。

**技术栈：**Playwright、TypeScript、Next.js、pytest 架构测试。

**权威规格：**`docs/specs/2026-07-13-playwright-auth-state.md`

---

### 任务 1：用失败的架构测试锁定认证项目契约

**文件：**

- 修改：`tests/architecture/test_local_development.py`

- [ ] **步骤 1：新增失败测试**

新增测试，读取 `playwright.config.ts`、`tests/e2e/helpers.ts` 和五个业务 spec，断言：

```python
def test_e2e_reuses_authenticated_state_after_auth_scenario() -> None:
    config = (ROOT / "playwright.config.ts").read_text(encoding="utf-8")
    helpers = (ROOT / "tests" / "e2e" / "helpers.ts").read_text(encoding="utf-8")
    business_specs = [
        "knowledge-style.spec.ts",
        "project-editor.spec.ts",
        "quality-billing.spec.ts",
        "writing-artifact.spec.ts",
    ]

    assert "AUTH_STATE_PATH" in config
    assert 'name: "认证准备"' in config
    assert 'dependencies: ["认证准备"]' in config
    assert "storageState: AUTH_STATE_PATH" in config
    assert "registerWithApi" not in helpers
    for filename in business_specs:
        source = (ROOT / "tests" / "e2e" / filename).read_text(encoding="utf-8")
        assert "registerWithApi" not in source
```

- [ ] **步骤 2：确认测试因功能缺失而失败**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/architecture/test_local_development.py::test_e2e_reuses_authenticated_state_after_auth_scenario -q
```

预期：失败，原因是 Playwright 配置尚未定义认证准备项目或业务 spec 仍调用 `registerWithApi`。

### 任务 2：实现认证状态准备与业务项目依赖

**文件：**

- 新建：`tests/e2e/auth-state.ts`
- 修改：`playwright.config.ts`
- 修改：`tests/e2e/auth.spec.ts`
- 修改：`tests/e2e/helpers.ts`
- 修改：`tests/e2e/knowledge-style.spec.ts`
- 修改：`tests/e2e/project-editor.spec.ts`
- 修改：`tests/e2e/quality-billing.spec.ts`
- 修改：`tests/e2e/writing-artifact.spec.ts`

- [ ] **步骤 1：定义唯一认证状态路径**

在 `tests/e2e/auth-state.ts` 中定义：

```ts
import path from "node:path";

export const AUTH_STATE_PATH = path.join("output", "playwright", ".auth", "user.json");
```

- [ ] **步骤 2：让认证用例保存最终登录状态**

在 `auth.spec.ts` 最终确认 `/dashboard` 后执行：

```ts
await page.context().storageState({ path: AUTH_STATE_PATH });
```

- [ ] **步骤 3：配置认证准备项目和业务依赖项目**

在 `playwright.config.ts` 导入 `AUTH_STATE_PATH`，把项目配置改为：

```ts
projects: [
  {
    name: "认证准备",
    testMatch: /auth\.spec\.ts/,
    use: { ...devices["Desktop Chrome"] },
  },
  {
    name: "chromium",
    testIgnore: /auth\.spec\.ts/,
    dependencies: ["认证准备"],
    use: {
      ...devices["Desktop Chrome"],
      storageState: AUTH_STATE_PATH,
    },
  },
],
```

- [ ] **步骤 4：移除业务场景的重复注册**

从五个业务场景中删除 `registerWithApi` 导入和调用，并从 `helpers.ts` 删除不再使用的 `registerWithApi()`。保留 `uniqueUsername()` 和 `E2E_PASSWORD` 供认证用例使用。

- [ ] **步骤 5：修正文风自动展开断言**

把创建文风后的旧点击：

```ts
await page.getByRole("button", { name: "展开" }).first().click();
```

替换为当前状态断言：

```ts
await expect(page.getByRole("button", { name: "收起" }).first()).toBeVisible();
await expect(page.locator('input[type="file"]')).toBeVisible();
```

- [ ] **步骤 6：确认目标架构测试转绿**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/architecture/test_local_development.py -q
```

预期：全部通过。

### 任务 3：验证测试清单和前端质量门

**文件：**无新增修改。

- [ ] **步骤 1：确认仍只有六个主流程**

运行：

```powershell
npm run test:e2e:list
```

预期：认证准备项目列出一个认证用例，Chromium 项目列出五个业务用例，总数为 6；认证用例不在 Chromium 项目中重复。

- [ ] **步骤 2：运行前端测试与静态检查**

运行：

```powershell
npm run test:web
npm run typecheck
npm run lint
```

预期：全部退出码为 `0`。

- [ ] **步骤 3：检查改动质量**

运行：

```powershell
git diff --check
```

预期：退出码为 `0`，且没有修改 Core 限流、数据库 schema 或 E2E 固定等待时间。

### 任务 4：运行真实三服务端到端验收

**文件：**仅在失败时按新 spec 和 TDD 流程修复。

- [ ] **步骤 1：确认三个服务健康且使用 fake 模型**

确认 `http://127.0.0.1:43119/login`、Core readiness 和 Agent readiness 均返回成功；服务进程必须显式使用 `MODEL_PROVIDER=fake`。

- [ ] **步骤 2：运行完整 E2E**

运行：

```powershell
$env:E2E_BASE_URL='http://127.0.0.1:43119'
npm run test:e2e
```

预期：6 个用例全部通过，退出码为 `0`。

- [ ] **步骤 3：若当前来源桶尚未恢复**

若唯一认证用例仍收到 `429`，读取响应的 `Retry-After` 作为现有桶证据。不得清理共享 Redis 键、伪造来源或修改 Core 限流；等待自然恢复后只重新运行完整套件。

- [ ] **步骤 4：最终回归**

重新运行目标架构测试、`npm run test:web`、`npm run typecheck`、`npm run lint` 和完整 E2E，记录真实退出码与通过数量。
