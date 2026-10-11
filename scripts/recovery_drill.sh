#!/bin/sh
set -eu

[ "${ALLOW_RECOVERY_DRILL:-no}" = yes ] || { echo "必须设置 ALLOW_RECOVERY_DRILL=yes" >&2; exit 1; }
# 此入口只验证 V1 快照、队列租约、取消和单集阶段恢复，不连接生产或修改业务数据。
[ -z "${TASK_ID:-}" ] || { echo "隔离恢复回归不接受生产 TASK_ID" >&2; exit 1; }
exec uv run pytest apps/agent-service/tests/graph/test_snapshots.py \
  apps/agent-service/tests/jobs/test_writing.py \
  apps/agent-service/tests/jobs/test_video_episode.py \
  apps/agent-service/tests/queue/test_consumer.py "$@"
