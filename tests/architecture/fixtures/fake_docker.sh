#!/bin/sh
set -u

printf 'tag=%s|docker %s\n' "${INKFORGE_IMAGE_TAG:-}" "$*" >> "$FAKE_DOCKER_LOG"

if [ "${1:-}" = "compose" ]; then
  case " $* " in
    *" version "*) exit 0 ;;
    *" config "*) exit 0 ;;
    *" up "*)
      if [ "${INKFORGE_IMAGE_TAG:-}" = "${FAKE_NEW_TAG:-new-tag}" ]; then
        exit "${FAKE_NEW_UP_STATUS:-0}"
      fi
      exit "${FAKE_ROLLBACK_UP_STATUS:-0}"
      ;;
    *" ps "*) exit 0 ;;
    *" port nginx 8080 "*) printf '%s\n' "${FAKE_NGINX_BINDING:-0.0.0.0:80}"; exit 0 ;;
    *" exec -T core-api /usr/local/bin/inkforge-schema-guard "*) exit "${FAKE_SCHEMA_VERIFY_STATUS:-0}" ;;
    *" exec -T core-api python -c "*) exit "${FAKE_SCHEMA_VERIFY_STATUS:-0}" ;;
    *" exec -T core-api sh -c "*) exit "${FAKE_CORE_UPLOAD_WRITE_STATUS:-0}" ;;
    *" exec -T agent-service sh -c "*) exit "${FAKE_AGENT_LOG_WRITE_STATUS:-0}" ;;
    *" exec -T agent-service "*)
      if [ -n "${FAKE_AGENT_READY_COUNTER:-}" ]; then
        count=0
        if [ -f "$FAKE_AGENT_READY_COUNTER" ]; then
          count="$(cat "$FAKE_AGENT_READY_COUNTER")"
        fi
        count=$((count + 1))
        printf '%s\n' "$count" > "$FAKE_AGENT_READY_COUNTER"
        if [ -n "${FAKE_AGENT_READY_SEQUENCE:-}" ]; then
          state="$FAKE_AGENT_READY_SEQUENCE"
          sequence_index="$count"
          while [ "$sequence_index" -gt 1 ]; do
            case "$state" in
              *,*) state="${state#*,}" ;;
              *) state=""; break ;;
            esac
            sequence_index=$((sequence_index - 1))
          done
          state="${state%%,*}"
        elif [ "$count" -lt "${FAKE_AGENT_READY_AFTER:-1}" ]; then
          state="not_ready"
        else
          state="ready"
        fi
        case "$state" in
          ready) ;;
          not_ready)
            printf '%s\n' '{"status":"not_ready","backgroundTasks":{"code":"BACKGROUND_TASK_BACKOFF"},"sensitiveToken":"fixture-sensitive-token"}' >&2
            printf '%s\n' 'INKFORGE_AGENT_READINESS_DIAGNOSTIC={"status":"not_ready","backgroundTasks":{"code":"BACKGROUND_TASK_BACKOFF"}}' >&2
            exit 1
            ;;
          *)
            printf 'FAKE_AGENT_READY_SEQUENCE 状态无效: %s\n' "$state" >&2
            exit 2
            ;;
        esac
      fi
      exit "${FAKE_VERIFY_STATUS:-0}"
      ;;
    *" exec "*) exit "${FAKE_VERIFY_STATUS:-0}" ;;
  esac
fi

if [ "${1:-}" = "ps" ]; then
  service=""
  for argument in "$@"; do
    case "$argument" in
      label=com.docker.compose.service=*) service="${argument##*=}" ;;
    esac
  done
  case "${FAKE_PREVIOUS_STATE:-valid}:$service" in
    none:*) exit 0 ;;
    partial:web) printf '%s\n' "container-web" ;;
    partial:*) exit 0 ;;
    *:web|*:core-api|*:agent-service) printf '%s\n' "container-$service" ;;
  esac
  exit 0
fi

if [ "${1:-}" = "inspect" ]; then
  inspect_format=""
  container=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --format)
        inspect_format="${2:-}"
        shift 2
        ;;
      *)
        container="$1"
        shift
        ;;
    esac
  done
  service="${container#container-}"
  case "$inspect_format" in
    '{{.Image}}')
      printf 'sha256:previous-%s-id\n' "$service"
      ;;
    '{{.Config.Image}}')
      tag="previous-tag"
      if [ "${FAKE_PREVIOUS_STATE:-valid}" = "mismatch" ] && [ "$service" = "agent-service" ]; then
        tag="other-tag"
      fi
      if [ "${FAKE_PREVIOUS_STATE:-valid}" = "invalid_repository" ] && [ "$service" = "web" ]; then
        printf 'unexpected-web:%s\n' "$tag"
      else
        printf 'inkforge-%s:%s\n' "$service" "$tag"
      fi
      ;;
    *) exit 2 ;;
  esac
  exit 0
