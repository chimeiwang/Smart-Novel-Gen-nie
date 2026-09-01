"""E2E Agent 工厂；生产镜像仍使用原始工厂且不加载本模块。"""

from __future__ import annotations

from controlled_provider import ControlledFakeModelProvider
from fastapi import FastAPI
from inkforge_agents.app import create_app as create_inkforge_app
from inkforge_agents.config import Settings


def create_app() -> FastAPI:
    settings = Settings()
    if (
        settings.environment != "test"
        or settings.e2e_execution_control_url is None
        or settings.e2e_execution_control_token is None
    ):
        raise RuntimeError("E2E Agent 工厂缺少 test 环境与随机控制令牌双门禁")
    provider = ControlledFakeModelProvider(
        control_url=settings.e2e_execution_control_url,
        control_token=settings.e2e_execution_control_token.get_secret_value(),
    )
    return create_inkforge_app(settings=settings, model_provider=provider)
