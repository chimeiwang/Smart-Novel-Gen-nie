# 生产域名 HTTPS 与安全会话恢复规格

## 状态

- 日期：2026-08-05
- 状态：已批准，实施中
- 生产域名：`inkforge.cn`、`www.inkforge.cn`
- 证书终止层：宿主机 Nginx

## 当前事实

2026-08-05 的公网与生产机只读核查确认：

- `inkforge.cn` 和 `www.inkforge.cn` 的 A 记录均指向 `124.71.85.180`，无 AAAA；
- 公网 80 端口可访问且返回 200，没有跳转；公网 443 端口没有监听；
- 公网真正入口是 Ubuntu 22.04 宿主机上的 Nginx 1.18，而不是 Compose 内的 Nginx；
- 宿主机 Nginx 把请求转发到 `127.0.0.1:43120` 对应的 Compose Nginx；
- 宿主机已安装 Certbot、Nginx 插件并启用每天两次的 `certbot.timer`，但尚未签发任何证书；
- Compose Nginx 当前把 `43120` 发布到所有宿主机地址，而不是只绑定回环地址；
- 生产 `.env` 当前显式设置 `ALLOW_INSECURE_HTTP_AUTH=true`，因此 Core 会签发不带 `Secure` 的会话 Cookie。

当前真实链路为：

```text
浏览器
  -> 宿主机 Nginx :80
  -> Compose Nginx 127.0.0.1:43120
  -> Web / Core API
```

仓库此前只记录了 Compose Nginx，未记录宿主机 Nginx 这一层。实现必须以当前生产事实为准，并把该边界补入仓库配置与运维文档。

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

- 仓库新增宿主机 Nginx 模板，生产文件固定为 `/etc/nginx/conf.d/inkforge.conf`。
- 修改前把原配置复制到不被 Nginx include 的备份目录，并保留时间戳、属主和权限。
- HTTP server 仅保留 ACME challenge，其余请求使用 308 跳转到根域 HTTPS，并保留原路径和查询字符串。
- HTTPS 根域 server 反代到 `127.0.0.1:43120`，显式传递 `Host`、客户端地址和 `X-Forwarded-Proto=https`。
- HTTPS `www` server 只做 308 根域跳转。
- TLS 只允许 1.2 和 1.3，使用 Certbot 提供的安全参数；启用 HSTS，但不启用 `preload` 或 `includeSubDomains`。
- `/internal/**` 在宿主机和 Compose Nginx 两层都返回 404。
- API 路径继续关闭 proxy buffering/cache，并保留 3600 秒读写超时，避免破坏 SSE。

### Compose 边界与转发协议

- `infra/compose.yaml` 把 Nginx 端口改为 `127.0.0.1:${INKFORGE_PORT:-43120}:8080`。
- Compose Nginx 只接受来自宿主机回环代理的入口，不再直接发布到所有宿主机地址。
- Compose Nginx 在上游明确传入 `https` 时保留该协议；没有受信任上游值时回退到自身 `$scheme`。
- 内部 Web、Core、Agent 与 Redis 网络不变，容器仍保持非 root、只读根文件系统和现有资源限制。

### 会话安全恢复

- 修改生产 `.env` 前创建权限不宽于原文件的时间戳备份。
- 删除 `ALLOW_INSECURE_HTTP_AUTH=true`，让 Compose 默认值 `false` 生效。
- 只重建 Core API 容器以加载新环境，随后验证 Core readiness、Compose smoke 和容器环境中的布尔状态。
- HTTPS 生效后不得继续向生产 Skill 或 CLI 注入远程 HTTP 放行；生产 origin 改为 `https://inkforge.cn`。

## 实施顺序

1. 再次确认两个域名解析、80 可达、应用健康和磁盘空间。
2. 备份宿主机 Nginx 配置与生产 `.env`。
3. 安装 ACME webroot 的临时 HTTP 配置并通过 `nginx -t`。
4. 为根域与 `www` 签发证书。
5. 安装最终 HTTPS 配置和续期 deploy hook，验证后 reload Nginx。
6. 从公网验证证书链、SAN、HTTP/www 跳转、页面、API readiness 和 `/internal/**` 404。
7. 删除生产 HTTP Cookie 放行并重建 Core API，重新执行健康检查。
8. 把宿主机配置模板、Compose 回环绑定、转发协议、测试和文档提交到仓库。
9. 发布仓库变更后监控完整 CI 与生产部署；再次验证 HTTPS 和自动续期 dry-run。
10. 把生产操作员 Skill 切换到 HTTPS，删除明文放行配置与说明。

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

### 生产验收

- `https://inkforge.cn/` 返回 200，证书链受信任，SAN 包含根域与 `www`，证书未过期。
- `http://inkforge.cn/**`、`http://www.inkforge.cn/**` 和 `https://www.inkforge.cn/**` 返回 308，并保留路径与查询字符串。
- TLS 1.0/1.1 失败，TLS 1.2/1.3 可用。
- `https://inkforge.cn/api/v1/health/ready` 返回 ready。
- `https://inkforge.cn/internal/v1/health/live` 返回 404。
- Compose 五个服务保持 healthy，schema 指纹检查和现有 smoke 通过。
- Core 运行环境不再启用 `ALLOW_INSECURE_HTTP_AUTH`，生产配置仍签发 `Secure` Cookie。
- `certbot renew --dry-run` 成功，deploy hook 能在配置有效时 reload Nginx。
- 公网 43120 不可直接访问；宿主机 Nginx仍能通过 `127.0.0.1:43120` 访问应用。

## 已知独立风险

只读核查发现宿主机 PostgreSQL 5432 和 Redis 6379 正监听公网地址，且公网 TCP 可达。这与“仅 Nginx 公网入口”的项目边界不符，风险高于普通配置清理。由于关闭端口可能影响未知运维来源，本规格只记录事实，不在 HTTPS 操作中顺手修改；必须另开安全收敛任务，核对云安全组、监听地址、认证和容器访问后处理。
