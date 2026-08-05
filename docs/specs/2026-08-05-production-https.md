# 生产域名 HTTPS 与安全会话恢复规格

## 状态

- 日期：2026-08-05
- 状态：生产已上线，仓库实现待发布，Skill待迁移
- 生产核验时间：2026-08-05 20:40+08 之后
- 生产域名：`inkforge.cn`、`www.inkforge.cn`
- 证书终止层：宿主机 Nginx

## 当前事实

2026-08-05 20:40+08 之后的公网与生产机核验确认：

- Ubuntu 22.04 宿主机 Nginx 1.18 已在 80/443 为 `inkforge.cn` 和 `www.inkforge.cn` 提供公网入口并终止 TLS；
- Let's Encrypt 证书 SAN 同时包含 `inkforge.cn` 与 `www.inkforge.cn`，签发者为 `CN=YR1`，到期日为 2026-11-03；
- 根域和 `www` 的 HTTP 请求以及 `www` 的 HTTPS 请求均返回 308，并规范化到 `https://inkforge.cn`；
- `https://inkforge.cn/api/v1/health/ready` 返回 ready，公网 `/internal/v1/health/live` 返回 404；
- TLS 1.2 与 1.3 可用，TLS 1.0 与 1.1 被拒绝；
- `certbot.timer` 处于 active，续期成功后的 Nginx 校验与 reload deploy hook 已安装；
- 生产 `.env` 已删除 `ALLOW_INSECURE_HTTP_AUTH`，Core 运行值已核验为 `false`，只读 schema 指纹检查和生产 smoke 均通过；
- 仓库分支已经实现 Compose Nginx 回环绑定、宿主机 Nginx 模板和边界测试，但尚未发布；因此生产运行中的 Compose 端口仍暂时发布为 `0.0.0.0:43120`，必须在仓库发布后收敛为仅绑定 `127.0.0.1:43120`。

当前真实链路为：

```text
公网 80/443
  -> 宿主机 Nginx（HTTP 跳转、TLS 终止、/internal/** 阻断）
  -> 127.0.0.1:43120
  -> Compose Nginx :8080
  -> Web / Core API
```

宿主机 Nginx 已是唯一预期公网入口，并始终通过回环地址访问 Compose Nginx。当前仅剩的服务器边界缺口是 Compose 端口仍额外绑定所有宿主机地址；仓库实现发布后才完成这一项收敛。

## 实施状态与可靠备份点

- 服务器 HTTPS、证书、跳转、会话安全恢复、续期 timer 与 deploy hook 已完成并核验。
- 仓库实现已经在本地分支完成，尚未推送和发布；不得把分支中的回环绑定描述成已经作用于生产 Compose。
- 个人 `inkforge-production-short-story-operator` Skill 尚未迁移到 `https://inkforge.cn`，本次不修改个人 Skill。

生产切换保留了以下可靠备份点；这里只记录目录与用途，不记录任何配置内容或秘密：

- `/root/inkforge-backups/20260805203449`：原 HTTP 配置；
- `/root/inkforge-backups/20260805203718`：最终切换前的 bootstrap 配置；
- `/root/inkforge-backups/20260805204043`：恢复 `Secure` Cookie 前的生产 `.env`。

## 目标

- 为 `inkforge.cn` 和 `www.inkforge.cn` 签发受信任的公开证书。
- `http://inkforge.cn/**`、`http://www.inkforge.cn/**` 和 `https://www.inkforge.cn/**` 永久跳转到 `https://inkforge.cn/**`。
- 宿主机 Nginx 在 443 终止 TLS，内部仍通过回环 HTTP 转发到 Compose Nginx。
- 保留 `/internal/**` 公网阻断、SSE 长连接和 50 MiB 请求体能力。
- 恢复生产 `Secure` 会话 Cookie，删除临时明文 HTTP 放行。
- 证书由现有 Certbot systemd timer 自动续期，成功续期后验证并 reload Nginx。
- 把 Compose 入口限制在 `127.0.0.1:43120`，避免绕过宿主机 TLS 边界。
- 建立可验证、可回退且不会触碰 PostgreSQL schema 或正式业务数据的操作流程。

## 非目标

- 不把 Web、Core API、Agent Service 或 Docker 内部通信改为 HTTPS。
- 不更换 Nginx，不引入 Caddy、CDN、云负载均衡或 DNS API 凭据。
- 不申请通配符证书，不增加 IPv6 解析。
- 不修改 PostgreSQL schema、数据库内容、Redis 数据或服务间 Ed25519 契约。
- 不在应用镜像、Git 仓库或 `.env` 中保存证书私钥。
- 不把 PostgreSQL 5432 和 Redis 6379 的公网暴露修复混入本次 HTTPS 变更；该问题单独按最高优先级处理。

