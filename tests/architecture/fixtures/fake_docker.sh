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
