#!/bin/sh
set -eu

env_file="${COMPOSE_ENV_FILE:-.env}"
override_file="${COMPOSE_OVERRIDE_FILE:-}"
agent_max_attempts="${SMOKE_AGENT_MAX_ATTEMPTS:-45}"
agent_required_successes="${SMOKE_AGENT_REQUIRED_SUCCESSES:-5}"
agent_poll_seconds="${SMOKE_AGENT_POLL_SECONDS:-2}"

compose() {
  if [ -n "$override_file" ]; then
    docker compose --env-file "$env_file" -f infra/compose.yaml -f "$override_file" "$@"
  else
    docker compose --env-file "$env_file" -f infra/compose.yaml "$@"
  fi
}

case "$agent_max_attempts" in
  ''|*[!0-9]*|0)
    echo "SMOKE_AGENT_MAX_ATTEMPTS 必须是正整数" >&2
    exit 1
    ;;
esac

case "$agent_required_successes" in
  ''|*[!0-9]*|0)
    echo "SMOKE_AGENT_REQUIRED_SUCCESSES 必须是正整数" >&2
    exit 1
    ;;
esac

case "$agent_poll_seconds" in
  ''|*[!0-9]*)
    echo "SMOKE_AGENT_POLL_SECONDS 必须是非负整数" >&2
    exit 1
    ;;
esac

if [ "$agent_required_successes" -gt "$agent_max_attempts" ]; then
  echo "SMOKE_AGENT_REQUIRED_SUCCESSES 不能大于 SMOKE_AGENT_MAX_ATTEMPTS" >&2
  exit 1
fi

compose ps
binding="$(compose port nginx 8080 | head -n 1)"
port="${binding##*:}"
case "$port" in
  ''|*[!0-9]*)
    echo "无法解析 Nginx 发布端口" >&2
    exit 1
    ;;
esac
base_url="http://127.0.0.1:${port}"

curl --fail --silent --show-error "${base_url}/login" >/dev/null
curl --fail --silent --show-error "${base_url}/api/v1/health/ready" | grep -q '"status":"ready"'
status="$(curl --silent --output /dev/null --write-out '%{http_code}' "${base_url}/internal/v1/health/live")"
[ "$status" = "404" ]

agent_attempts=0
agent_consecutive_successes=0
agent_stable=0
while [ "$agent_attempts" -lt "$agent_max_attempts" ]; do
  agent_attempts=$((agent_attempts + 1))
  agent_output=""
  if agent_output="$(compose exec -T agent-service python - http://127.0.0.1:8001/internal/v1/health/ready < scripts/agent_readiness_probe.py 2>&1)"; then
    agent_consecutive_successes=$((agent_consecutive_successes + 1))
    if [ "$agent_consecutive_successes" -ge "$agent_required_successes" ]; then
      agent_stable=1
      break
    fi
  else
    printf '%s\n' "$agent_output" | while IFS= read -r diagnostic_line; do
      case "$diagnostic_line" in
        INKFORGE_AGENT_READINESS_DIAGNOSTIC=*|INKFORGE_AGENT_READINESS_HTTP_STATUS=*)
          printf '%s\n' "$diagnostic_line" >&2
          ;;
      esac
    done
    agent_consecutive_successes=0
  fi

  if [ "$agent_attempts" -lt "$agent_max_attempts" ] && [ "$agent_poll_seconds" -gt 0 ]; then
    sleep "$agent_poll_seconds"
  fi
done

if [ "$agent_stable" -ne 1 ]; then
  echo "Agent 服务未连续稳定就绪：最多尝试 ${agent_max_attempts} 次，要求连续成功 ${agent_required_successes} 次" >&2
  exit 1
fi

echo "编排冒烟检查通过"
