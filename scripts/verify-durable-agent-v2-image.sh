#!/bin/sh
set -eu

component="${1:-}"
image="${2:-}"
expected_manifest_fingerprint="${3:-}"
[ "$#" -le 3 ] || {
  echo "V2-aware 镜像检查参数过多" >&2
  exit 2
}
case "$component" in
  core|agent) ;;
  *) echo "V2-aware 镜像检查组件必须是 core 或 agent" >&2; exit 2 ;;
esac
case "$image" in
  inkforge-core-api:*|inkforge-agent-service:*|sha256:*) ;;
  *) echo "V2-aware 镜像检查目标不属于 InkForge 受控仓库" >&2; exit 2 ;;
esac
command -v docker >/dev/null 2>&1 || { echo "缺少 docker" >&2; exit 1; }
docker image inspect "$image" >/dev/null 2>&1 || { echo "待检查镜像不存在" >&2; exit 1; }

case "$component" in
  core)
    [ -z "$expected_manifest_fingerprint" ] || {
      echo "Core 镜像检查不接受 execution manifest 指纹" >&2
      exit 2
    }
    docker run --rm --network none --read-only --cap-drop ALL \
      --entrypoint /bin/sh "$image" -ec \
      "grep -aFq 'pre-durable-agent-v2/schema-contract.json' /app/inkforge-core-api.jar && \
       grep -aFq 'post-durable-agent-v2/schema-contract.json' /app/inkforge-core-api.jar && \
       grep -aFq 'DurableAgentSchemaGate.class' /app/inkforge-core-api.jar && \
       grep -aFq 'WorkflowsController.class' /app/inkforge-core-api.jar && \
       grep -aFq 'JooqWorkflowCallbackRepository.class' /app/inkforge-core-api.jar" \
      >/dev/null || {
        echo "Core 镜像不是耐久 Agent V2-aware 镜像" >&2
        exit 1
      }
    ;;
  agent)
    if [ -n "$expected_manifest_fingerprint" ]; then
      case "$expected_manifest_fingerprint" in
        *[!0-9a-f]*)
          echo "预期 execution manifest 指纹必须是 64 位小写十六进制" >&2
          exit 2
          ;;
      esac
      [ "${#expected_manifest_fingerprint}" -eq 64 ] || {
        echo "预期 execution manifest 指纹必须是 64 位小写十六进制" >&2
        exit 2
      }
    fi
    # Registry loader 会在镜像内部校验 manifest、每个版本化资产的原始 SHA、
    # JSON Schema 与跨 Registry 引用。探针不联网、不挂卷、不注入运行环境。
    if actual_manifest_fingerprint="$(
      docker run --rm --network none --read-only --cap-drop ALL \
        --entrypoint python "$image" -c \
        'from inkforge_agents.execution.registry import load_execution_registry; print(load_execution_registry(environment="production").manifest_fingerprint)'
    )"; then
      :
    else
      echo "Agent 镜像无法离线验证耐久 Agent V2 execution manifest" >&2
      exit 1
    fi
    case "$actual_manifest_fingerprint" in
      *[!0-9a-f]*)
        echo "Agent 镜像输出了无效的 execution manifest 指纹" >&2
        exit 1
        ;;
    esac
    [ "${#actual_manifest_fingerprint}" -eq 64 ] || {
      echo "Agent 镜像输出了无效的 execution manifest 指纹" >&2
      exit 1
    }
    if [ -n "$expected_manifest_fingerprint" ] \
      && [ "$actual_manifest_fingerprint" != "$expected_manifest_fingerprint" ]; then
      echo "Agent 镜像 execution manifest 指纹与发布预期不一致" >&2
      exit 1
    fi
    ;;
esac

if [ "$component" = "agent" ]; then
  printf 'v2-aware-image-ok:agent:%s\n' "$actual_manifest_fingerprint"
else
  printf 'v2-aware-image-ok:core\n'
fi
