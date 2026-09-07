from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tests.architecture.durable_agent_execution_fixtures import BASE_SCHEMA, _psql, _scalar

ROOT = Path(__file__).parents[2]
MODULE = ROOT / "scripts" / "archive_legacy_writing_tasks.py"
ENTRY = ROOT / "scripts" / "archive-legacy-writing-tasks.sh"


def _module():
    specification = importlib.util.spec_from_file_location("legacy_writing_archive", MODULE)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _scope():
    return {
        "schemaVersion": 1,
        "database": "novelwriterdev",
        "tasks": [{
            "id": "archive-task", "phase": "idle", "novelId": "archive-novel",
            "updatedAt": "2026-09-07T00:00:00.000Z",
        }],
    }


def test_清单仅允许具名数据库和精确冻结任务() -> None:
    archive = _module()
    assert archive.validate_scope(_scope(), "novelwriterdev") == _scope()
    with pytest.raises(archive.ArchiveError):
        archive.validate_scope(_scope(), "novelwriter")


@pytest.mark.parametrize("phase", ["completed", "error", "active", "waiting_call", "*"])
def test_不能以通配或其他阶段扩大退出范围(phase: str) -> None:
    archive = _module()
    scope = _scope()
    scope["tasks"][0]["phase"] = phase
    with pytest.raises(archive.ArchiveError):
        archive.validate_scope(scope, "novelwriterdev")


def test_重复任务或额外字段不能进入清单() -> None:
    archive = _module()
    scope = _scope()
    scope["tasks"].append(dict(scope["tasks"][0]))
    with pytest.raises(archive.ArchiveError):
        archive.validate_scope(scope, "novelwriterdev")
    scope = _scope()
    scope["deleteAll"] = True
    with pytest.raises(archive.ArchiveError):
        archive.validate_scope(scope, "novelwriterdev")


PROXY = r'''#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path

tool = Path(sys.argv[0]).name
arguments = sys.argv[1:]
with Path(os.environ["ARCHIVE_TEST_LOG"]).open("a") as stream:
    stream.write(json.dumps([tool, *arguments]) + "\n")
prefix = [os.environ["ARCHIVE_TEST_DOCKER"], "exec", "-i", os.environ["ARCHIVE_TEST_CONTAINER"]]
if tool == "psql":
    result = subprocess.run(prefix + ["psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1",
                                     "-U", "postgres", "-d", "novelwriterdev"],
                            input=sys.stdin.buffer.read(), capture_output=True)
elif tool == "pg_dump":
    result = subprocess.run(prefix + ["pg_dump", "-U", "postgres", "--format=custom",
                                     "--no-owner", "--no-acl", "novelwriterdev"],
                            capture_output=True)
    destination = Path(arguments[arguments.index("--file") + 1])
    destination.write_bytes(result.stdout)
    result.stdout = b""
else:
    result = subprocess.run(prefix + ["pg_restore", "--list"],
                            input=Path(arguments[-1]).read_bytes(), capture_output=True)
sys.stdout.buffer.write(result.stdout)
sys.stderr.buffer.write(result.stderr)
sys.exit(result.returncode)
'''


