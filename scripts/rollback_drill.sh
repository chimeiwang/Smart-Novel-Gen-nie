#!/bin/sh
set -eu

[ "${ALLOW_ROLLBACK_DRILL:-no}" = "yes" ] || { echo "必须设置 ALLOW_ROLLBACK_DRILL=yes" >&2; exit 1; }
: "${ROLLBACK_IMAGE_TAG:?必须设置已验证的回滚镜像标签}"

export INKFORGE_IMAGE_TAG="$ROLLBACK_IMAGE_TAG"
docker compose --env-file .env -f infra/compose.yaml up -d --no-build --wait
docker compose --env-file .env -f infra/compose.yaml ps
echo "已切换到回滚镜像标签：$ROLLBACK_IMAGE_TAG"
