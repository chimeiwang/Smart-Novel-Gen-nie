from __future__ import annotations

from ..config import Settings
from .base import ModelProvider
from .fake import FakeModelProvider
from .openai_compatible import OpenAICompatibleProvider


def create_model_provider(settings: Settings) -> ModelProvider:
    if settings.model_provider == "fake":
        return FakeModelProvider()
    return OpenAICompatibleProvider(settings)