def _runtime(tmp_path: Path, isolated_postgres, monkeypatch):
    docker, container = isolated_postgres
    _psql(docker, container, "DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    _psql(docker, container, BASE_SCHEMA.read_text(encoding="utf-8"))
    _psql(docker, container, """
        INSERT INTO public."User" (id, username, "passwordHash", "updatedAt")
        VALUES ('archive-user', 'archive-user', 'test', CURRENT_TIMESTAMP);
        INSERT INTO public."Novel" (id, name, "userId", "updatedAt")
        VALUES ('archive-novel', '原小说完整保存', 'archive-user', CURRENT_TIMESTAMP);
        INSERT INTO public."Chapter" (id, "novelId", title, content, "order", "updatedAt")
        VALUES ('archive-chapter', 'archive-novel', '第一章',
                '正式正文不许修改', 1, CURRENT_TIMESTAMP);
        INSERT INTO public."Outline" (id, "novelId", content, "updatedAt")
        VALUES ('archive-outline', 'archive-novel', '完整大纲不许修改', CURRENT_TIMESTAMP);
        INSERT INTO public."WritingSession" (id, "novelId", "chapterId", "updatedAt")
        VALUES ('archive-session', 'archive-novel', 'archive-chapter', CURRENT_TIMESTAMP);
        INSERT INTO public."WritingMessage" (id, "sessionId", role, content)
        VALUES ('archive-message', 'archive-session', 'user', '原聊天也不截断');
        INSERT INTO public."WritingTask" (id, "novelId", "chapterId", "targetWordCount",
            "selectedAgents", phase, "graphStateJson", "writingSessionId", "updatedAt")
        VALUES ('archive-task','archive-novel','archive-chapter',1000,'writer','idle',
                '{"original":"冻结输入完整保留"}','archive-session','2026-09-07T00:00:00'),
               ('archive-waiting','archive-novel','archive-chapter',1000,'writer',
                'awaiting_user_review','{"original":"待审输入完整保留"}',
                'archive-session','2026-09-07T00:00:00'),
               ('other-task','archive-novel','archive-chapter',1000,'writer','idle',
                NULL,NULL,'2026-09-07T00:00:00');
        INSERT INTO public."WritingRunCommand" (id, "taskId", kind, "payloadJson",
            "idempotencyKey", status, "resultJson", "updatedAt")
        VALUES ('archive-command','archive-waiting','start','{"sourceBindings":{"original":true}}',
                'archive-idempotency','succeeded','{"original":"原回执"}',CURRENT_TIMESTAMP);
        INSERT INTO public."ReviewArtifact" (id, "novelId", "chapterId", "taskId", kind,
            status, "payloadJson", revision, "updatedAt")
        VALUES ('archive-artifact','archive-novel','archive-chapter','archive-waiting',
                'chapter_draft','awaiting_user','{"content":"完整未采用候选"}',1,CURRENT_TIMESTAMP);
        INSERT INTO public."ReviewArtifactRevision" (id,"artifactId",revision,"payloadJson")
        VALUES ('archive-revision','archive-artifact',1,'{"content":"完整未采用候选"}');
    """)
    binary = tmp_path / "bin"
    binary.mkdir()
    for tool in ("psql", "pg_dump", "pg_restore"):
        path = binary / tool
        path.write_text(PROXY.replace("#!/usr/bin/env python3", f"#!{sys.executable}", 1))
        path.chmod(0o700)
    app = tmp_path / "app"
    (app / "scripts").mkdir(parents=True)
    queue = app / "scripts" / "durable-agent-execution-migration.sh"
    archive = _module()
    metrics = sorted(archive.STATIC_METRICS | archive.EXECUTION_METRICS)
    queue.write_text(
        "#!/bin/sh\nexec python3 - <<'PY'\nimport json,os\n"
        "from datetime import datetime,timezone\n"
        f"metrics={{name:{{'count':0}} for name in {metrics!r}}}\n"
        "metrics['v1AgentJobsQueued']['count']=int(os.environ.get('ARCHIVE_TEST_QUEUED','0'))\n"
        "print(json.dumps({'database':'novelwriterdev','metrics':metrics,"
        "'coreRuntime':{'routeMode':'off','v1FreshStartsEnabled':False},"
        "'sampleWindow':{'finishedAt':datetime.now(timezone.utc).isoformat()}}))\nPY\n"
    )
    env = app / ".env"
    env.write_text(
        "DATABASE_URL=postgresql://postgres:archive-password-do-not-print"
        "@host.docker.internal/novelwriterdev\n"
    )
    env.chmod(0o600)
    scope = _scope()
    scope["tasks"].append({**scope["tasks"][0], "id": "archive-waiting",
                           "phase": "awaiting_user_review"})
    scope_path = tmp_path / "scope.json"
    scope_path.write_text(json.dumps(scope))
    for key, value in {
        "PATH": str(binary) + os.pathsep + os.environ["PATH"],
        "APP_DIR": str(app), "DURABLE_AGENT_MIGRATION_ENV_FILE": str(env),
        "ARCHIVE_TEST_DOCKER": docker, "ARCHIVE_TEST_CONTAINER": container,
        "ARCHIVE_TEST_LOG": str(tmp_path / "commands.log"),
    }.items():
        monkeypatch.setenv(key, value)
    return scope_path, tmp_path / "archive", app


def _invoke(action, paths):
    scope, directory, _ = paths
    result = subprocess.run(  # noqa: S603 - 只执行仓库 helper 与隔离 PostgreSQL 工具代理
        [sys.executable, str(MODULE), action, "novelwriterdev", str(scope), str(directory)],
        capture_output=True, text=True, timeout=45, check=False,
    )
    assert "archive-password-do-not-print" not in result.stdout + result.stderr
    assert "正式正文不许修改" not in result.stdout + result.stderr
    return result


def test_真实PG完整预览备份退出核验及重放只改两个字段(
    tmp_path, isolated_postgres, monkeypatch
) -> None:
    paths = _runtime(tmp_path, isolated_postgres, monkeypatch)
    started = time.monotonic()
    for action in ("preview", "backup", "apply", "verify", "apply", "backup"):
        result = _invoke(action, paths)
        assert result.returncode == 0, (action, result.stderr)
    before = json.loads((paths[1] / "before.json").read_text())
    after = json.loads((paths[1] / "after.json").read_text())
    assert before["tables"] == after["tables"]
    assert len(before["tables"]) >= 60
    for old, new in zip(before["tasks"], after["tasks"], strict=True):
        assert new["phase"] == "error"
        assert {key: value for key, value in old.items() if key not in {"phase", "updatedAt"}} == {
            key: value for key, value in new.items() if key not in {"phase", "updatedAt"}
        }
    assert _scalar(
        *isolated_postgres, 'SELECT phase FROM public."WritingTask" WHERE id=\'other-task\''
    ) == "idle"
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in paths[1].iterdir())
    assert "archive-password-do-not-print" not in (tmp_path / "commands.log").read_text()
    assert time.monotonic() - started < 45


