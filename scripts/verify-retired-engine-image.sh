#!/bin/sh
set -eu
[ "$#" -eq 2 ] || { echo "必须提供组件和镜像" >&2; exit 2; }
component="$1"
image="$2"
case "$image" in
  inkforge-core-api:*|inkforge-agent-service:*|sha256:*) ;;
  *) echo "镜像不属于受控发布" >&2; exit 2 ;;
esac
docker image inspect "$image" >/dev/null
case "$component" in
  core)
    docker run --rm --network none --read-only --cap-drop ALL \
      --entrypoint java "$image" \
      -Dloader.main=cn.inkforge.core.platform.db.RetiredEngineProbe \
      -cp /app/inkforge-core-api.jar org.springframework.boot.loader.launch.PropertiesLauncher
    ;;
  agent)
    docker run --rm --network none --read-only --cap-drop ALL \
      --entrypoint python "$image" -c \
      'import importlib.util; assert importlib.util.find_spec("inkforge_agents.execution") is None; from inkforge_agents.app import create_app; from inkforge_agents.jobs.video_episode import EpisodeJobHandler; print("engineRetired=true,ordinaryQueue=true")'
    ;;
  *) echo "组件必须是 core 或 agent" >&2; exit 2 ;;
esac
