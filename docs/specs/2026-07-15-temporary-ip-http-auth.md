# 临时 IP/HTTP 会话兼容规格

## 状态

- 初始日期：2026-07-15
- 结束日期：2026-08-05
- 状态：已结束

生产域名 HTTPS 已上线，生产 `.env` 已删除 `ALLOW_INSECURE_HTTP_AUTH`，Core 运行值已核验为 `false`。本文件仅保留临时 IP/HTTP 过渡方案的历史记录，不再是当前生产部署指引；生产不得重新启用明文会话 Cookie。

## 历史背景

当时的生产入口暂时只能通过 `http://124.71.85.180` 访问。Core API 在生产环境固定签发 `Secure` 会话 Cookie，浏览器不会在 HTTP 来源保存该 Cookie，导致登录接口成功后仍被页面保护逻辑重定向到登录页。

## 当时目标

在不把服务降级为 `dev` 环境的前提下，提供一个默认关闭、显式开启、可回退的临时配置，使 IP/HTTP 部署能够签发非 `Secure` 的会话 Cookie。

## 历史约束

- 默认行为不变：生产环境仍签发 `Secure` Cookie。
- 只允许 `ALLOW_INSECURE_HTTP_AUTH=true` 明确关闭 `Secure` 属性；保留 `HttpOnly`、`SameSite=lax`、`Path=/` 与现有过期时间。
- 登录和退出必须使用同一个 Cookie 安全属性，避免 HTTP 下无法删除 Cookie。
- 不修改 PostgreSQL schema，不修改 Web 登录请求逻辑，不将 `ENVIRONMENT` 改为 `dev`。
- Compose 仅向 Core API 传递该变量，默认值必须为 `false`。
- `.env.example` 必须说明该变量仅供短期 IP/HTTP 过渡使用，并提示 HTTPS 恢复后删除。

## 历史验收标准

1. 生产默认和显式 `false` 时，登录 Cookie 含 `Secure`。
2. 生产显式 `true` 时，登录与退出 Cookie 均不含 `Secure`，其余安全属性保持不变。
3. 非生产环境维持既有非 `Secure` 行为。
4. 生产 Compose 向 Core API 注入 `ALLOW_INSECURE_HTTP_AUTH: ${ALLOW_INSECURE_HTTP_AUTH:-false}`。
5. 过渡部署后，线上登录响应不含 `Secure`，浏览器可进入 `/dashboard`；可信 HTTPS 上线后结束过渡并恢复生产 `Secure` Cookie。

## 当时的部署兼容

- 生产部署脚本中的 Git 命令必须仅对当前 `APP_DIR` 声明 `safe.directory`，以兼容仓库文件由不同运维用户创建的服务器。
- 不得写入任何用户的全局 Git 配置，也不得放宽 SSH 主机密钥校验。