@pytest.mark.parametrize("mutation", [
    'UPDATE public."WritingTask" SET phase=\'active\' WHERE id=\'archive-task\';',
    'UPDATE public."WritingTask" SET "updatedAt"="updatedAt"+INTERVAL \'1 millisecond\' '
    'WHERE id=\'archive-task\';',
    'UPDATE public."WritingRunCommand" SET status=\'pending\' WHERE id=\'archive-command\';',
    'UPDATE public."Chapter" SET content=\'合法新正文\' WHERE id=\'archive-chapter\';',
    'UPDATE public."ReviewArtifact" SET status=\'applying\' WHERE id=\'archive-artifact\';',
])
def test_备份后任务竞争活动命令或成果变化拒绝整体退出(
    tmp_path, isolated_postgres, monkeypatch, mutation
) -> None:
    paths = _runtime(tmp_path, isolated_postgres, monkeypatch)
    assert _invoke("backup", paths).returncode == 0
    _psql(*isolated_postgres, mutation)
    result = _invoke("apply", paths)
    assert result.returncode != 0
    assert _scalar(
        *isolated_postgres, 'SELECT count(*) FROM public."WritingTask" WHERE phase=\'error\''
    ) == "0"


def test_事务内副作用改变正式成果必须回滚全部退出(tmp_path, isolated_postgres, monkeypatch) -> None:
    paths = _runtime(tmp_path, isolated_postgres, monkeypatch)
    assert _invoke("backup", paths).returncode == 0
    _psql(*isolated_postgres, """
        CREATE FUNCTION public.archive_test_side_effect() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN UPDATE public."Chapter" SET content='不得提交的副作用'; RETURN NEW; END; $$;
        CREATE TRIGGER archive_test_side_effect BEFORE UPDATE ON public."WritingTask"
        FOR EACH ROW EXECUTE FUNCTION public.archive_test_side_effect();
    """)
    result = _invoke("apply", paths)
    assert result.returncode != 0
    assert _scalar(
        *isolated_postgres, 'SELECT count(*) FROM public."WritingTask" WHERE phase=\'error\''
    ) == "0"
    assert _scalar(*isolated_postgres, 'SELECT content FROM public."Chapter"') == "正式正文不许修改"


def test_真实队列非空时不执行归档(tmp_path, isolated_postgres, monkeypatch) -> None:
    paths = _runtime(tmp_path, isolated_postgres, monkeypatch)
    assert _invoke("backup", paths).returncode == 0
    monkeypatch.setenv("ARCHIVE_TEST_QUEUED", "1")
    assert _invoke("apply", paths).returncode != 0
    assert not (paths[1] / "apply-intent.json").exists()