fi

if [ "${1:-}" = "image" ] && [ "${2:-}" = "inspect" ]; then
  inspect_format=""
  image=""
  shift 2
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --format=*) inspect_format="${1#--format=}"; shift ;;
      --format) inspect_format="${2:-}"; shift 2 ;;
      *) image="$1"; shift ;;
    esac
  done
  if [ "${FAKE_PREVIOUS_STATE:-valid}" = "missing_image" ]; then
    case "$image" in
      sha256:previous-core-api-id|inkforge-core-api:previous-tag) exit 1 ;;
    esac
  fi
  case "$inspect_format" in
    *cn.inkforge.core.runtime*)
      case "$image" in
        inkforge-core-api:${FAKE_NEW_TAG:-new-tag})
          printf '%s\n' "${FAKE_NEW_CORE_RUNTIME-java}"
          ;;
        sha256:previous-core-api-id|inkforge-core-api:previous-tag)
          printf '%s\n' "${FAKE_PREVIOUS_CORE_RUNTIME-}"
          ;;
        *)
          printf '%s\n' "${FAKE_OTHER_CORE_RUNTIME-}"
          ;;
      esac
      ;;
    '{{.Id}}')
      case "$image" in
        sha256:previous-*-id)
          printf '%s\n' "$image"
          ;;
        inkforge-web:rollback-*)
          if [ "${FAKE_PREVIOUS_STATE:-valid}" = "snapshot_existing_conflict" ]; then
            printf '%s\n' 'sha256:older-web-id'
            exit 0
          fi
          [ -f "$FAKE_SNAPSHOT_STATE_DIR/web" ] || exit 1
          printf '%s\n' 'sha256:previous-web-id'
          ;;
        inkforge-core-api:rollback-*)
          [ -f "$FAKE_SNAPSHOT_STATE_DIR/core-api" ] || exit 1
          if [ "${FAKE_PREVIOUS_STATE:-valid}" = "snapshot_verify_mismatch" ]; then
            printf '%s\n' 'sha256:unexpected-core-id'
          else
            printf '%s\n' 'sha256:previous-core-api-id'
          fi
          ;;
        inkforge-agent-service:rollback-*)
          [ -f "$FAKE_SNAPSHOT_STATE_DIR/agent-service" ] || exit 1
          printf '%s\n' 'sha256:previous-agent-service-id'
          ;;
        *) printf '%s\n' 'sha256:fixture-id' ;;
      esac
      ;;
  esac
  exit 0
fi

if [ "${1:-}" = "image" ] && [ "${2:-}" = "tag" ]; then
  if [ "${FAKE_PREVIOUS_STATE:-valid}" = "snapshot_tag_failure" ] \
    && [ "${3:-}" = "sha256:previous-core-api-id" ]; then
    exit 27
  fi
  case "${4:-}" in
    inkforge-web:rollback-*) : > "$FAKE_SNAPSHOT_STATE_DIR/web" ;;
    inkforge-core-api:rollback-*) : > "$FAKE_SNAPSHOT_STATE_DIR/core-api" ;;
    inkforge-agent-service:rollback-*) : > "$FAKE_SNAPSHOT_STATE_DIR/agent-service" ;;
  esac
  exit 0
fi

if [ "${1:-}" = "exec" ]; then
  if [ "${2:-}" = "container-core-api" ]; then
    case " $* " in
      *"DURABLE_AGENT_EXECUTION_ROUTE_MODE"*)
        [ "${FAKE_RUNNING_CORE_ROUTE_MODE:-off}" = "off" ]
        exit $?
        ;;
    esac
  fi
  case " $* " in
    *" /usr/local/bin/inkforge-schema-guard "*) exit "${FAKE_SCHEMA_VERIFY_STATUS:-0}" ;;
  esac
fi

if [ "${1:-}" = "run" ]; then
  case " $* " in
    *"source=inkforge_uploads,target=/data/uploads"*) exit "${FAKE_UPLOAD_INIT_STATUS:-0}" ;;
    *"source=inkforge_agent_logs,target=/data/agent-logs"*) exit "${FAKE_AGENT_LOG_INIT_STATUS:-0}" ;;
    *"source=inkforge_execution_redis_data,target=/data"*) exit "${FAKE_EXECUTION_REDIS_INIT_STATUS:-0}" ;;
  esac
fi

exit 0
