from __future__ import annotations

from ..config import Settings
from .base import ModelProvider
from .deepseek_v4 import DeepSeekV4Provider
from .fake import FakeModelProvider
from .openai_compatible import OpenAICompatibleProvider


def create_model_provider(settings: Settings) -> ModelProvider:
    if settings.model_provider == "fake":
        return FakeModelProvider()
    if settings.openai_compatibility_profile == "deepseek_v4":
        return DeepSeekV4Provider(settings)
    return OpenAICompatibleProvider(settings)
