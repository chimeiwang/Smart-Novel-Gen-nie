# 临时 IP/HTTP 会话兼容规格

## 背景

生产入口暂时只能通过 `http://124.71.85.180` 访问。Core API 在生产环境固定签发 `Secure` 会话 Cookie，浏览器不会在 HTTP 来源保存该 Cookie，导致登录接口成功后仍被页面保护逻辑重定向到登录页。

## 目标

在不把服务降级为 `dev` 环境的前提下，提供一个默认关闭、显式开启、可回退的临时配置，使 IP/HTTP 部署能够签发非 `Secure` 的会话 Cookie。

## 约束

- 默认行为不变：生产环境仍签发 `Secure` Cookie。
- 只允许 `ALLOW_INSECURE_HTTP_AUTH=true` 明确关闭 `Secure` 属性；保留 `HttpOnly`、`SameSite=lax`、`Path=/` 与现有过期时间。
- 登录和退出必须使用同一个 Cookie 安全属性，避免 HTTP 下无法删除 Cookie。
- 不修改 PostgreSQL schema，不修改 Web 登录请求逻辑，不将 `ENVIRONMENT` 改为 `dev`。
- Compose 仅向 Core API 传递该变量，默认值必须为 `false`。
- `.env.example` 必须说明该变量仅供短期 IP/HTTP 过渡使用，并提示 HTTPS 恢复后删除。

## 验收标准

1. 生产默认和显式 `false` 时，登录 Cookie 含 `Secure`。
2. 生产显式 `true` 时，登录与退出 Cookie 均不含 `Secure`，其余安全属性保持不变。
3. 非生产环境维持既有非 `Secure` 行为。
4. 生产 Compose 向 Core API 注入 `ALLOW_INSECURE_HTTP_AUTH: ${ALLOW_INSECURE_HTTP_AUTH:-false}`。
5. 部署后，线上登录响应不再含 `Secure`，浏览器可进入 `/dashboard`；恢复 HTTPS 后把 `.env` 改回 `false` 并再次部署。
