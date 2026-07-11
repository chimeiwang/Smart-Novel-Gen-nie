from __future__ import annotations

from .repository import RedisRunQueue


async def recover_abandoned_jobs(queue: RedisRunQueue) -> int:
    return await queue.recover_expired()
