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
    *" exec -T core-api python -c "*) exit "${FAKE_SCHEMA_VERIFY_STATUS:-0}" ;;
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
  container=""
  for argument in "$@"; do container="$argument"; done
  service="${container#container-}"
  tag="previous-tag"
  if [ "${FAKE_PREVIOUS_STATE:-valid}" = "mismatch" ] && [ "$service" = "agent-service" ]; then
    tag="other-tag"
  fi
  printf 'inkforge-%s:%s\n' "$service" "$tag"
  exit 0
fi

if [ "${1:-}" = "image" ] && [ "${2:-}" = "inspect" ]; then
  image="${3:-}"
  if [ "${FAKE_PREVIOUS_STATE:-valid}" = "missing_image" ]; then
    case "$image" in
      inkforge-core-api:previous-tag) exit 1 ;;
    esac
  fi
  exit 0
fi

exit 0
