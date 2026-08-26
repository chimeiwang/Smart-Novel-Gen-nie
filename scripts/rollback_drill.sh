#!/bin/sh
set -eu

[ "${ALLOW_ROLLBACK_DRILL:-no}" = "yes" ] || { echo "必须设置 ALLOW_ROLLBACK_DRILL=yes" >&2; exit 1; }
: "${CURRENT_IMAGE_TAG:?必须设置当前 Java 三服务镜像标签}"
: "${ROLLBACK_IMAGE_TAG:?必须设置已验证的回滚镜像标签}"
[ "$CURRENT_IMAGE_TAG" != "$ROLLBACK_IMAGE_TAG" ] || { echo "当前标签与回滚标签不能相同" >&2; exit 1; }

env_file="${ROLLBACK_ENV_FILE:-.env.test}"
override_file="${ROLLBACK_COMPOSE_OVERRIDE_FILE:-infra/compose.test.yaml}"
python_rollback_file="infra/compose.python-core-rollback.yaml"
[ "$override_file" = "infra/compose.test.yaml" ] || {
  echo "回滚演练只能使用 infra/compose.test.yaml" >&2
  exit 1
}
# 演练被硬限制在测试覆盖层和 TEST_DATABASE_URL，不能把“验证回滚”变成一次生产切换。
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

core_image_runtime_label() {
  docker image inspect \
    --format '{{ index .Config.Labels "cn.inkforge.core.runtime" }}' "$1"
}

classify_core_runtime() {
  case "$1" in
    java) printf '%s\n' java ;;
    ""|"<no value>") printf '%s\n' python ;;
    *) printf '%s\n' unknown ;;
  esac
}

current_runtime="$(classify_core_runtime "$(core_image_runtime_label "inkforge-core-api:$CURRENT_IMAGE_TAG")")"
[ "$current_runtime" = "java" ] || {
  echo "当前 Core 镜像必须是 Java runtime" >&2
  exit 1
}
rollback_runtime="$(classify_core_runtime "$(core_image_runtime_label "inkforge-core-api:$ROLLBACK_IMAGE_TAG")")"
[ "$rollback_runtime" != "unknown" ] || {
  echo "回滚 Core 镜像 runtime 标签无法识别" >&2
  exit 1
}
if [ "$rollback_runtime" = "python" ]; then
  [ -f "$python_rollback_file" ] || { echo "缺少历史 Python Core 回滚编排" >&2; exit 1; }
fi

compose_java() {
  docker compose --env-file "$env_file" \
    -f infra/compose.yaml -f "$override_file" "$@"
}

compose_python() {
  docker compose --env-file "$env_file" \
    -f infra/compose.yaml -f "$override_file" -f "$python_rollback_file" "$@"
}

compose_for_runtime() {
  runtime="$1"
  shift
  if [ "$runtime" = "python" ]; then
    compose_python "$@"
  else
    compose_java "$@"
  fi
}

# 指纹统一投影到 v1 兼容面，允许比较历史 Python guard 与 Java guard，而不掩盖真实表结构差异。
java_schema_fingerprint() {
  compose_java exec -T core-api /usr/local/bin/inkforge-schema-guard \
    --compatibility-fingerprint-v1
}

python_schema_fingerprint() {
  compose_python exec -T core-api python -c \
    'import asyncio, inspect, os; from inkforge_core.config import Settings; import inkforge_core.db.schema_guard as guard; from inkforge_core.db import session as db_session; database_url = os.environ["DATABASE_URL"]; profile_factory = getattr(db_session, "schema_profile_for_settings", lambda _settings: "full"); profile = profile_factory(Settings()); verify_options = {"profile": profile} if "profile" in inspect.signature(guard.verify_live_schema).parameters else {}; result = asyncio.run(guard.verify_live_schema(database_url, db_session.SCHEMA_CONTRACT_PATH, **verify_options)); contract = guard.load_schema_contract(db_session.SCHEMA_CONTRACT_PATH); actual = asyncio.run(guard._inspect_live(database_url, str(contract.get("schema", "public")))); projector = getattr(guard, "project_schema_contract", None); actual = projector(actual, profile) if projector is not None else actual; actual["contractVersion"] = 1; [table.pop("checkConstraints", None) for table in actual["tables"]]; print(guard.canonical_fingerprint(actual)); raise SystemExit(0 if result.ready else 1)'
}

schema_fingerprint() {
  if [ "$1" = "python" ]; then
    python_schema_fingerprint
  else
    java_schema_fingerprint
  fi
}

run_smoke() {
  runtime="$1"
  if [ "$runtime" = "python" ]; then
    COMPOSE_ENV_FILE="$env_file" \
      COMPOSE_OVERRIDE_FILE="$override_file" \
      COMPOSE_ADDITIONAL_OVERRIDE_FILE="$python_rollback_file" \
      sh scripts/compose_smoke.sh
  else
    COMPOSE_ENV_FILE="$env_file" \
      COMPOSE_OVERRIDE_FILE="$override_file" \
      COMPOSE_ADDITIONAL_OVERRIDE_FILE= \
      sh scripts/compose_smoke.sh
  fi
}

restore_current() {
  export INKFORGE_IMAGE_TAG="$CURRENT_IMAGE_TAG"
  compose_java up -d --no-build --wait &&
  compose_java exec -T core-api /usr/local/bin/inkforge-schema-guard >/dev/null &&
  run_smoke java
}

cleanup() {
  status=$?
  trap - EXIT
  # 无论演练成功还是中途失败，退出前都恢复并验证当前 Java 栈，同时保留原失败状态。
  if ! restore_current; then
    echo "无法自动恢复当前 Java 镜像栈" >&2
    status=1
  fi
  exit "$status"
}
trap cleanup EXIT

export INKFORGE_IMAGE_TAG="$CURRENT_IMAGE_TAG"
before_fingerprint="$(schema_fingerprint java)"

# 顺序验证“旧栈可启动 → 冒烟/E2E 可用 → schema 未漂移”；EXIT trap 随后恢复当前 Java 栈。
export INKFORGE_IMAGE_TAG="$ROLLBACK_IMAGE_TAG"
compose_for_runtime "$rollback_runtime" up -d --no-build --wait
run_smoke "$rollback_runtime"
E2E_BASE_URL="${E2E_BASE_URL:-http://127.0.0.1:${INKFORGE_PORT:-80}}" npm run test:e2e
after_fingerprint="$(schema_fingerprint "$rollback_runtime")"
[ "$before_fingerprint" = "$after_fingerprint" ] || { echo "回滚前后数据库结构指纹不一致" >&2; exit 1; }

echo "上一版 ${rollback_runtime} 三服务镜像回滚演练通过：$ROLLBACK_IMAGE_TAG"
