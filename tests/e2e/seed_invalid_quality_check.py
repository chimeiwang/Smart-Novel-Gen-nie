from __future__ import annotations

import asyncio
import os
import shutil
import sys
from urllib.parse import parse_qs, unquote, urlsplit


async def seed_invalid_quality_check(check_id: str) -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("E2E 缺少 DATABASE_URL")
    psql = shutil.which("psql")
    if not psql:
        raise RuntimeError("E2E 构造终检记录需要 psql")
    url = urlsplit(database_url.replace("postgresql+asyncpg://", "postgresql://", 1))
    environment = {
        **os.environ,
        "PGHOST": url.hostname or "localhost",
        "PGPORT": str(url.port or 5432),
        "PGDATABASE": url.path.lstrip("/"),
        "PGUSER": unquote(url.username or ""),
        "PGPASSWORD": unquote(url.password or ""),
    }
    for option, variable in (
        ("sslmode", "PGSSLMODE"), ("sslrootcert", "PGSSLROOTCERT"),
        ("sslcert", "PGSSLCERT"), ("sslkey", "PGSSLKEY"),
    ):
        values = parse_qs(url.query).get(option)
        if values:
            environment[variable] = values[-1]
    # psql 的引用变量绑定 SQL 值，凭据不进入进程参数或错误输出。
    process = await asyncio.create_subprocess_exec(
        psql,
        "--no-psqlrc",
        "-v",
        "ON_ERROR_STOP=1",
        "-At",
        "-v",
        f"check_id={check_id}",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=environment,
    )
    sql = """
                    BEGIN;
                    UPDATE public."ChapterQualityCheck"
                    SET status = 'completed',
                        result = NULL,
                        "scoreOverall" = NULL,
                        "qualityGate" = NULL,
                        "updatedAt" = CURRENT_TIMESTAMP
                    WHERE id = :'check_id'
                    RETURNING id;
                    COMMIT;
                    """
    stdout, _stderr = await process.communicate(sql.encode())
    if process.returncode != 0 or check_id not in stdout.decode().splitlines():
        raise RuntimeError("无法构造指定的 E2E 终检记录")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("用法：seed_invalid_quality_check.py <check_id>")
    asyncio.run(seed_invalid_quality_check(sys.argv[1]))
