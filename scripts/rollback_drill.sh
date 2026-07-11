#!/bin/sh
set -eu

[ "${ALLOW_ROLLBACK_DRILL:-no}" = "yes" ] || { echo "必须设置 ALLOW_ROLLBACK_DRILL=yes" >&2; exit 1; }
: "${CURRENT_IMAGE_TAG:?必须设置当前 Python 三服务镜像标签}"
: "${ROLLBACK_IMAGE_TAG:?必须设置已验证的回滚镜像标签}"
[ "$CURRENT_IMAGE_TAG" != "$ROLLBACK_IMAGE_TAG" ] || { echo "当前标签与回滚标签不能相同" >&2; exit 1; }

env_file="${ROLLBACK_ENV_FILE:-.env.test}"
override_file="${ROLLBACK_COMPOSE_OVERRIDE_FILE:-infra/compose.test.yaml}"
[ "$override_file" = "infra/compose.test.yaml" ] || {
  echo "回滚演练只能使用 infra/compose.test.yaml" >&2
  exit 1
}
[ -f "$env_file" ] || { echo "缺少回滚测试环境文件：$env_file" >&2; exit 1; }
grep -q '^TEST_DATABASE_URL=' "$env_file" || { echo "回滚环境缺少 TEST_DATABASE_URL" >&2; exit 1; }

for image in \
  "inkforge-web:$CURRENT_IMAGE_TAG" \
  "inkforge-core-api:$CURRENT_IMAGE_TAG" \
  "inkforge-agent-service:$CURRENT_IMAGE_TAG"; do
  docker image inspect "$image" >/dev/null 2>&1 || { echo "缺少当前镜像：$image" >&2; exit 1; }
done

for image in \
  "inkforge-web:$ROLLBACK_IMAGE_TAG" \
  "inkforge-core-api:$ROLLBACK_IMAGE_TAG" \
  "inkforge-agent-service:$ROLLBACK_IMAGE_TAG"; do
  docker image inspect "$image" >/dev/null 2>&1 || { echo "缺少回滚镜像：$image" >&2; exit 1; }
done

compose() {
  docker compose --env-file "$env_file" \
    -f infra/compose.yaml -f "$override_file" "$@"
}

schema_fingerprint() {
  compose exec -T core-api python -c \
    'import asyncio, os; from inkforge_core.db.schema_guard import verify_live_schema; from inkforge_core.db.session import SCHEMA_CONTRACT_PATH; result = asyncio.run(verify_live_schema(os.environ["DATABASE_URL"], SCHEMA_CONTRACT_PATH)); print(result.fingerprint); raise SystemExit(0 if result.ready else 1)'
}

restore_current() {
  export INKFORGE_IMAGE_TAG="$CURRENT_IMAGE_TAG"
  compose up -d --no-build --wait
}

cleanup() {
  status=$?
  trap - EXIT
  if ! restore_current; then
    echo "无法自动恢复当前镜像栈" >&2
    status=1
  fi
  exit "$status"
}
trap cleanup EXIT

before_fingerprint="$(schema_fingerprint)"

export INKFORGE_IMAGE_TAG="$ROLLBACK_IMAGE_TAG"
compose up -d --no-build --wait
COMPOSE_ENV_FILE="$env_file" COMPOSE_OVERRIDE_FILE="$override_file" scripts/compose_smoke.sh
E2E_BASE_URL="${E2E_BASE_URL:-http://127.0.0.1:${INKFORGE_PORT:-80}}" npm run test:e2e
after_fingerprint="$(schema_fingerprint)"
[ "$before_fingerprint" = "$after_fingerprint" ] || { echo "回滚前后数据库结构指纹不一致" >&2; exit 1; }

echo "上一版 Python 三服务镜像回滚演练通过：$ROLLBACK_IMAGE_TAG"
