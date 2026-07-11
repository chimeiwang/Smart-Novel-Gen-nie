#!/bin/sh
set -eu

[ "${ALLOW_STABILITY_DRILL:-no}" = "yes" ] || {
  echo "必须设置 ALLOW_STABILITY_DRILL=yes" >&2
  exit 1
}

duration="${STABILITY_DURATION_SECONDS:-1800}"
case "$duration" in
  *[!0-9]*|'') echo "STABILITY_DURATION_SECONDS 必须是整数" >&2; exit 1 ;;
esac
[ "$duration" -ge 1800 ] || { echo "稳定性验证不得少于 1800 秒" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || { echo "缺少 docker 命令" >&2; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "缺少 npm 命令" >&2; exit 1; }

env_file="${STABILITY_ENV_FILE:-.env.test}"
[ -f "$env_file" ] || { echo "缺少测试环境文件：$env_file" >&2; exit 1; }
grep -q '^TEST_DATABASE_URL=' "$env_file" || {
  echo "测试环境文件缺少 TEST_DATABASE_URL" >&2
  exit 1
}

compose() {
  docker compose --env-file "$env_file" \
    -f infra/compose.yaml -f infra/compose.test.yaml "$@"
}

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
output_dir="${STABILITY_OUTPUT_DIR:-output/stability/$stamp}"
mkdir -p "$output_dir"
resources_file="$output_dir/resources.csv"
baseline_file="$output_dir/restart-baseline.csv"
report_file="$output_dir/report.txt"

printf '%s\n' '时间,容器,处理器,内存,进程数' > "$resources_file"
: > "$baseline_file"

compose config >/dev/null
compose up --build -d --wait

for service in nginx web core-api agent-service redis postgres; do
  container_id="$(compose ps -q "$service")"
  [ -n "$container_id" ] || { echo "服务未运行：$service" >&2; exit 1; }
  restart_count="$(docker inspect --format '{{.RestartCount}}' "$container_id")"
  printf '%s,%s,%s\n' "$service" "$container_id" "$restart_count" >> "$baseline_file"
done

start_time="$(date +%s)"
deadline=$((start_time + duration))
run_count=0
e2e_failures=0

while [ "$(date +%s)" -lt "$deadline" ]; do
  run_count=$((run_count + 1))
  now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  docker stats --no-stream --format "${now},{{.Name}},{{.CPUPerc}},{{.MemUsage}},{{.PIDs}}" \
    $(compose ps -q) >> "$resources_file"

  if ! E2E_BASE_URL="${E2E_BASE_URL:-http://127.0.0.1:${INKFORGE_PORT:-80}}" \
    npm run test:e2e > "$output_dir/e2e-$run_count.log" 2>&1; then
    e2e_failures=$((e2e_failures + 1))
  fi
done

system_failures=0
while IFS=, read -r service container_id baseline_restart_count; do
  current_restart_count="$(docker inspect --format '{{.RestartCount}}' "$container_id")"
  oom_killed="$(docker inspect --format '{{.State.OOMKilled}}' "$container_id")"
  if [ "$current_restart_count" -ne "$baseline_restart_count" ]; then
    echo "容器发生重启：$service" >&2
    system_failures=$((system_failures + 1))
  fi
  if [ "$oom_killed" = "true" ]; then
    echo "容器发生 OOMKilled：$service" >&2
    system_failures=$((system_failures + 1))
  fi
done < "$baseline_file"

{
  echo "持续秒数：$duration"
  echo "端到端轮数：$run_count"
  echo "端到端失败数：$e2e_failures"
  echo "容器异常数：$system_failures"
  echo "资源采样：$resources_file"
} | tee "$report_file"

[ "$run_count" -gt 0 ] || { echo "稳定性验证未完成任何端到端轮次" >&2; exit 1; }
[ "$e2e_failures" -eq 0 ] || { echo "稳定性验证存在端到端失败" >&2; exit 1; }
[ "$system_failures" -eq 0 ] || { echo "稳定性验证存在容器异常" >&2; exit 1; }

echo "2 核 2 GB 稳定性验证通过"