## 方案选择

### 方案一：宿主机 Nginx + 现有 Certbot（采用）

宿主机 Nginx 继续作为真正的公网入口，通过 HTTP-01 为根域和 `www` 签发证书，并反代到回环地址上的 Compose Nginx。该方案复用已经安装并运行的 Certbot timer，不新增常驻容器，也不改变应用内部网络。

### 方案二：Compose Nginx 直接终止 TLS（拒绝）

该方案需要迁移 80/443 监听、证书挂载、非 root 私钥权限和续期 reload，同时移除或绕过现有宿主机 Nginx。双层入口迁移的中断风险明显高于方案一。

### 方案三：Caddy、CDN 或云负载均衡终止 TLS（拒绝）

该方案会新增外部依赖、费用、DNS 控制面或可信代理配置。当前单机已有完整的 Nginx 与 Certbot 能力，没有引入它们的必要。

## 目标架构

```text
公网 80/443
  -> 宿主机 Nginx
       - 80：ACME HTTP-01；其他请求 308 到 https://inkforge.cn
       - 443：TLS 1.2/1.3、HSTS、/internal/** 返回 404
       - www：308 到根域
  -> 127.0.0.1:43120
  -> Compose Nginx :8080
       - /api/v1/** -> Core API :8000
       - 其他路径 -> Web :43119
```

宿主机 Nginx 是唯一可从公网直接到达的入口。Compose Nginx 只绑定宿主机回环地址，继续承担应用路由、内部接口阻断和上游切换隔离。

## 详细设计

### 证书签发与续期

- 使用 Certbot `webroot` 验证，验证目录固定为 `/var/www/letsencrypt`。
- 证书名称固定为 `inkforge.cn`，SAN 同时包含 `inkforge.cn` 和 `www.inkforge.cn`。
- 首次签发前先安装只包含 HTTP 与 ACME location 的临时配置，`nginx -t` 通过后 reload；整个签发过程不停止现有 HTTP 服务。
- 证书保存在 Certbot 默认的 `/etc/letsencrypt`，权限与备份由宿主机管理，不复制到 Git 工作区。
- 现有 `certbot.timer` 继续每天两次执行 `certbot renew`。
- 新增 Certbot deploy hook：只有续期成功时才执行 `nginx -t` 和 `systemctl reload nginx`。
- 首次上线后运行一次 `certbot renew --dry-run`，证明 HTTP-01、续期配置和 reload hook 可用。

### 宿主机 Nginx

- 仓库分支已新增宿主机 Nginx 模板，生产文件固定为 `/etc/nginx/conf.d/inkforge.conf`；模板随仓库发布后才进入正式发布链路。
- 修改前把原配置复制到不被 Nginx include 的备份目录，并保留时间戳、属主和权限。
- HTTP server 仅保留 ACME challenge，其余请求使用 308 跳转到根域 HTTPS，并保留原路径和查询字符串。
- HTTPS 根域 server 反代到 `127.0.0.1:43120`，显式传递 `Host`、客户端地址和 `X-Forwarded-Proto=https`。
- HTTPS `www` server 只做 308 根域跳转。
- TLS 只允许 1.2 和 1.3，使用 Certbot 提供的安全参数；启用 HSTS，但不启用 `preload` 或 `includeSubDomains`。
- `/internal/**` 在宿主机和 Compose Nginx 两层都返回 404。
- API 路径继续关闭 proxy buffering/cache，并保留 3600 秒读写超时，避免破坏 SSE。

### Compose 边界与转发协议

- 仓库分支中的 `infra/compose.yaml` 已把 Nginx 端口改为 `127.0.0.1:${INKFORGE_PORT:-43120}:8080`。
- 仓库发布后，生产 Compose Nginx 只接受来自宿主机回环代理的入口，不再直接发布到所有宿主机地址；发布前的生产运行态仍是 `0.0.0.0:43120`。
- Compose Nginx 在上游明确传入 `https` 时保留该协议；没有受信任上游值时回退到自身 `$scheme`。
- 内部 Web、Core、Agent 与 Redis 网络不变，容器仍保持非 root、只读根文件系统和现有资源限制。

### 会话安全恢复

