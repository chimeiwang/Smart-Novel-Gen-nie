"""服务端模型账单请求标识的稳定作用域。"""

from __future__ import annotations

import hashlib


def video_task_billing_request_prefix(task_id: str) -> str:
    """生成不泄露任务 ID、可供 Core 精确聚合的视频任务账单前缀。"""

    digest = hashlib.sha256(task_id.encode("utf-8")).hexdigest()[:32]
    return f"video-task-{digest}-"
