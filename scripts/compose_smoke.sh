#!/bin/sh
set -eu

port="${INKFORGE_PORT:-80}"
base_url="http://127.0.0.1:${port}"
env_file="${COMPOSE_ENV_FILE:-.env}"
override_file="${COMPOSE_OVERRIDE_FILE:-}"

compose() {
  if [ -n "$override_file" ]; then
    docker compose --env-file "$env_file" -f infra/compose.yaml -f "$override_file" "$@"
  else
    docker compose --env-file "$env_file" -f infra/compose.yaml "$@"
  fi
}

compose ps
curl --fail --silent --show-error "${base_url}/login" >/dev/null
curl --fail --silent --show-error "${base_url}/api/v1/health/ready" | grep -q '"status":"ready"'
status="$(curl --silent --output /dev/null --write-out '%{http_code}' "${base_url}/internal/v1/health/live")"
[ "$status" = "404" ]
compose exec -T agent-service python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/internal/v1/health/ready', timeout=3)"
echo "编排冒烟检查通过"
