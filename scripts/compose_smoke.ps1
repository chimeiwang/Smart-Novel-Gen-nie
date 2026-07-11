$ErrorActionPreference = "Stop"
$compose = @("compose", "-f", "infra/compose.yaml", "-f", "infra/compose.test.yaml")
$port = if ($env:INKFORGE_PORT) { $env:INKFORGE_PORT } else { "80" }
$baseUrl = "http://127.0.0.1:$port"

docker @compose ps
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
