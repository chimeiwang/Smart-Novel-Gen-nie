from inkforge_core.billing.pricing import (
    CREDIT_MICROS_PER_CREDIT,
    SIGNUP_BONUS_MICROS,
    calculate_usage_cost_micros,
    estimate_tokens_from_text,
    format_credit_micros,
)


def test_deepseek_flash_pricing_preserves_cached_input_rate() -> None:
    cost = calculate_usage_cost_micros(
        prompt_tokens=1_000_000,
        cached_tokens=100_000,
        completion_tokens=1_000_000,
    )

    assert cost == 2_902 * CREDIT_MICROS_PER_CREDIT
    assert SIGNUP_BONUS_MICROS == 1_000 * CREDIT_MICROS_PER_CREDIT


def test_credit_display_and_prompt_estimate_match_existing_behavior() -> None:
    assert format_credit_micros(123_456_000) == "123.456"
    assert format_credit_micros(-2_500_000) == "-2.5"
    assert estimate_tokens_from_text(" 甲 乙\n丙 ") == 3
    assert estimate_tokens_from_text("   ") == 1
