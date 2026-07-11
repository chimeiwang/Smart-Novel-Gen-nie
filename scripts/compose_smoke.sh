#!/bin/sh
set -eu

port="${INKFORGE_PORT:-80}"
base_url="http://127.0.0.1:${port}"
compose="docker compose -f infra/compose.yaml -f infra/compose.test.yaml"

$compose ps
curl --fail --silent --show-error "${base_url}/login" >/dev/null
curl --fail --silent --show-error "${base_url}/api/v1/health/ready" | grep -q '"status":"ready"'
status="$(curl --silent --output /dev/null --write-out '%{http_code}' "${base_url}/internal/v1/health/live")"
[ "$status" = "404" ]
$compose exec -T agent-service python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/internal/v1/health/ready', timeout=3)"
echo "编排冒烟检查通过"
