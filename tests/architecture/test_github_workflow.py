from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "durable-agent-v2-release.yml"
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy-production.sh"
IMAGE_UPLOAD_SCRIPT = ROOT / "scripts" / "upload-docker-images.sh"
SOURCE_UPLOAD_SCRIPT = ROOT / "scripts" / "upload-deploy-source.sh"
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


def test_ci_has_no_production_delivery_and_release_is_fixed_before_image_upload() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    release = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "docker build -t inkforge:latest ." not in source
    for forbidden in (
        "scripts/upload-docker-images.sh",
        "scripts/upload-deploy-source.sh",
        "scripts/deploy-production.sh",
        "Deploy over SSH",
        "environment: production",
        "secrets.",
    ):
        assert forbidden not in source
    for obsolete in (
        "POSTGRES_DATA_VOLUME",
        "POSTGRES_USER: inkforge",
        "POSTGRES_PASSWORD: ci-placeholder",
        "POSTGRES_DB: inkforge",
    ):
        assert obsolete not in source
    assert "scripts/upload-docker-images.sh" not in release
    assert "上传目标镜像（release transaction 已建锁）" not in release
    assert "streaming-broker-and-sealed-genesis-not-implemented" in release
    assert "environment:\n      name: production" in release
    assert "fetch-depth: 0" in release
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
    assert 'docker save "${images_to_upload[@]}"' not in source
    assert 'docker save "$1"' in source
    assert 'if [ "${#images_to_upload[@]}" -eq 0 ]' in source
    assert "docker load" in source


def test_legacy_image_upload_helper_has_a_total_timeout_but_release_cannot_call_it() -> None:
    source = IMAGE_UPLOAD_SCRIPT.read_text(encoding="utf-8")
    release = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert 'IMAGE_ARCHIVE_TIMEOUT_SECONDS="${IMAGE_ARCHIVE_TIMEOUT_SECONDS:-600}"' in source
    assert 'IMAGE_UPLOAD_TIMEOUT_SECONDS="${IMAGE_UPLOAD_TIMEOUT_SECONDS:-1200}"' in source
    assert (
        'validate_timeout IMAGE_UPLOAD_TIMEOUT_SECONDS '
        '"$IMAGE_UPLOAD_TIMEOUT_SECONDS" 3600'
    ) in source
    assert 'timeout --kill-after=30s "$IMAGE_UPLOAD_TIMEOUT_SECONDS"' in source
    assert "scripts/upload-docker-images.sh" not in release
    assert "timeout-minutes: 20" in release


def test_release_downloads_semantic_trust_artifacts_and_has_no_remote_execution() -> None:
    source = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    production = source.split("  production:", 1)[1]
    for artifact in (
        "durable-agent-v2-ssh-release-attestation",
        "durable-agent-v2-ssh-release-evidence",
        "durable-agent-v2-release-bootstrap-attestation",
    ):
        assert artifact in production
    assert production.index("durable_agent_release_trust.py verify") < production.index(
        "streaming-broker-and-sealed-genesis-not-implemented"
    )
    for forbidden in (
        "scripts/upload-deploy-source.sh",
        "DEPLOY_BUNDLE_PATH=%q",
        "remote_command",
        "ssh -",
        "scp ",
    ):
        assert forbidden not in production


def test_release_consumes_only_v2_development_evidence_with_both_run_attempts() -> None:
    source = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    development = source.split("  development_evidence:", 1)[1].split(
        "  rollback_manifest:", 1
    )[0]

    for artifact in (
        "durable-agent-v2-candidate-evidence",
        "durable-agent-v2-development-images",
        "durable-agent-v2-migration-qualification",
        "durable-agent-v2-target-images",
    ):
        assert artifact in development
    for binding in (
        "inputs.development_candidate_run_attempt",
        "inputs.development_migration_qualification_run_attempt",
        '--candidate-run-attempt "$CANDIDATE_RUN_ATTEMPT"',
        '--qualification-run-attempt "$QUALIFICATION_RUN_ATTEMPT"',
        '--qualification-source-commit "$QUALIFICATION_SOURCE_COMMIT"',
        '--source-tree-manifest "$source_tree_manifest"',
    ):
        assert binding in source
    assert "durable_agent_v2_development_consumer.py" in development
    assert "development-evidence.json" not in source
    assert "durable-agent-v2-development-reports" not in source
    assert "verify-production" not in source


