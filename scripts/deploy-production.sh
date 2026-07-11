#!/bin/sh
set -eu

compose_file="infra/compose.yaml"

command -v docker >/dev/null 2>&1 || { echo "缺少 docker 命令" >&2; exit 1; }
[ -f .env ] || { echo "缺少 .env" >&2; exit 1; }
[ -f infra/secrets/core-to-agent-private.pem ] || { echo "缺少服务密钥" >&2; exit 1; }

docker compose --env-file .env -f "$compose_file" config >/dev/null
docker compose --env-file .env -f "$compose_file" up --build -d --wait
docker compose --env-file .env -f "$compose_file" ps
echo "生产编排已启动"
