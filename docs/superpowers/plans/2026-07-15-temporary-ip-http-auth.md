# 临时 IP/HTTP 会话兼容 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保留生产配置边界的同时，为临时 IP/HTTP 部署提供显式、默认关闭的非 Secure 会话 Cookie 开关。

**Architecture:** `Settings` 读取 `ALLOW_INSECURE_HTTP_AUTH`，启动阶段将其计算为 `AuthService.cookie_secure`，认证路由统一使用该属性签发和删除 Cookie。Compose 把变量传入 Core API，默认关闭。

**Tech Stack:** Python、FastAPI、Pydantic Settings、pytest、Docker Compose。

---

### Task 1: 定义会话 Cookie 安全属性并锁定行为

**Files:**
- Modify: `apps/core-api/tests/auth/test_auth_api.py`
- Modify: `apps/core-api/tests/test_config.py`
- Modify: `apps/core-api/src/inkforge_core/config.py`
- Modify: `apps/core-api/src/inkforge_core/app.py`
- Modify: `apps/core-api/src/inkforge_core/auth/service.py`
- Modify: `apps/core-api/src/inkforge_core/auth/router.py`

- [ ] **Step 1: 写入失败测试**

在 `test_cookie_security_attributes_follow_environment` 中增加生产环境显式 `cookie_secure=False` 的登录和退出断言：两个 `Set-Cookie` 均不含 `Secure`，但仍含 `HttpOnly`、`SameSite=lax` 和 `Path=/`。在 `test_config.py` 中断言 `Settings(environment="production")` 默认值为安全 Cookie，显式 `allow_insecure_http_auth=True` 才会关闭它。

- [ ] **Step 2: 运行失败测试**

运行：`uv run pytest apps/core-api/tests/auth/test_auth_api.py::test_cookie_security_attributes_follow_environment apps/core-api/tests/test_config.py -q`

预期：失败，原因是 `AuthService` 尚未接受 `cookie_secure`，配置尚无临时开关。

- [ ] **Step 3: 实现最小配置与传递链路**

在 `Settings` 增加 `allow_insecure_http_auth: bool = False`，增加只读属性 `session_cookie_secure`：仅当环境为 `production` 且该开关为 `false` 时返回 `true`。`AuthService` 构造函数接收并保存 `cookie_secure: bool`。`_configure_auth` 传递 `settings.session_cookie_secure`。认证路由的登录、注册和退出 Cookie 全部使用 `service.cookie_secure`。

- [ ] **Step 4: 验证单元测试通过**

运行：`uv run pytest apps/core-api/tests/auth/test_auth_api.py::test_cookie_security_attributes_follow_environment apps/core-api/tests/test_config.py -q`

预期：通过。

### Task 2: 暴露受控部署变量与文档

**Files:**
- Modify: `infra/compose.yaml`
- Modify: `.env.example`
- Modify: `tests/architecture/test_compose_security.py`

- [ ] **Step 1: 写入失败架构测试**

在 `test_compose_security.py` 增加断言：`core-api` 服务块包含 `ALLOW_INSECURE_HTTP_AUTH: ${ALLOW_INSECURE_HTTP_AUTH:-false}`；`.env.example` 包含默认 `ALLOW_INSECURE_HTTP_AUTH=false` 与中文风险说明。

- [ ] **Step 2: 运行失败测试**

运行：`uv run pytest tests/architecture/test_compose_security.py -q`

预期：失败，原因是 Compose 和环境示例尚未声明开关。

- [ ] **Step 3: 实现最小部署配置**

在 `core-api.environment` 添加默认关闭的变量；在 `.env.example` 的 JWT 配置之后添加默认值和中文说明，明确仅用于短期 IP/HTTP 过渡、恢复 HTTPS 后改回 `false`。

- [ ] **Step 4: 验证架构测试通过**

运行：`uv run pytest tests/architecture/test_compose_security.py -q`

预期：通过。

### Task 3: 完整验证、提交与发布

**Files:**
- Verify: `apps/core-api/tests/auth/test_auth_api.py`
- Verify: `apps/core-api/tests/test_config.py`
- Verify: `tests/architecture/test_compose_security.py`

- [ ] **Step 1: 运行完整相关验证**

运行：`uv run pytest apps/core-api/tests/auth/test_auth_api.py apps/core-api/tests/test_config.py tests/architecture/test_compose_security.py -q`

运行：`uv run ruff check apps/core-api/src apps/core-api/tests tests/architecture`

运行：`uv run mypy apps/core-api/src`

- [ ] **Step 2: 提交并推送临时兼容改动**

提交信息：`修复：支持临时 IP HTTP 登录会话`

- [ ] **Step 3: 在服务器启用并部署**

在服务器 `/srv/smart-novel-gen/.env` 设置 `ALLOW_INSECURE_HTTP_AUTH=true`，以现有严格 SSH 部署路径发布新镜像；不得打印 `.env` 或密钥内容。

- [ ] **Step 4: 验证线上真实登录链路**

确认登录响应不再含 `Secure`，使用浏览器登录 `admin` 后访问 `/dashboard` 为 200；最后确认 `/api/v1/auth/me` 为 200。
