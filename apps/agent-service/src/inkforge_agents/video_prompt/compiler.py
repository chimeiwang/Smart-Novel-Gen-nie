"""兼容旧导入路径的共享视频编译器导出。"""

from inkforge_contracts.video_compiler import (
    DEFAULT_MAX_CHINESE_PROMPT_CHARACTERS,
    DEFAULT_MAX_PROVIDER_PROMPT_CHARACTERS,
    RECOMMENDED_CHINESE_PROMPT_CHARACTERS,
    PromptCompileError,
    SeedancePromptCompiler,
    materialize_scene_assets,
)

__all__ = [
    "DEFAULT_MAX_CHINESE_PROMPT_CHARACTERS",
    "DEFAULT_MAX_PROVIDER_PROMPT_CHARACTERS",
    "RECOMMENDED_CHINESE_PROMPT_CHARACTERS",
    "PromptCompileError",
    "SeedancePromptCompiler",
    "materialize_scene_assets",
]
