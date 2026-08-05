# 生产域名 HTTPS 实施计划

> **供 Agent 执行：** 必须使用 `subagent-driven-development`（推荐）或 `executing-plans` 按任务实施；生产写操作只能由主 Agent 串行执行，子 Agent 仅处理仓库实现或只读复核。

**目标：** 让 `inkforge.cn` 和 `www.inkforge.cn` 使用可信 HTTPS，恢复 Secure Cookie，并把 Compose 入口收敛到宿主机回环地址。

**架构：** TLS 终止在现有 Ubuntu 宿主机 Nginx，证书由现有 Certbot 与 systemd timer 管理；宿主机 Nginx 通过 `127.0.0.1:43120` 访问 Compose Nginx。应用容器内部继续使用现有 HTTP 与服务身份，不修改数据库结构或业务数据。

**技术栈：** Ubuntu 22.04、Nginx 1.18、Certbot 1.21、systemd、Docker Compose、pytest、PowerShell/Paramiko。

---

### 任务一：用失败测试锁定公网边界

**文件：**

- 新建：`tests/architecture/test_production_https.py`
- 修改：`tests/architecture/test_compose_security.py`

- [ ] **步骤 1：为 Compose 回环绑定写失败断言**

在 `test_only_nginx_publishes_ports_and_internal_routes_are_blocked` 中加入：

```python
nginx_service = _service_block(source, "nginx")
assert '127.0.0.1:${INKFORGE_PORT:-43120}:8080' in nginx_service
assert '${INKFORGE_PORT:-80}:8080' not in nginx_service
```

- [ ] **步骤 2：为宿主机 TLS 模板和续期 hook 写失败测试**

新建 `tests/architecture/test_production_https.py`：

```python
from pathlib import Path

ROOT = Path(__file__).parents[2]
HOST_NGINX = ROOT / "infra" / "host-nginx" / "inkforge.conf"
BOOTSTRAP_NGINX = ROOT / "infra" / "host-nginx" / "inkforge-http-bootstrap.conf"
RELOAD_HOOK = ROOT / "infra" / "certbot" / "reload-nginx.sh"


def test_host_nginx_terminates_tls_and_keeps_acme_available() -> None:
    source = HOST_NGINX.read_text(encoding="utf-8")
    assert "listen 443 ssl http2;" in source
    assert "server_name inkforge.cn www.inkforge.cn;" in source
    assert "/etc/letsencrypt/live/inkforge.cn/fullchain.pem" in source
    assert "/etc/letsencrypt/live/inkforge.cn/privkey.pem" in source
    assert "location ^~ /.well-known/acme-challenge/" in source
    assert "return 308 https://inkforge.cn$request_uri;" in source
    assert "proxy_pass http://127.0.0.1:43120;" in source
    assert "location ^~ /internal/" in source
    assert "proxy_buffering off;" in source
    assert "proxy_read_timeout 3600s;" in source


def test_http_bootstrap_does_not_require_a_certificate() -> None:
    source = BOOTSTRAP_NGINX.read_text(encoding="utf-8")
    assert "listen 80 default_server;" in source
    assert "location ^~ /.well-known/acme-challenge/" in source
    assert "proxy_pass http://127.0.0.1:43120;" in source
    assert "listen 443" not in source
    assert "ssl_certificate" not in source


def test_certbot_deploy_hook_validates_before_reload() -> None:
    source = RELOAD_HOOK.read_text(encoding="utf-8")
    assert "set -eu" in source
    assert "nginx -t" in source
    assert "systemctl reload nginx" in source


def test_compose_nginx_preserves_trusted_https_scheme() -> None:
    source = (ROOT / "infra" / "nginx" / "nginx.conf").read_text(encoding="utf-8")
    assert "map $http_x_forwarded_proto $inkforge_forwarded_proto" in source
    assert source.count("proxy_set_header X-Forwarded-Proto $inkforge_forwarded_proto;") == 2
```

- [ ] **步骤 3：运行测试并确认按预期失败**

运行：

```powershell
uv run pytest tests/architecture/test_production_https.py tests/architecture/test_compose_security.py -q
```

预期：新模板不存在且 Compose 尚未回环绑定，测试失败；失败原因不得来自依赖安装或数据库连接。

### 任务二：实现仓库内 HTTPS 边界

**文件：**

- 新建：`infra/host-nginx/inkforge-http-bootstrap.conf`
- 新建：`infra/host-nginx/inkforge.conf`
- 新建：`infra/certbot/reload-nginx.sh`
- 修改：`infra/compose.yaml`
- 修改：`infra/nginx/nginx.conf`
- 修改：`.env.example`

