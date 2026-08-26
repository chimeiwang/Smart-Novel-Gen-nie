#!/bin/sh
set -eu

env_file="${COMPOSE_ENV_FILE:-.env}"
override_file="${COMPOSE_OVERRIDE_FILE:-}"
additional_override_file="${COMPOSE_ADDITIONAL_OVERRIDE_FILE:-}"
agent_max_attempts="${SMOKE_AGENT_MAX_ATTEMPTS:-45}"
agent_required_successes="${SMOKE_AGENT_REQUIRED_SUCCESSES:-5}"
agent_poll_seconds="${SMOKE_AGENT_POLL_SECONDS:-2}"

compose() {
  if [ -n "$override_file" ]; then
    if [ -n "$additional_override_file" ]; then
      docker compose --env-file "$env_file" -f infra/compose.yaml \
        -f "$override_file" -f "$additional_override_file" "$@"
    else
      docker compose --env-file "$env_file" -f infra/compose.yaml -f "$override_file" "$@"
    fi
  elif [ -n "$additional_override_file" ]; then
    docker compose --env-file "$env_file" -f infra/compose.yaml \
      -f "$additional_override_file" "$@"
  else
    docker compose --env-file "$env_file" -f infra/compose.yaml "$@"
  fi
}

# 先验证轮询参数，避免容器已被探测后才因无效配置产生误导性结果。
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
# 写探针只创建并删除专用空目录：同时验证卷权限，又不覆盖任何真实上传或日志。
compose exec -T core-api sh -c '
set -eu
upload_root="${UPLOADS_ROOT:?缺少 UPLOADS_ROOT}"
test -d "$upload_root"
probe_dir="$upload_root/.inkforge-write-probe-$$"
mkdir "$probe_dir"
rmdir "$probe_dir"
'
compose exec -T agent-service sh -c '
set -eu
log_dir="${WORKFLOW_HUMAN_LOG_DIR:?缺少 WORKFLOW_HUMAN_LOG_DIR}"
test -d "$log_dir"
probe_dir="$log_dir/.inkforge-write-probe-$$"
mkdir "$probe_dir"
rmdir "$probe_dir"
'
binding="$(compose port nginx 8080 | head -n 1)"
port="${binding##*:}"
case "$port" in
  ''|*[!0-9]*)
    echo "无法解析 Nginx 发布端口" >&2
    exit 1
    ;;
esac
base_url="http://127.0.0.1:${port}"

# 从唯一公网入口同时验证页面与公共 API，并确认内部路由没有被 Nginx 暴露。
curl --fail --silent --show-error "${base_url}/login" >/dev/null
curl --fail --silent --show-error "${base_url}/api/v1/health/ready" | grep -q '"status":"ready"'
status="$(curl --silent --output /dev/null --write-out '%{http_code}' "${base_url}/internal/v1/health/live")"
[ "$status" = "404" ]

agent_attempts=0
agent_consecutive_successes=0
agent_stable=0
# 连续成功用于识别“短暂 ready 后重启”的假健康，而不是一次探测成功就放行部署。
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
