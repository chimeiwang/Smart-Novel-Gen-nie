from __future__ import annotations

import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from tests.architecture.durable_agent_execution_fixtures import BASE_SCHEMA, _psql
from tests.architecture.test_durable_agent_execution_rollout import (
    ROOT,
    MigrationFixture,
    _drain_source_files,
    _pre_ddl_redis_files,
)


def _fixture(tmp_path: Path):
    fixture = MigrationFixture(tmp_path)
    shutil.copy2(ROOT / "scripts" / "durable_agent_pre_migration_drain.py",
                 fixture.app_dir / "scripts")
    return fixture


def test_未迁移且旧Task非零时仍可读取真实前置队列边界而不伪造marker(tmp_path) -> None:
    fixture = _fixture(tmp_path)
    sources = _drain_source_files(
        tmp_path, postgres_metric="v1WritingTasksActive", pre_contract=True
    )
    result = fixture.run("drain-status", extra_env={
        **sources, "FAKE_RUNNING_CORE_SCHEMA_READY": "false",
        "FAKE_V1_DRAIN_INDEX_VERSION": "__missing__",
        "FAKE_V2_DRAIN_INDEX_VERSION": "__missing__",
    })

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["schemaState"] == "unmigrated"
    assert report["v2PostgresFacts"] == "absent-by-verified-schema"
    assert report["redisIndexes"] is None
    assert report["metrics"]["v1WritingTasksActive"]["count"] == 1
    assert report["metrics"]["v2RunsActive"]["count"] == 0
    log = fixture.log_path.read_text()
    assert " EVAL " not in log
    assert " SET " not in log
    assert "--file" not in log
    assert fixture.password not in log + result.stdout + result.stderr


@pytest.mark.parametrize("change", ["queue", "callback", "quarantine", "schema", "runtime"])
def test_迁移前快照不豁免真实执行尾项或已启用运行环境(tmp_path, change) -> None:
    fixture = _fixture(tmp_path)
    environment = {"FAKE_RUNNING_CORE_SCHEMA_READY": "false"}
    if change == "queue":
        environment.update(_pre_ddl_redis_files(tmp_path, v1_metric="queued"))
    elif change == "callback":
        environment.update(_pre_ddl_redis_files(tmp_path, v2_metric="pending"))
    elif change == "quarantine":
        environment.update(_pre_ddl_redis_files(tmp_path, quarantined=True))
    elif change == "schema":
        environment["FAKE_RUNNING_CORE_SCHEMA_READY"] = "true"
    else:
        environment["FAKE_RUNNING_CORE_V1_FRESH_STARTS"] = "true"
    result = fixture.run("drain-status", extra_env=environment)
    assert result.returncode != 0


def test_真实未迁移PG与双Redis入口允许旧Task但拒绝真实队列且不初始化marker(
    tmp_path, isolated_postgres
) -> None:
    docker, postgres = isolated_postgres
    _psql(docker, postgres, "DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    _psql(docker, postgres, BASE_SCHEMA.read_text(encoding="utf-8"))
    _psql(docker, postgres, """
        INSERT INTO public."User" (id,username,"passwordHash","updatedAt")
        VALUES ('pre-user','pre-user','test',CURRENT_TIMESTAMP);
        INSERT INTO public."Novel" (id,name,"userId","updatedAt")
        VALUES ('pre-novel','真实前置检查','pre-user',CURRENT_TIMESTAMP);
        INSERT INTO public."Chapter" (id,"novelId",title,content,"order","updatedAt")
        VALUES ('pre-chapter','pre-novel','第一章','完整正文',1,CURRENT_TIMESTAMP);
        INSERT INTO public."WritingTask" (id,"novelId","chapterId","targetWordCount",
            "selectedAgents",phase,"updatedAt")
        VALUES ('pre-task','pre-novel','pre-chapter',1000,'writer','idle',CURRENT_TIMESTAMP);
    """)
    fixture = _fixture(tmp_path)
    containers = {}

    def real(*arguments):
        result = subprocess.run(  # noqa: S603 - 本测试创建的具名隔离 Redis，无业务资源
            [docker, *arguments], capture_output=True, text=True, timeout=45, check=False,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    try:
        for name in ("redis", "execution-redis"):
            containers[name] = real(
                "run", "--rm", "-d", "--name", "inkforge-pre-drain-" + uuid.uuid4().hex,
                "--network", "none", "--memory", "96m", "--memory-swap", "96m",
                "redis:7.4-alpine", "redis-server", "--save", "",
                "--appendonly", "yes" if name == "execution-redis" else "no",
                "--appendfsync", "always", "--aof-load-truncated", "no",
                "--maxmemory", "32mb", "--maxmemory-policy", "noeviction",
            )
            real("exec", containers[name], "redis-cli", "PING")
        original = fixture.bin_dir / "docker-fixture"
        (fixture.bin_dir / "docker").rename(original)
        bridge = fixture.bin_dir / "docker"
        bridge.write_text(
            f"#!{sys.executable}\nimport os,sys,subprocess\n"
            f"mapping={containers!r}\ndocker={docker!r}\nargs=sys.argv[1:]\n"
            "if args[0]=='compose' and args[-3:-1]==['ps','-q'] and args[-1] in mapping:\n"
            " print(mapping[args[-1]]);sys.exit(0)\n"
            "if args[0]=='inspect' and args[-1] in mapping.values():\n"
            " os.execv(docker,[docker,*args])\n"
            "if args[0]=='compose' and 'exec' in args:\n"
            " tail=args[args.index('exec')+1:]\n"
            " if tail[0]=='-T':tail=tail[1:]\n"
            " if tail[0] in mapping:\n"
            "  os.execv(docker,[docker,'exec','-i',mapping[tail[0]],*tail[1:]])\n"
            f"os.execv({str(original)!r},[{str(original)!r},*args])\n"
        )
        bridge.chmod(0o700)
        proxy = fixture.bin_dir / "psql"
        proxy.write_text(
            f"#!{sys.executable}\nimport subprocess,sys\n"
            f"args={[docker, 'exec', '-i', postgres, 'psql', '-X', '-qAt', '-v', 'ON_ERROR_STOP=1', '-v', 'expected_database=novelwriterdev', '-U', 'postgres', '-d', 'novelwriterdev']!r}\n"  # noqa: E501
            "result=subprocess.run(args,input=sys.stdin.buffer.read(),capture_output=True)\n"
            "sys.stdout.buffer.write(result.stdout);sys.stderr.buffer.write(result.stderr)\n"
            "sys.exit(result.returncode)\n"
        )
        proxy.chmod(0o700)
        accepted = fixture.run(
            "drain-status", extra_env={"FAKE_RUNNING_CORE_SCHEMA_READY": "false"}
        )
        assert accepted.returncode == 0, accepted.stderr
        report = json.loads(accepted.stdout)
        assert report["schemaState"] == "unmigrated"
        assert report["metrics"]["v1WritingTasksActive"]["count"] == 1
        assert report["metrics"]["v2RunsActive"]["count"] == 0
        assert real("exec", containers["redis"], "redis-cli", "GET",
                    "inkforge:runs:drain:index-version") == ""
        assert real("exec", containers["execution-redis"], "redis-cli", "GET",
                    "inkforge:executions:drain:index-version") == ""
        real("exec", containers["redis"], "redis-cli", "ZADD", "inkforge:runs:ready", "1", "job")
        rejected = fixture.run(
            "drain-status", extra_env={"FAKE_RUNNING_CORE_SCHEMA_READY": "false"}
        )
        assert rejected.returncode != 0
    finally:
        for container in containers.values():
            real("rm", "--force", container)
