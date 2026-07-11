from __future__ import annotations

CREDIT_MICROS_PER_CREDIT = 1_000_000
SIGNUP_BONUS_MICROS = 1_000 * CREDIT_MICROS_PER_CREDIT
UNCACHED_INPUT_MICROS_PER_TOKEN = 1_000
CACHED_INPUT_MICROS_PER_TOKEN = 20
OUTPUT_MICROS_PER_TOKEN = 2_000
MIN_OUTPUT_TOKEN_BUDGET = 128


def calculate_usage_cost_micros(
    *, prompt_tokens: int, cached_tokens: int, completion_tokens: int
) -> int:
    normalized_prompt = max(prompt_tokens, 0)
    normalized_cached = min(max(cached_tokens, 0), normalized_prompt)
    normalized_completion = max(completion_tokens, 0)
    return (
        (normalized_prompt - normalized_cached) * UNCACHED_INPUT_MICROS_PER_TOKEN
        + normalized_cached * CACHED_INPUT_MICROS_PER_TOKEN
        + normalized_completion * OUTPUT_MICROS_PER_TOKEN
    )


def estimate_tokens_from_text(text: str) -> int:
    return max(1, len("".join(text.split())))


def format_credit_micros(value: int) -> str:
    negative = value < 0
    absolute = abs(value)
    whole, fraction = divmod(absolute, CREDIT_MICROS_PER_CREDIT)
    prefix = "-" if negative else ""
    if fraction == 0:
        return f"{prefix}{whole}"
    fraction_text = f"{fraction:06d}".rstrip("0")[:3]
    return f"{prefix}{whole}.{fraction_text}"