def test_无Task绑定的applying也必须阻断而不能作为静态候选忽略(
    tmp_path, isolated_postgres, monkeypatch
) -> None:
    paths = _runtime(tmp_path, isolated_postgres, monkeypatch)
    _psql(*isolated_postgres, """
        UPDATE public."ReviewArtifact" SET "taskId"=NULL,status='applying'
        WHERE id='archive-artifact';
    """)
    assert _invoke("preview", paths).returncode != 0
    assert _invoke("backup", paths).returncode != 0
    assert not (paths[1] / "database.dump").exists()


def test_全表写锁五秒超时退出不循环且普通读取仍可用(
    tmp_path, isolated_postgres, monkeypatch
) -> None:
    paths = _runtime(tmp_path, isolated_postgres, monkeypatch)
    assert _invoke("backup", paths).returncode == 0
    with ThreadPoolExecutor(max_workers=1) as executor:
        locked = executor.submit(_psql, *isolated_postgres, """
            BEGIN;
            LOCK TABLE public."Chapter" IN SHARE ROW EXCLUSIVE MODE;
            SELECT pg_sleep(9);
            COMMIT;
        """)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            exists = _scalar(*isolated_postgres, """
                SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_locks
                    WHERE relation='public."Chapter"'::regclass
                      AND mode='ShareRowExclusiveLock' AND granted)
            """)
            if exists == "t":
                break
            time.sleep(0.05)
        assert exists == "t"
        assert _scalar(*isolated_postgres, 'SELECT content FROM public."Chapter"')
        started = time.monotonic()
        result = _invoke("apply", paths)
        elapsed = time.monotonic() - started
        assert result.returncode != 0
        assert 5 <= elapsed < 9
        locked.result(timeout=12)
    assert _scalar(
        *isolated_postgres, 'SELECT count(*) FROM public."WritingTask" WHERE phase=\'error\''
    ) == "0"


def test_原归档篡改拒绝执行且不覆盖备份(tmp_path, isolated_postgres, monkeypatch) -> None:
    paths = _runtime(tmp_path, isolated_postgres, monkeypatch)
    assert _invoke("backup", paths).returncode == 0
    original = (paths[1] / "database.dump").read_bytes()
    (paths[1] / "before.json").write_text("{}")
    assert _invoke("apply", paths).returncode != 0
    assert (paths[1] / "database.dump").read_bytes() == original


def test_提交后回执发布失败仍能凭原意图独立恢复核验(
    tmp_path, isolated_postgres, monkeypatch
) -> None:
    paths = _runtime(tmp_path, isolated_postgres, monkeypatch)
    assert _invoke("backup", paths).returncode == 0
    archive = _module()
    original_link = archive.os.link

    def failed_after_publish(source, destination):
        if Path(destination).name == "after.json":
            raise OSError("模拟回执发布中断")
        return original_link(source, destination)

    monkeypatch.setattr(archive.os, "link", failed_after_publish)
    with pytest.raises(OSError, match="模拟回执发布中断"):
        archive.perform("apply", "novelwriterdev", paths[0], paths[1], paths[2], paths[2] / ".env")
    assert not (paths[1] / "after.json").exists()
    assert _scalar(
        *isolated_postgres, 'SELECT count(*) FROM public."WritingTask" WHERE phase=\'error\''
    ) == "2"
    monkeypatch.setattr(archive.os, "link", original_link)
    assert _invoke("verify", paths).returncode == 0
    assert _invoke("apply", paths).returncode == 0


def test_触发器伪造成功终态也必须在同事务拒绝(tmp_path, isolated_postgres, monkeypatch) -> None:
    paths = _runtime(tmp_path, isolated_postgres, monkeypatch)
    assert _invoke("backup", paths).returncode == 0
    _psql(*isolated_postgres, """
        CREATE FUNCTION public.archive_test_false_success() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN NEW.phase='completed'; RETURN NEW; END; $$;
        CREATE TRIGGER archive_test_false_success BEFORE UPDATE ON public."WritingTask"
        FOR EACH ROW EXECUTE FUNCTION public.archive_test_false_success();
    """)
    assert _invoke("apply", paths).returncode != 0
    assert _scalar(
        *isolated_postgres,
        'SELECT count(*) FROM public."WritingTask" WHERE phase IN (\'error\',\'completed\')',
    ) == "0"
