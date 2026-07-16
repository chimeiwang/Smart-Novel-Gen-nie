from __future__ import annotations

import asyncio
import os
import sys

from inkforge_core.db.session import create_database_engine
from sqlalchemy import text


async def seed_invalid_quality_check(check_id: str) -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("E2E 缺少 DATABASE_URL")
    engine = create_database_engine(database_url)
    try:
        async with engine.begin() as connection:
            result = await connection.execute(
                text(
                    '''
                    UPDATE public."ChapterQualityCheck"
                    SET status = 'completed',
                        result = NULL,
                        "scoreOverall" = NULL,
                        "qualityGate" = NULL,
                        "updatedAt" = CURRENT_TIMESTAMP
                    WHERE id = :check_id
                    RETURNING id
                    '''
                ),
                {"check_id": check_id},
            )
            if result.scalar_one_or_none() != check_id:
                raise RuntimeError("找不到待构造的 E2E 终检记录")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("用法：seed_invalid_quality_check.py <check_id>")
    asyncio.run(seed_invalid_quality_check(sys.argv[1]))
