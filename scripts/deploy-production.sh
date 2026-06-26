#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/srv/smart-novel-gen}"
REPO_URL="${REPO_URL:-https://github.com/chimeiwang/Smart-Novel-Gen-nie.git}"
BRANCH="${BRANCH:-main}"
IMAGE_NAME="${IMAGE_NAME:-inkforge:latest}"
SKIP_DOCKER_BUILD="${SKIP_DOCKER_BUILD:-false}"

if ! command -v git >/dev/null 2>&1; then
  echo "git is required on the deployment server" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required on the deployment server" >&2
  exit 1
fi

mkdir -p "$APP_DIR"
cd "$APP_DIR"

if [ ! -d .git ]; then
  echo "Initializing repository in $APP_DIR"
  git init -b "$BRANCH"
  git remote add origin "$REPO_URL"
fi

echo "Fetching $BRANCH from $REPO_URL"
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"

if [ ! -f .env.production ]; then
  echo ".env.production is missing in $APP_DIR" >&2
  exit 1
fi

if [ "$SKIP_DOCKER_BUILD" = "true" ]; then
  echo "Using prebuilt Docker image $IMAGE_NAME"
else
  echo "Building Docker image $IMAGE_NAME"
  docker build -t "$IMAGE_NAME" .
fi

echo "Starting Docker Compose services"
docker compose up -d

echo "Pruning unused Docker images"
docker image prune -f