def test_release_precheckout_guard_canonicalizes_every_dispatch_run_number() -> None:
    workflow = yaml.safe_load(RELEASE_WORKFLOW.read_text(encoding="utf-8"))
    guard = workflow["jobs"]["source"]["steps"][0]["run"]

    assert '""|0*|*[!0-9]*) exit 1' in guard
    producer_numbers = (
        "SSH_ATTESTATION_RUN_ID",
        "SSH_ATTESTATION_RUN_ATTEMPT",
        "BOOTSTRAP_ATTESTATION_RUN_ID",
        "BOOTSTRAP_ATTESTATION_RUN_ATTEMPT",
    )
    for variable in producer_numbers:
        assert f'"${variable}"' in guard
    assert 'require_positive_decimal "$producer_number"' in guard
    for variable in (
        "DEVELOPMENT_CANDIDATE_RUN_ID",
        "DEVELOPMENT_QUALIFICATION_RUN_ID",
        "RELEASE_MANIFEST_RUN_ID",
        "FAILED_LOCK_OWNER_RUN_ID",
        "FAILED_LOCK_OWNER_RUN_ATTEMPT",
    ):
        assert f'require_positive_decimal "${variable}"' in guard


def _target_image_member_guard() -> str:
    workflow = yaml.safe_load(RELEASE_WORKFLOW.read_text(encoding="utf-8"))
    development = workflow["jobs"]["development_evidence"]
    semantic = next(
        step
        for step in development["steps"]
        if step.get("name") == "复验实际镜像与 v2 qualification/candidate 全部语义"
    )
    marker = 'python3 - "$images_dir" <<\'PY\'\n'
    assert semantic["run"].index(marker) < semantic["run"].index(
        'sha256sum --strict --check SHA256SUMS'
    )
    assert semantic["run"].index(marker) < semantic["run"].index("docker load")
    semantic_index = development["steps"].index(semantic)
    verified_upload_index = next(
        index
        for index, step in enumerate(development["steps"])
        if step.get("name") == "转存本次 release workflow 的已复验 v2 开发输入"
    )
    assert semantic_index < verified_upload_index
    return semantic["run"].split(marker, 1)[1].split("\nPY\n", 1)[0]


