from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy-production.sh"
IMAGE_UPLOAD_SCRIPT = ROOT / "scripts" / "upload-docker-images.sh"
API_GENERATOR = ROOT / "scripts" / "generate_api_client.mjs"


def test_ci_uses_current_node_python_and_openapi_gates() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    for forbidden in ("db:generate", "prisma", "docker-compose.yml"):
        assert forbidden not in source

    for action in (
        "actions/checkout@v7",
        "actions/setup-node@v6",
        "actions/setup-python@v6",
        "astral-sh/setup-uv@v7",
    ):
        assert action in source

    for command in (
        "uv sync --frozen --all-packages --group dev",
        "npm run api:check",
        "npm run test:web",
        "npm run typecheck",
        "npm run lint",
        "npm run build",
        "uv run pytest",
        "uv run ruff check .",
        "uv run mypy apps/core-api/src apps/agent-service/src "
        "packages/service-contracts/src packages/service-auth/src",
    ):
        assert command in source


def test_deploy_builds_and_uploads_all_three_versioned_images() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "docker build -t inkforge:latest ." not in source
    assert (
        "docker compose --env-file .env.example -f infra/compose.yaml "
        "build web core-api agent-service"
    ) in source
    for obsolete in (
        "POSTGRES_DATA_VOLUME",
        "POSTGRES_USER: inkforge",
        "POSTGRES_PASSWORD: ci-placeholder",
        "POSTGRES_DB: inkforge",
    ):
        assert obsolete not in source
    assert "scripts/upload-docker-images.sh" in source
    assert "fetch-depth: 0" in source
    for image in (
        "inkforge-web:${INKFORGE_IMAGE_TAG}",
        "inkforge-core-api:${INKFORGE_IMAGE_TAG}",
        "inkforge-agent-service:${INKFORGE_IMAGE_TAG}",
    ):
        assert image in IMAGE_UPLOAD_SCRIPT.read_text(encoding="utf-8")


def test_image_upload_reuses_matching_server_images() -> None:
    source = IMAGE_UPLOAD_SCRIPT.read_text(encoding="utf-8")

    assert "docker image inspect --format='{{.Id}}'" in source
    assert 'docker image inspect "$image_id"' in source
    assert 'docker image tag "$image_id" "$image"' in source
    assert 'images_to_upload+=("$image")' in source
    assert 'docker save "${images_to_upload[@]}"' in source
    assert 'if [ "${#images_to_upload[@]}" -eq 0 ]' in source
    assert "docker load" in source


def test_image_upload_reuses_services_with_unchanged_build_inputs() -> None:
    source = IMAGE_UPLOAD_SCRIPT.read_text(encoding="utf-8")

    assert 'git diff --quiet "$base_sha" "$DEPLOY_SHA" --' in source
    for build_input in (
        "apps/web",
        "packages/api-client",
        "apps/core-api",
        "apps/agent-service",
        "packages/service-auth",
        "packages/service-contracts",
        "package-lock.json",
        "uv.lock",
    ):
        assert build_input in source
    assert "读取服务器当前运行镜像" in source
    assert "复用构建输入未变化的服务器镜像" in source


def test_api_generator_selects_uv_command_for_each_platform() -> None:
    source = API_GENERATOR.read_text(encoding="utf-8")

    assert 'process.platform === "win32"' in source
    assert 'execFileSync(uvCommand, uvArgs' in source


def test_python_failures_are_published_to_the_workflow_summary() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "pytest.log" in source
    assert "GITHUB_STEP_SUMMARY" in source
    assert "::error title=Python 测试失败::" in source


def test_ci_does_not_inject_optional_redis_dependency() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "\n      REDIS_URL:" not in source


def test_deploy_failures_are_published_to_the_workflow_summary() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "deploy.log" in source
    assert "## 生产部署失败" in source
    assert "::error title=生产部署失败::" in source


def test_production_deploy_uses_pinned_ssh_host_identity_and_non_cancelled_queue() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "StrictHostKeyChecking=no" not in source
    assert "DEPLOY_SSH_KNOWN_HOSTS" in source
    assert "SSH_KNOWN_HOSTS_FILE" in source
    assert "StrictHostKeyChecking=yes" in source
    assert "UserKnownHostsFile=" in source
    assert 'group: production\n      cancel-in-progress: false' in source


def test_remote_deploy_requires_server_configuration_and_never_builds() -> None:
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    for contract in (
        'APP_DIR="${APP_DIR:-/srv/smart-novel-gen}"',
        'DEPLOY_SHA="${DEPLOY_SHA:?必须设置部署提交}"',
        "git -c http.version=HTTP/1.1 fetch",
        'git reset --hard "$DEPLOY_SHA"',
        "infra/compose.yaml",
        ".env",
        "core-to-agent-private.pem",
        "core-to-agent-jwks.json",
        "agent-to-core-private.pem",
        "agent-to-core-jwks.json",
        "--no-build",
        "--wait",
    ):
        assert contract in source

    assert 'grep -q \'host.docker.internal\' "$compose_file"' in source
    assert '[ -r .env ]' in source
    assert '部署用户无法读取 .env' in source
    assert '[ -x infra/secrets ]' in source
    assert "部署用户无法检查服务密钥目录" in source
    assert 'max_fetch_attempts="3"' in source
    assert '[ "$fetch_attempt" -lt "$max_fetch_attempts" ]' in source
    assert "Git 获取连续失败" in source
    assert "host\\.docker\\.internal" in source
    assert 'stat -c %u "infra/secrets/$private_key"' in source
    assert 'stat -c %a "infra/secrets/$private_key"' in source
    assert '"$owner" = "10001"' in source
    assert '"$mode" = "600"' in source

    assert "up --build" not in source