- [ ] **步骤 1：新增无证书 HTTP bootstrap 配置**

配置必须以 `listen 80 default_server` 接收当前公网流量；`/.well-known/acme-challenge/` 从 `/var/www/letsencrypt` 提供，其余流量继续反代到 `127.0.0.1:43120`。必须保留 `Host`、真实地址、`X-Forwarded-Proto=http`、关闭 buffering/cache、3600 秒读写超时和 50 MiB 请求体上限。

- [ ] **步骤 2：新增最终宿主机 Nginx 配置**

最终文件必须包含三个 server：

```nginx
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name inkforge.cn www.inkforge.cn;

    location ^~ /.well-known/acme-challenge/ {
        root /var/www/letsencrypt;
        default_type text/plain;
        try_files $uri =404;
    }

    location / {
        return 308 https://inkforge.cn$request_uri;
    }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name www.inkforge.cn;
    ssl_certificate /etc/letsencrypt/live/inkforge.cn/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/inkforge.cn/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
    return 308 https://inkforge.cn$request_uri;
}
```

根域 HTTPS server 使用相同证书，添加 `Strict-Transport-Security: max-age=31536000 always`，先阻断 `/internal/`，再把其他请求反代到 `127.0.0.1:43120`。不得启用 `includeSubDomains` 或 `preload`。

- [ ] **步骤 3：新增 Certbot deploy hook**

`infra/certbot/reload-nginx.sh` 的完整内容为：

```sh
#!/bin/sh
set -eu

nginx -t
systemctl reload nginx
```

- [ ] **步骤 4：收敛 Compose 端口并保留原始协议**

把 `infra/compose.yaml` 的 Nginx发布端口改为：

```yaml
ports:
  - "127.0.0.1:${INKFORGE_PORT:-43120}:8080"
```

在 `infra/nginx/nginx.conf` 的 `http` 块加入：

```nginx
map $http_x_forwarded_proto $inkforge_forwarded_proto {
    default $scheme;
    https https;
}
```

两条代理路径都使用：

```nginx
proxy_set_header X-Forwarded-Proto $inkforge_forwarded_proto;
```

- [ ] **步骤 5：更新环境示例**

`.env.example` 使用 `INKFORGE_PORT=43120`，并明确该端口只由宿主机 Nginx 从回环地址访问；`ALLOW_INSECURE_HTTP_AUTH=false` 说明改为“生产 HTTPS 必须保持 false”。

- [ ] **步骤 6：运行目标测试并提交仓库实现**

运行：

```powershell
uv run pytest tests/architecture/test_production_https.py tests/architecture/test_compose_security.py -q
uv run ruff check tests/architecture/test_production_https.py tests/architecture/test_compose_security.py
git diff --check
```

预期：全部通过。提交信息：`部署：增加生产 HTTPS 边界配置`。

### 任务三：同步当前文档契约

**文件：**

- 修改：`docs/requirements/05-auth-billing-and-ops.md`
- 修改：`README.md`
- 修改：`docs/specs/2026-07-15-temporary-ip-http-auth.md`
- 修改：`docs/specs/2026-08-04-production-short-story-operator-skill.md`
- 修改：`docs/specs/2026-08-05-production-https.md`

- [ ] **步骤 1：把生产链路改为双层 Nginx 事实**

需求和 README 必须明确：公网只到宿主机 80/443，宿主机 Nginx 终止 TLS，Compose Nginx 只绑定 `127.0.0.1:43120`；Certbot timer 负责续期，证书私钥不进入仓库。

- [ ] **步骤 2：关闭历史 HTTP 过渡状态**

临时 HTTP 规格追加实际结束日期和结果；生产操作员规格的入口改为 `https://inkforge.cn`，状态先改为“服务器 HTTPS 已实现，生产操作员 Skill 待迁移”。任务六完成后再改为“已实现”，不再把明文 HTTP 描述为当前生产方案。

- [ ] **步骤 3：把 HTTPS 规格状态改为“仓库实现完成，待生产验收”并提交**

运行 `rg -n "生产入口当前只有 HTTP|http://124\.71\.85\.180|待实施" README.md docs/requirements docs/specs/2026-07-15-temporary-ip-http-auth.md docs/specs/2026-08-04-production-short-story-operator-skill.md docs/specs/2026-08-05-production-https.md`，只允许保留明确标注为历史事实或回退说明的匹配。提交信息：`文档：同步生产 HTTPS 运维边界`。

