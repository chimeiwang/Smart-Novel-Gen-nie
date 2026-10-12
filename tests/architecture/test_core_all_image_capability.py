"""全量配置只允许切换到和回滚到明确支持 all 的 Core 镜像。"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tests.architecture.test_deploy_scripts import POSIX_SHELL, _posix_path, _write_executable

ROOT = Path(__file__).parents[2]
VERIFIER = ROOT / "scripts" / "verify-durable-agent-v2-image.sh"


def test_core_image_declares_all_support_in_the_final_runtime_layer() -> None:
    source = (ROOT / "infra/docker/core-api.Dockerfile").read_text()
    assert 'LABEL cn.inkforge.durable-route-all="true"' in source
    assert source.index('LABEL cn.inkforge.durable-route-all="true"') > source.index(" AS runtime")


@pytest.mark.parametrize(
    ("component", "label", "class_status", "inspect_status", "accepted"),
    [
        ("core-all", "true", 0, 0, True),
        ("core-all", "", 0, 0, False),
        ("core-all", "false", 0, 0, False),
        ("core-all", "TRUE", 0, 0, False),
        ("core-all", "true\n", 0, 0, False),
        ("core-all", "true\nextra", 0, 0, False),
        ("core-all", "true", 7, 0, False),
        ("core-all", "true", 0, 7, False),
        ("core", "", 0, 0, True),
        ("core", "false", 0, 0, True),
    ],
)
def test_core_all_probe_requires_exact_label_and_original_core_checks(
    tmp_path: Path, component: str, label: str, class_status: int,
    inspect_status: int, accepted: bool,
) -> None:
    binary = tmp_path / "bin"
    binary.mkdir()
    log = tmp_path / "docker.log"
    _write_executable(
        binary / "docker",
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$*" >> "$PROBE_LOG"\n'
        'case " $* " in\n'
        '  *" image inspect --format "*)\n'
        '    [ "$PROBE_INSPECT_STATUS" = 0 ] || exit "$PROBE_INSPECT_STATUS"\n'
        '    if [ "$PROBE_ALL_LABEL" = true ]; then echo true; else echo false; fi ;;\n'
        '  *" image inspect "*) exit 0 ;;\n'
        '  *" run "*) exit "$PROBE_CLASS_STATUS" ;;\n'
        '  *) exit 99 ;;\n'
        'esac\n',
    )
    environment = {
        **os.environ,
        "PATH": str(binary) + os.pathsep + os.environ["PATH"],
        "PROBE_LOG": _posix_path(log),
        "PROBE_ALL_LABEL": label,
        "PROBE_CLASS_STATUS": str(class_status),
        "PROBE_INSPECT_STATUS": str(inspect_status),
    }
    result = subprocess.run(  # noqa: S603 - 只运行仓库脚本和本测试替身。
        [POSIX_SHELL, str(VERIFIER), component, "sha256:" + "a" * 64],
        env=environment, capture_output=True, text=True, timeout=15, check=False,
    )
    assert (result.returncode == 0) is accepted
    if accepted:
        assert result.stdout == f"v2-aware-image-ok:{component}\n"
    else:
        assert result.stdout == ""
    calls = log.read_text() if log.exists() else ""
    if accepted or class_status:
        assert "RoutingWritingRunStarter.class" in calls
        assert "DurableAgentSchemaGate.class" in calls
    if component == "core-all" and class_status == 0:
        assert '{{eq (index .Config.Labels "cn.inkforge.durable-route-all") "true"}}' in calls
    if component == "core":
        assert "cn.inkforge.durable-route-all" not in calls
    for line in calls.splitlines():
        if line.startswith("run "):
            assert "--network none" in line and "--read-only" in line
            assert "--env" not in line and "--mount" not in line
