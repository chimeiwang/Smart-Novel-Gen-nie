#!/bin/sh
set -eu

[ "${ALLOW_RECOVERY_DRILL:-no}" = yes ] || { echo "必须设置 ALLOW_RECOVERY_DRILL=yes" >&2; exit 1; }
# V2 恢复使用独立 Java Core、Agent 和持久 Redis 测试栈；不再删除生产 V1 队列键。
[ -z "${TASK_ID:-}" ] || { echo "V2 隔离演练自行创建具名测试 Run，不接受生产 TASK_ID" >&2; exit 1; }
exec uv run python -m tests.durable_agent_v2_e2e.run_e2e --phase minimum "$@"