### 任务四：签发证书并切换宿主机 Nginx

**生产目标：**

- 读取：`/etc/nginx/conf.d/inkforge.conf`
- 新建备份：`/root/inkforge-backups/<时间戳>/inkforge.conf`
- 安装：`/etc/nginx/conf.d/inkforge.conf`
- 安装：`/etc/letsencrypt/renewal-hooks/deploy/reload-nginx`
- 使用：`/var/www/letsencrypt`

- [ ] **步骤 1：执行只读预检**

确认 A 记录仍为服务器 IP、HTTP 页面与 API ready、`nginx -t`、Compose 五服务 healthy、磁盘可用空间大于 1 GiB、Certbot timer active。任一条件不满足时停止写操作。

- [ ] **步骤 2：创建受限备份并安装 bootstrap 配置**

远端以 root 执行：

```sh
set -eu
stamp="$(date +%Y%m%d%H%M%S)"
backup_dir="/root/inkforge-backups/$stamp"
install -d -m 700 "$backup_dir"
cp -a /etc/nginx/conf.d/inkforge.conf "$backup_dir/inkforge.conf"
install -d -m 755 /var/www/letsencrypt
install -m 644 /tmp/inkforge-http-bootstrap.conf /etc/nginx/conf.d/inkforge.conf
nginx -t
systemctl reload nginx
```

主 Agent通过已核验 `known_hosts` 的 SSH/SFTP 上传 `/tmp/inkforge-http-bootstrap.conf`，不得在日志输出密码。

- [ ] **步骤 3：签发根域与 www 证书**

远端执行：

```sh
certbot certonly \
  --webroot --webroot-path /var/www/letsencrypt \
  --cert-name inkforge.cn \
  --domain inkforge.cn --domain www.inkforge.cn \
  --non-interactive --agree-tos --register-unsafely-without-email
```

预期：`certbot certificates` 显示一个包含两个域名且状态有效的 `inkforge.cn` 证书。

- [ ] **步骤 4：安装最终配置和续期 hook**

上传最终模板与 hook 到 `/tmp`，然后执行：

```sh
install -m 644 /tmp/inkforge.conf /etc/nginx/conf.d/inkforge.conf
install -d -m 755 /etc/letsencrypt/renewal-hooks/deploy
install -m 755 /tmp/reload-nginx.sh /etc/letsencrypt/renewal-hooks/deploy/reload-nginx
nginx -t
systemctl reload nginx
ss -ltnp | grep -E ':(80|443)[[:space:]]'
```

若 `nginx -t` 或 reload 失败，立即从本次 `backup_dir` 恢复并 reload，不继续改会话配置。

- [ ] **步骤 5：执行第一次公网验收**

从本机绕过代理验证根域 HTTPS 200、三条 308 跳转、证书 SAN/签发者/有效期、API ready、`/internal/**` 404、TLS 1.0/1.1 拒绝和 TLS 1.2/1.3 成功。

### 任务五：恢复 Secure Cookie 并发布仓库收敛

**生产文件：**

- 修改：`/srv/smart-novel-gen/.env`
- 备份：`/root/inkforge-backups/<时间戳>/.env`

- [ ] **步骤 1：备份并移除临时 HTTP 放行**

远端执行：

```sh
set -eu
cd /srv/smart-novel-gen
stamp="$(date +%Y%m%d%H%M%S)"
backup_dir="/root/inkforge-backups/$stamp"
install -d -m 700 "$backup_dir"
cp -a .env "$backup_dir/.env"
awk '!/^ALLOW_INSECURE_HTTP_AUTH=/' .env > .env.https.tmp
chmod --reference=.env .env.https.tmp
chown --reference=.env .env.https.tmp
mv .env.https.tmp .env
docker compose --env-file .env -f infra/compose.yaml up --no-build -d --wait --no-deps --force-recreate core-api
```

- [ ] **步骤 2：验证 Core 和 HTTPS 后再推送**

确认 Core 容器环境为 `ALLOW_INSECURE_HTTP_AUTH=false`、五服务 healthy、schema 只读指纹和 `scripts/compose_smoke.sh` 通过，公网 HTTPS/API/404 仍正确。

- [ ] **步骤 3：披露并推送完整 main 范围**

运行 `git fetch origin main`、`git log --oneline origin/main..main` 和 `git diff --stat origin/main...main`。在推送前明确列出本地此前的长篇 CLI 规格提交、HTTPS 规格、计划、实现与文档提交。随后执行 `git push origin main`。