- 修改生产 `.env` 前已创建权限不宽于原文件的时间戳备份，可靠备份点为 `/root/inkforge-backups/20260805204043`。
- 生产 `.env` 已删除 `ALLOW_INSECURE_HTTP_AUTH=true`，Compose 默认值 `false` 已生效。
- Core API 已加载新环境；Core readiness、Compose smoke、只读 schema 指纹和容器环境中的布尔状态均已核验。
- 服务器 HTTPS 已生效；个人生产 Skill 仍待改为 `https://inkforge.cn` 并删除远程 HTTP 放行，迁移前不得静默降级到旧入口。

## 实施顺序

1. [x] 确认两个域名解析、80 可达、应用健康和磁盘空间。
2. [x] 备份宿主机 Nginx 配置与生产 `.env`。
3. [x] 安装 ACME webroot 的临时 HTTP 配置并通过 `nginx -t`。
4. [x] 为根域与 `www` 签发证书。
5. [x] 安装最终 HTTPS 配置和续期 deploy hook，验证后 reload Nginx。
6. [x] 从公网验证证书、SAN、HTTP/www 跳转、API readiness、TLS 版本和 `/internal/**` 404。
7. [x] 删除生产 HTTP Cookie 放行并重建 Core API，重新执行健康、schema 与 smoke 检查。
8. [x] 在本地仓库分支实现宿主机配置模板、Compose 回环绑定、转发协议和测试，并同步文档。
9. [ ] 推送并发布仓库变更，监控完整 CI 与生产部署；确认生产 Compose 已收敛到回环绑定，并补做尚未留存结果的自动续期 dry-run。
10. [ ] 把个人生产操作员 Skill 切换到 HTTPS，删除明文放行配置与说明。

## 错误处理与回退

- DNS、80 验证、`nginx -t` 或证书签发任一失败时，不安装 HTTPS 配置，HTTP 继续按原配置工作。
- 最终配置测试失败时恢复时间戳备份并 reload；证书文件可以保留，不影响旧 HTTP 服务。
- reload 后 443 不可达时先恢复宿主机 Nginx 配置，再区分本机监听与云安全组问题，不连续叠加修改。
- Core 重建失败时恢复 `.env` 备份并按现有 Compose 流程恢复 Core；不得修改数据库或删除卷。
- 应用镜像回滚与证书生命周期相互独立，任何回滚不得删除 `/etc/letsencrypt`。
- 日志不得输出 `.env`、SSH 密码、JWT、数据库密码、服务私钥或证书私钥。

## 测试与验收

### 仓库验证

- 架构测试断言 Compose Nginx 只绑定 `127.0.0.1`，且仍是唯一发布端口的 Compose 服务。
- Nginx 测试断言保留受信任的 `X-Forwarded-Proto`、`/internal/**` 阻断和 SSE 参数。
- 宿主机配置模板测试断言包含 80 跳转、443 TLS、根域/`www`、ACME 路径、回环 upstream 和 `/internal/**` 阻断。
- 运行部署相关 pytest、Ruff、Mypy、`npm run typecheck`、`npm run lint` 和生产构建。

### 生产已核验

- Let's Encrypt 证书 SAN 包含根域与 `www`，签发者为 `CN=YR1`，到期日为 2026-11-03。
- `http://inkforge.cn/**`、`http://www.inkforge.cn/**` 和 `https://www.inkforge.cn/**` 返回 308 到 `https://inkforge.cn`。
- TLS 1.0/1.1 被拒绝，TLS 1.2/1.3 可用。
- `https://inkforge.cn/api/v1/health/ready` 返回 ready，`https://inkforge.cn/internal/v1/health/live` 返回 404。
- schema 指纹检查和生产 smoke 通过；Core 运行环境中的 `ALLOW_INSECURE_HTTP_AUTH` 为 `false`。
- `certbot.timer` 处于 active，续期 deploy hook 已安装。

### 发布后待验收

- 发布并监控仓库实现对应的完整 CI 与生产部署。
- 确认生产 Compose Nginx 只绑定 `127.0.0.1:43120`，公网不能绕过宿主机 Nginx 直达 43120。
- 运行并留存 `certbot renew --dry-run` 结果，确认续期成功后 deploy hook 能验证并 reload Nginx。
- 把个人生产操作员 Skill 迁移到 `https://inkforge.cn`，删除旧 IP/HTTP 放行且不提供静默降级。

## 已知独立风险

只读核查发现宿主机 PostgreSQL 5432 和 Redis 6379 正监听公网地址，且公网 TCP 可达。这与“仅 Nginx 公网入口”的项目边界不符，风险高于普通配置清理。由于关闭端口可能影响未知运维来源，本规格只记录事实，不在 HTTPS 操作中顺手修改；必须另开安全收敛任务，核对云安全组、监听地址、认证和容器访问后处理。
