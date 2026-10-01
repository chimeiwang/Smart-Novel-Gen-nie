from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy-production.sh"
IMAGE_UPLOAD_SCRIPT = ROOT / "scripts" / "upload-docker-images.sh"
SOURCE_UPLOAD_SCRIPT = ROOT / "scripts" / "upload-deploy-source.sh"
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "deploy-release.yml"
RETRY_WORKFLOW = ROOT / ".github" / "workflows" / "retry-production.yml"
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
        "uv run mypy apps/agent-service/src "
        "packages/service-contracts/src packages/service-auth/src",
    ):
        assert command in source


def test_main_push_only_publishes_three_versioned_ghcr_images_after_ci() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    jobs = yaml.safe_load(source)["jobs"]
    publish = jobs["publish-images"]

    assert "docker build -t inkforge:latest ." not in source
    for obsolete in (
        "POSTGRES_DATA_VOLUME",
        "POSTGRES_USER: inkforge",
        "POSTGRES_PASSWORD: ci-placeholder",
        "POSTGRES_DB: inkforge",
    ):
        assert obsolete not in source
    assert "scripts/upload-docker-images.sh" not in source
    assert publish["needs"] == "ci"
    assert publish["if"] == (
        "github.event_name == 'push' && github.ref == 'refs/heads/main' "
        "&& github.repository == 'chimeiwang/Smart-Novel-Gen-nie'"
    )
    assert publish["permissions"] == {"contents": "read", "packages": "write"}
    assert jobs["ci"].get("permissions") is None
    assert yaml.safe_load(source)["permissions"] == {"contents": "read"}
    assert publish["outputs"]["artifact-id"] == "${{ steps.release-artifact.outputs.artifact-id }}"
    steps = publish["steps"]
    assert any(step.get("uses") == "docker/setup-buildx-action@v4" for step in steps)
    assert any(step.get("uses") == "docker/login-action@v4" for step in steps)
    builds = [step for step in steps if step.get("uses") == "docker/build-push-action@v7"]
    assert len(builds) == 3
    for step, service in zip(builds, ("web", "core-api", "agent-service"), strict=True):
        config = step["with"]
        assert config["context"] == "."
        assert config["file"] == f"infra/docker/{service}.Dockerfile"
        assert config["platforms"] == "linux/amd64"
        assert config["push"] is True
        assert config["load"] is True
        assert config["provenance"] is False
        assert config["tags"] == (
            f"ghcr.io/chimeiwang/smart-novel-gen-nie/{service}:${{{{ github.sha }}}}"
        )
        assert "org.opencontainers.image.revision=${{ github.sha }}" in config["labels"]
        assert config["cache-from"] == f"type=gha,scope={service}"
        assert config["cache-to"] == f"type=gha,scope={service},mode=max"
    create = next(step for step in steps if step.get("name") == "生成发布清单")
    assert "scripts/release_manifest.py create" in create["run"]
    for digest in ("WEB_DIGEST", "CORE_DIGEST", "AGENT_DIGEST"):
        assert digest in create["env"]
    artifact = next(step for step in steps if step.get("id") == "release-artifact")
    assert artifact["uses"] == "actions/upload-artifact@v7"
    assert artifact["with"]["retention-days"] == 30
    assert artifact["with"]["overwrite"] is False


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


def test_production_pull_has_bounded_step_and_uses_verified_manifest() -> None:
    source = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    job = yaml.safe_load(source)["jobs"]["deploy"]
    steps = job["steps"]
    pull = next(step for step in steps if step.get("name") == "拉取已验证镜像")
    assert pull["timeout-minutes"] == 55
    assert "scripts/pull-release-images.py" in pull["run"]
    assert pull["env"]["GITHUB_TOKEN"] == "${{ github.token }}"  # noqa: S105 - 工作流表达式
    assert "--manifest" in pull["run"]
    assert "--source-run-id" in pull["run"]
    assert steps.index(pull) < next(
        index for index, step in enumerate(steps) if step.get("name") == "通过 SSH 部署"
    )


