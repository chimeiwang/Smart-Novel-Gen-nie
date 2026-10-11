"""离线探针必须证明引擎已退役，且不向镜像提供生产网络或凭据。"""

import os
import subprocess
from pathlib import Path

import pytest

from tests.architecture.test_deploy_scripts import POSIX_SHELL, _write_executable

ROOT = Path(__file__).parents[2]
VERIFIER = ROOT / "scripts/verify-retired-engine-image.sh"


def test_core_declares_current_engine_in_final_runtime_layer():
    source = (ROOT / "infra/docker/core-api.Dockerfile").read_text()
    marker = 'LABEL cn.inkforge.execution-engine="v1"'
    assert marker in source
    assert source.index(marker) > source.index(" AS runtime")
    assert "durable-route-all" not in source


@pytest.mark.parametrize("component", ["core", "agent"])
@pytest.mark.parametrize("inspect_status,probe_status", [(0, 0), (7, 0), (0, 7)])
def test_retirement_probe_requires_real_image_and_successful_execution(
    tmp_path, component, inspect_status, probe_status
):
    binary = tmp_path / "bin"
    binary.mkdir()
    log = tmp_path / "docker.log"
    _write_executable(
        binary / "docker",
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$*" >> "$PROBE_LOG"\n'
        'case "$1" in image) exit "$INSPECT_STATUS" ;;\n'
        'run) exit "$PROBE_STATUS" ;; *) exit 99 ;; esac\n',
    )
    env = {
        **os.environ,
        "PATH": str(binary) + os.pathsep + os.environ["PATH"],
        "PROBE_LOG": str(log),
        "INSPECT_STATUS": str(inspect_status),
        "PROBE_STATUS": str(probe_status),
    }
    result = subprocess.run(  # noqa: S603 - 固定仓库脚本与本地测试替身。
        [POSIX_SHELL, str(VERIFIER), component, "sha256:" + "a" * 64],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )  # noqa: S603
    assert (result.returncode == 0) is (inspect_status == probe_status == 0)
    calls = log.read_text()
    if inspect_status == 0:
        assert "--network none" in calls and "--read-only" in calls and "--cap-drop ALL" in calls
        assert "--env" not in calls and "--mount" not in calls
        assert (
            "RetiredEngineProbe"
            if component == "core"
            else 'find_spec("inkforge_agents.execution") is None'
        ) in calls
