$ErrorActionPreference = "Stop"
$envFile = if ($env:COMPOSE_ENV_FILE) { $env:COMPOSE_ENV_FILE } else { ".env" }
$compose = @("compose", "--env-file", $envFile, "-f", "infra/compose.yaml")
if ($env:COMPOSE_OVERRIDE_FILE) {
    $compose += @("-f", $env:COMPOSE_OVERRIDE_FILE)
}
if ($env:COMPOSE_ADDITIONAL_OVERRIDE_FILE) {
    $compose += @("-f", $env:COMPOSE_ADDITIONAL_OVERRIDE_FILE)
}
$port = if ($env:INKFORGE_PORT) { $env:INKFORGE_PORT } else { "80" }
$baseUrl = "http://127.0.0.1:$port"

docker @compose ps
$coreWriteProbe = @'
set -eu
upload_root="${UPLOADS_ROOT:?缺少 UPLOADS_ROOT}"
test -d "$upload_root"
probe_dir="$upload_root/.inkforge-write-probe-$$"
mkdir "$probe_dir"
rmdir "$probe_dir"
'@
docker @compose exec -T core-api sh -c $coreWriteProbe
if ($LASTEXITCODE -ne 0) { throw "Core 上传目录不可写" }

$agentWriteProbe = @'
set -eu
log_dir="${WORKFLOW_HUMAN_LOG_DIR:?缺少 WORKFLOW_HUMAN_LOG_DIR}"
test -d "$log_dir"
probe_dir="$log_dir/.inkforge-write-probe-$$"
mkdir "$probe_dir"
rmdir "$probe_dir"
'@
docker @compose exec -T agent-service sh -c $agentWriteProbe
if ($LASTEXITCODE -ne 0) { throw "Agent 人工日志目录不可写" }

$page = Invoke-WebRequest -UseBasicParsing "$baseUrl/login"
if ($page.StatusCode -ne 200) { throw "登录页面不可用" }

$health = Invoke-RestMethod "$baseUrl/api/v1/health/ready"
if ($health.status -ne "ready") { throw "核心接口服务未就绪" }

try {
    Invoke-WebRequest -UseBasicParsing "$baseUrl/internal/v1/health/live"
    throw "内部接口被错误暴露"
} catch {
    if ($_.Exception.Response.StatusCode.value__ -ne 404) { throw }
}

docker @compose exec -T agent-service python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/internal/v1/health/ready', timeout=3)"
Write-Host "编排冒烟检查通过"