def test_deploy_uploads_verified_source_bundle_before_remote_execution() -> None:
    source = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    upload_name = "      - name: 上传部署源码 bundle"
    deploy_name = "      - name: 通过 SSH 部署"
    assert upload_name in source
    assert source.index(upload_name) < source.index(deploy_name)
    assert "scripts/upload-deploy-source.sh" in source
    assert "DEPLOY_BUNDLE_PATH='/tmp/inkforge-deploy-${SOURCE_SHA}.bundle'" in source


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
    if os.name != "nt":
        assert SOURCE_UPLOAD_SCRIPT.stat().st_mode & 0o111


def test_image_upload_reuses_services_with_unchanged_build_inputs() -> None:
    source = IMAGE_UPLOAD_SCRIPT.read_text(encoding="utf-8")

    assert 'git diff --quiet "$base_sha" "$DEPLOY_SHA" --' in source
    for build_input in (
        "apps/web",
        "packages/api-client",
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


def test_api_generator_consumes_canonical_contract_without_core_process() -> None:
    source = API_GENERATOR.read_text(encoding="utf-8")

    assert "public-openapi.json" in source
    assert "execFileSync" not in source


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


def test_deploy_failures_are_published_to_the_workflow_summary() -> None:
    source = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    assert "deploy.log" in source
    assert "## 生产部署失败" in source
    assert "::error title=生产部署失败::" in source


def test_production_deploy_uses_pinned_ssh_host_identity_and_non_cancelled_queue() -> None:
    source = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    main = WORKFLOW.read_text(encoding="utf-8")
    workflow_header = main.split("\njobs:", maxsplit=1)[0]

    assert "StrictHostKeyChecking=no" not in source
    assert "DEPLOY_SSH_KNOWN_HOSTS" in source
    assert "SSH_KNOWN_HOSTS_FILE" in source
    assert "StrictHostKeyChecking=yes" in source
    assert "UserKnownHostsFile=" in source
    assert "\nconcurrency:" not in workflow_header
    assert (
        "  ci:\n"
        "    concurrency:\n"
        "      group: ci-${{ github.workflow }}-${{ github.ref }}\n"
        "      cancel-in-progress: true"
    ) in main
    assert 'group: production\n      cancel-in-progress: false' in source


def test_retry_resolves_a_trusted_run_and_reuses_the_same_deployment() -> None:
    source = RETRY_WORKFLOW.read_text(encoding="utf-8")
    jobs = yaml.safe_load(source)["jobs"]
    assert "workflow_dispatch:" in source
    assert source.count("      run_id:") == 1
    assert "source_sha:" not in source.split("permissions:", maxsplit=1)[0]
    assert "digest:" not in source.split("permissions:", maxsplit=1)[0]
    resolver = jobs["resolve-release"]
    assert resolver["if"] == (
        "github.repository == 'chimeiwang/Smart-Novel-Gen-nie' "
        "&& github.ref == 'refs/heads/main'"
    )
    assert resolver["permissions"] == {"actions": "read", "contents": "read"}
    assert "scripts/resolve-release-retry.py" in resolver["steps"][-1]["run"]
    assert "--run-id \"$SOURCE_RUN_ID\"" in resolver["steps"][-1]["run"]
    deploy = jobs["deploy"]
    assert deploy["needs"] == "resolve-release"
    assert deploy["uses"] == "./.github/workflows/deploy-release.yml"
    assert deploy["permissions"] == {
        "actions": "read",
        "contents": "read",
        "packages": "read",
    }
    assert deploy["with"]["artifact_id"] == "${{ needs.resolve-release.outputs.artifact-id }}"


def test_reusable_deployment_keeps_manifest_source_and_environment_gates() -> None:
    main = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    deploy = main["deploy"]
    assert deploy["needs"] == "publish-images"
    assert deploy["if"] == (
        "github.event_name == 'push' && github.ref == 'refs/heads/main' "
        "&& github.repository == 'chimeiwang/Smart-Novel-Gen-nie'"
    )
    assert deploy["uses"] == "./.github/workflows/deploy-release.yml"
    assert deploy["permissions"] == {
        "actions": "read",
        "contents": "read",
        "packages": "read",
    }
    reusable = yaml.safe_load(DEPLOY_WORKFLOW.read_text(encoding="utf-8"))["jobs"]["deploy"]
    assert reusable["if"] == (
        "github.repository == 'chimeiwang/Smart-Novel-Gen-nie' "
        "&& github.ref == 'refs/heads/main'"
    )
    assert reusable["environment"] == "production"
    steps = reusable["steps"]
    assert any(step.get("uses") == "actions/download-artifact@v8" for step in steps)
    download = next(step for step in steps if step.get("uses") == "actions/download-artifact@v8")
    assert download["with"]["artifact-ids"] == "${{ inputs.artifact_id }}"
    assert download["with"]["run-id"] == "${{ inputs.source_run_id }}"
    assert download["with"]["digest-mismatch"] == "error"
    assert any("scripts/release_manifest.py validate" in step.get("run", "") for step in steps)
    assert any("git rev-parse HEAD" in step.get("run", "") for step in steps)
    queue_gate = next(step for step in steps if step.get("name") == "在生产队列内复核发布来源")
    assert "scripts/resolve-release-retry.py" in queue_gate["run"]
    assert "--run-id \"$SOURCE_RUN_ID\"" in queue_gate["run"]
    assert "release-gate.json" in queue_gate["run"]
    for field in ("sourceSha", "sourceRunId", "artifactId"):
        assert field in queue_gate["run"]
    assert steps.index(queue_gate) < next(
        index for index, step in enumerate(steps) if step.get("name") == "下载发布清单"
    )
    checkout = next(step for step in steps if step.get("name") == "检出当前 main")
    assert checkout["with"]["ref"] == "main"


def test_remote_deploy_requires_server_configuration_and_never_builds() -> None:
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    for contract in (
        'APP_DIR="${APP_DIR:-/srv/smart-novel-gen}"',
        'DEPLOY_SHA="${DEPLOY_SHA:?必须设置部署提交}"',
        'safe_git -c http.version=HTTP/1.1 fetch',
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
    assert 'max_fetch_attempts="3"' in source
    assert '[ "$fetch_attempt" -lt "$max_fetch_attempts" ]' in source
    assert "Git 获取连续失败" in source
    assert "host\\.docker\\.internal" in source
    assert 'stat -c %u "infra/secrets/$private_key"' in source
    assert 'stat -c %a "infra/secrets/$private_key"' in source
    assert '"$owner" = "10001"' in source
    assert '"$mode" = "600"' in source

    assert "up --build" not in source


def test_remote_deploy_prefers_verified_bundle_and_always_cleans_it() -> None:
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    for contract in (
        'DEPLOY_BUNDLE_PATH="${DEPLOY_BUNDLE_PATH:-}"',
        'expected_bundle_path="/tmp/inkforge-deploy-${DEPLOY_SHA}.bundle"',
        'safe_git bundle verify "$DEPLOY_BUNDLE_PATH"',
        'safe_git fetch "$DEPLOY_BUNDLE_PATH" HEAD',
        'bundle_sha="$(safe_git rev-parse FETCH_HEAD)"',
        'safe_git update-ref "refs/remotes/origin/$BRANCH" "$DEPLOY_SHA"',
        'rm -f -- "$DEPLOY_BUNDLE_PATH"',
    ):
        assert contract in source

    bundle_fetch = source.index('safe_git fetch "$DEPLOY_BUNDLE_PATH" HEAD')
    origin_fetch = source.index("fetch --depth=1 origin")
    assert bundle_fetch < origin_fetch


def test_remote_deploy_allows_only_its_app_directory_for_git_operations() -> None:
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert 'git -c safe.directory="$APP_DIR" "$@"' in source
    assert 'safe_git reset --hard "$DEPLOY_SHA"' in source