def _run_target_image_member_guard(directory: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - 只执行当前解释器与 Workflow 内固定检查
        [sys.executable, "-", str(directory)],
        input=_target_image_member_guard(),
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.parametrize("attack", ["directory", "symlink", "fifo", "hardlink"])
def test_target_image_artifact_rejects_non_whitelisted_or_non_regular_members(
    tmp_path: Path,
    attack: str,
) -> None:
    images = tmp_path / "images"
    images.mkdir()
    for name in ("SHA256SUMS", "target-images.snapshot", "target-images.tar.gz"):
        (images / name).write_text(name, encoding="utf-8")
    assert _run_target_image_member_guard(images).returncode == 0

    if attack == "directory":
        (images / "extra").mkdir()
    elif attack == "symlink":
        (images / "target-images.tar.gz").unlink()
        (images / "target-images.tar.gz").symlink_to(images / "target-images.snapshot")
    elif attack == "fifo":
        (images / "target-images.tar.gz").unlink()
        os.mkfifo(images / "target-images.tar.gz")
    else:
        (images / "target-images.tar.gz").unlink()
        os.link(images / "target-images.snapshot", images / "target-images.tar.gz")

    assert _run_target_image_member_guard(images).returncode != 0


def test_source_bundle_upload_is_sha_bound_atomic_and_pinned() -> None:
    source = SOURCE_UPLOAD_SCRIPT.read_text(encoding="utf-8")

    for contract in (
        'DEPLOY_SHA="${DEPLOY_SHA:?必须设置部署提交}"',
        'git -C "$DEPLOY_SOURCE_ROOT" rev-parse HEAD',
        'git -C "$DEPLOY_SOURCE_ROOT" bundle create "$local_bundle" HEAD --',
        'git bundle verify "$local_bundle"',
        'chmod 600 "$local_bundle"',
        'remote_bundle="/tmp/inkforge-deploy-${DEPLOY_SHA}.bundle"',
        'remote_partial="${remote_bundle}.partial"',
        "StrictHostKeyChecking=yes",
        "UserKnownHostsFile=$SSH_KNOWN_HOSTS_FILE",
        "BatchMode=yes",
        '"${remote}:${remote_partial}"',
        "mv -f -- '$remote_partial' '$remote_bundle'",
    ):
        assert contract in source

    assert "StrictHostKeyChecking=no" not in source
    assert "ssh-keyscan" not in source
    assert SOURCE_UPLOAD_SCRIPT.stat().st_mode & 0o111


def test_image_upload_reuses_services_with_unchanged_build_inputs() -> None:
    source = IMAGE_UPLOAD_SCRIPT.read_text(encoding="utf-8")

    assert 'git diff --quiet "$base_sha" "$DEPLOY_SHA" --' in source
    for build_input in (
        "apps/web",
        "packages/api-client",
        "apps/core-api",
        "apps/core-api-java",
        "apps/agent-service",
        "packages/service-auth",
        "packages/service-auth-java",
        "packages/service-contracts",
        "packages/service-contracts-java",
        "contracts/core",
        ".mvn",
        "mvnw",
        "pom.xml",
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


def test_java_failures_are_published_to_the_workflow_summary() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "maven-verify.log" in source
    assert "## Java 迁移工作区验证失败" in source
    assert "grep -E -A 8 '<<< (FAILURE|ERROR)!' maven-verify.log" in source
    assert 'annotation="$(tail -n 20 maven-verify.log)"' in source
    assert "::error title=Java 迁移工作区验证失败::" in source


def test_ci_does_not_inject_optional_redis_dependency() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "\n      REDIS_URL:" not in source


def test_release_fixed_gate_never_attempts_remote_failure_compensation() -> None:
    source = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    production = source.split("  production:", 1)[1]
    assert "sealed genesis 与真正流式双角色 broker 未接线" in production
    assert "mark-transaction-failed" not in production
    assert "continue-on-error: true" not in production
    assert production.rstrip().endswith("exit 1")


def test_production_compares_pinned_host_identity_without_exposing_private_key() -> None:
    source = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    workflow_header = source.split("\njobs:", maxsplit=1)[0]

    assert "StrictHostKeyChecking=no" not in source
    assert "DURABLE_AGENT_V2_RELEASE_SSH_KNOWN_HOSTS" in source
    assert "secrets.DURABLE_AGENT_V2_RELEASE_SSH_PRIVATE_KEY" not in source
    assert "secrets.DURABLE_AGENT_V2_RELEASE_EXECUTION_SSH_PRIVATE_KEY" not in source
    assert "secrets.DURABLE_AGENT_V2_RELEASE_UPLOAD_SSH_PRIVATE_KEY" not in source
    assert "StrictHostKeyChecking=yes" not in source
    assert "cmp \"$actual_known_hosts\"" not in source
    assert '--expected-known-hosts-file "$trust_root/production-known-hosts"' in source
    assert "\nconcurrency:" not in workflow_header
    assert 'group: production\n      cancel-in-progress: false' in source


def test_remote_deploy_requires_server_configuration_and_never_builds() -> None:
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    for contract in (
        'APP_DIR="${APP_DIR:-/srv/smart-novel-gen}"',
        'DEPLOY_SHA="${DEPLOY_SHA:?必须设置部署提交}"',
        'DEPLOY_BUNDLE_PATH="${DEPLOY_BUNDLE_PATH:?必须设置部署源码 bundle}"',
        'control_dir="${DURABLE_AGENT_CONTROL_BUNDLE_DIR:?必须设置不可变 control bundle 目录}"',
        'safe_git bundle verify "$DEPLOY_BUNDLE_PATH"',
        'safe_git fetch "$DEPLOY_BUNDLE_PATH" HEAD',
        'safe_git reset --hard "$DEPLOY_SHA"',
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
    assert "服务器不再保留 fetch 兼容旁路" in source
    assert "fetch --depth=1 origin" not in source
    assert "host\\.docker\\.internal" in source
    assert 'stat -c %u "infra/secrets/$private_key"' in source
    assert 'stat -c %a "infra/secrets/$private_key"' in source
    assert '"$owner" = "10001"' in source
    assert '"$mode" = "600"' in source

    assert "up --build" not in source


def test_remote_deploy_prefers_verified_bundle_and_always_cleans_it() -> None:
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    for contract in (
        'DEPLOY_BUNDLE_PATH="${DEPLOY_BUNDLE_PATH:?必须设置部署源码 bundle}"',
        'expected_bundle_path="/tmp/inkforge-deploy-${DEPLOY_SHA}.bundle"',
        'safe_git bundle verify "$DEPLOY_BUNDLE_PATH"',
        'safe_git fetch "$DEPLOY_BUNDLE_PATH" HEAD',
        'bundle_sha="$(safe_git rev-parse FETCH_HEAD)"',
        'safe_git update-ref "refs/remotes/origin/$BRANCH" "$DEPLOY_SHA"',
        'rm -f -- "$DEPLOY_BUNDLE_PATH"',
    ):
        assert contract in source
    assert "fetch --depth=1 origin" not in source


def test_remote_deploy_allows_only_its_app_directory_for_git_operations() -> None:
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert 'git -c safe.directory="$APP_DIR" "$@"' in source
    assert 'safe_git reset --hard "$DEPLOY_SHA"' in source