- [ ] **步骤 4：监控 GitHub Actions 到终态**

使用 `gh run list` 找到本次 main push 的运行，使用 `gh run watch <run-id> --exit-status` 等到 CI 与 deploy 完成。失败时读取实际 job/step 日志；不得把“push 成功”当成“生产部署成功”。

- [ ] **步骤 5：验证回环收敛**

部署成功后确认 Compose Nginx 仅显示 `127.0.0.1:43120->8080`；宿主机能访问回环 upstream，而公网 43120 不可达；HTTPS 端到端仍通过。

### 任务六：迁移生产操作员 Skill 到 HTTPS

**前置子技能：** 修改前必须读取并遵循 `writing-skills`。

**文件：**

- 修改：`C:/Users/niebo/.codex/skills/inkforge-production-short-story-operator/SKILL.md`
- 修改：`C:/Users/niebo/.codex/skills/inkforge-production-short-story-operator/references/cli-contract.md`
- 修改：`C:/Users/niebo/.codex/skills/inkforge-production-short-story-operator/references/recovery.md`
- 修改：`C:/Users/niebo/.codex/skills/inkforge-production-short-story-operator/scripts/configure.ps1`
- 修改：`C:/Users/niebo/.codex/skills/inkforge-production-short-story-operator/scripts/operator.ps1`

- [ ] **步骤 1：先写/更新 wrapper 失败测试**

测试必须断言固定 origin 是 `https://inkforge.cn`，子进程不存在 `INKFORGE_CLI_ALLOW_INSECURE_HTTP_ORIGIN`，配置不再包含 `acceptedInsecureHttp`，旧 schema v2 明确要求重新配置而不是静默迁移。

- [ ] **步骤 2：把配置升级到 schema v3**

`configure.ps1` 只保存：

```powershell
$config = [ordered]@{
    schemaVersion = 3
    repositoryRoot = $resolvedRepositoryRoot
    expectedUsername = $normalizedUsername
}
```

删除 `-AcceptInsecureHttp` 和明文 HTTP 警告，输出固定 HTTPS origin。

- [ ] **步骤 3：删除 wrapper 的 HTTP 放行路径**

`operator.ps1` 使用：

```powershell
$script:ProductionOrigin = 'https://inkforge.cn'
$script:ProductionProfile = 'production'
```

删除 `InsecureOriginEnvironment`、`acceptedInsecureHttp` 校验和子进程环境变量注入/恢复逻辑；保留身份预检、命令白名单、profile 与 origin 固定规则。

- [ ] **步骤 4：同步 Skill 与 references 并验证**

文档不得再把生产链路描述为 HTTP 或要求接受明文风险。运行 Skill 自带的 PowerShell 测试和 `quick_validate.py`；最后执行一次不写业务数据的 `auth.whoami` 或 `short.list`，若 profile 因 origin 变化而未登录，只报告需要用户在真实终端重新登录，不索取密码。

### 任务七：最终验证与状态收口

**文件：**

- 修改：`docs/specs/2026-08-05-production-https.md`
- 修改：`docs/plans/2026-08-05-production-https.md`

- [ ] **步骤 1：运行仓库验证**

```powershell
uv run pytest tests/architecture/test_production_https.py tests/architecture/test_compose_security.py tests/architecture/test_deploy_scripts.py tests/architecture/test_github_workflow.py -q
uv run pytest
uv run ruff check .
uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src
npm run typecheck
npm run lint
npm run build
git diff --check
```

本机没有 Docker 时必须明确记录跳过本地 Compose 健康检查，并以成功的 GitHub Actions 生产构建/部署和远端 Compose 验收补充证据。

- [ ] **步骤 2：验证自动续期**

远端运行 `certbot renew --dry-run`，确认成功后 deploy hook 的 `nginx -t` 与 reload 没有错误；重新读取当前线上证书，证明服务仍使用正式证书而非 staging 证书。

- [ ] **步骤 3：更新状态并提交**

把 HTTPS 规格状态改为“已实现”，记录实际证书名称、续期 timer、回退备份目录和验收时间；把本计划已执行任务勾选。提交信息：`运维：完成生产 HTTPS 验收`。

- [ ] **步骤 4：交付精确结果**

报告域名、HTTP/HTTPS 状态、证书 SAN/签发者/有效期、TLS 版本、Secure Cookie 配置、Certbot timer/dry-run、Compose 绑定、Git 分支/提交/远端 ref、Actions run URL 和未处理的 5432/6379 风险。不得输出任何凭据或私钥内容。
