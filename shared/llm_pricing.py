# shared/llm_pricing.py
"""
Centralized LLM pricing calculator for fairydust platform.
All costs calculated server-side only - never accept costs from client APIs.
"""

import logging
import os
from enum import Enum

logger = logging.getLogger(__name__)


class LLMProvider(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


# Pricing per million tokens (input/output) - Updated 2024
PRICING_CONFIG = {
    "anthropic": {
        # Claude models - per million tokens
        "claude-opus-4": {"input": 15.0, "output": 75.0},
        "claude-sonnet-4": {"input": 3.0, "output": 15.0},
        "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},  # Current production model
        "claude-3-5-haiku-20241022": {"input": 0.8, "output": 4.0},
        "claude-3-5-haiku": {"input": 0.8, "output": 4.0},
        "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},  # Legacy haiku model
        "claude-3-sonnet-20240229": {"input": 3.0, "output": 15.0},  # Legacy sonnet model
        "claude-3-opus-20240229": {"input": 15.0, "output": 75.0},   # Legacy opus model
    },
    "openai": {
        # GPT models - per million tokens
        "gpt-4o": {"input": 2.5, "output": 10.0},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    },
}

# Default fallback rates (per million tokens) if model not found
DEFAULT_RATES = {
    "anthropic": {"input": 3.0, "output": 15.0},  # Sonnet-level pricing
    "openai": {"input": 5.0, "output": 15.0},  # GPT-4o pricing
}


def get_model_pricing(provider: str, model_id: str) -> dict[str, float]:
    """
    Get pricing for a specific model.

    Args:
        provider: LLM provider (anthropic, openai)
        model_id: Model identifier

    Returns:
        Dict with 'input' and 'output' rates per million tokens
    """
    provider = provider.lower()

    # Check if provider exists
    if provider not in PRICING_CONFIG:
        logger.warning(f"Unknown provider '{provider}', using default rates")
        return DEFAULT_RATES.get("anthropic", {"input": 3.0, "output": 15.0})

    provider_config = PRICING_CONFIG[provider]

    # Check if model exists for provider
    if model_id not in provider_config:
        available_models = list(provider_config.keys())
        logger.warning(
            f"Unknown model '{model_id}' for provider '{provider}'. "
            f"Available models: {available_models}. Using default rates for {provider}."
        )
        return DEFAULT_RATES.get(provider, {"input": 3.0, "output": 15.0})

    return provider_config[model_id]


def calculate_llm_cost(
    provider: str,
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    batch_processing: bool = False,
) -> float:
    """
    Calculate LLM cost based on token usage and current pricing.

    Args:
        provider: LLM provider (anthropic, openai)
        model_id: Model identifier
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        batch_processing: Whether this is batch processing (50% discount)

    Returns:
        Cost in USD (rounded to 6 decimal places)
    """
    # Validate inputs
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("Token counts cannot be negative")

    if input_tokens > 10_000_000 or output_tokens > 10_000_000:
        logger.warning(f"Very high token count: input={input_tokens}, output={output_tokens}")

    # Get pricing for model
    pricing = get_model_pricing(provider, model_id)

    # Calculate cost (pricing is per million tokens)
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    total_cost = input_cost + output_cost

    # Apply batch discount if applicable
    if batch_processing:
        total_cost *= 0.5  # 50% discount for batch processing

    # Round to 6 decimal places (standard for financial calculations)
    return round(total_cost, 6)


def validate_token_counts(prompt_tokens: int, completion_tokens: int, total_tokens: int) -> bool:
    """
    Validate that token counts are consistent and reasonable.

    Args:
        prompt_tokens: Number of input tokens
        completion_tokens: Number of output tokens
        total_tokens: Total tokens (should equal prompt + completion)

    Returns:
        True if valid, False otherwise
    """
    # Basic validation
    if any(count < 0 for count in [prompt_tokens, completion_tokens, total_tokens]):
        logger.error("Token counts cannot be negative")
        return False

    # Check total equals sum
    if total_tokens != prompt_tokens + completion_tokens:
        logger.error(
            f"Token count mismatch: {total_tokens} != {prompt_tokens} + {completion_tokens}"
        )
        return False

    # Reasonable bounds checking
    max_reasonable_tokens = 1_000_000  # 1M tokens per request seems like a reasonable upper bound
    if any(count > max_reasonable_tokens for count in [prompt_tokens, completion_tokens]):
        logger.warning(
            f"Unusually high token count: prompt={prompt_tokens}, completion={completion_tokens}"
        )
        # Don't reject, just log warning

    return True


def estimate_cost_range(provider: str, model_id: str, estimated_tokens: int) -> dict[str, float]:
    """
    Estimate cost range for a given token count (useful for frontend cost estimation).

    Args:
        provider: LLM provider
        model_id: Model identifier
        estimated_tokens: Estimated total tokens

    Returns:
        Dict with 'min_cost', 'max_cost' based on input/output ratio assumptions
    """
    pricing = get_model_pricing(provider, model_id)

    # Assume different input/output ratios for cost estimation
    # Conservative: 80% input, 20% output (cheaper)
    conservative_input = int(estimated_tokens * 0.8)
    conservative_output = int(estimated_tokens * 0.2)
    min_cost = calculate_llm_cost(provider, model_id, conservative_input, conservative_output)

    # Expensive: 20% input, 80% output (more expensive due to higher output rates)
    expensive_input = int(estimated_tokens * 0.2)
    expensive_output = int(estimated_tokens * 0.8)
    max_cost = calculate_llm_cost(provider, model_id, expensive_input, expensive_output)

    return {"min_cost": min_cost, "max_cost": max_cost, "estimated_tokens": estimated_tokens}


def get_all_supported_models() -> dict[str, list]:
    """Get list of all supported models by provider."""
    return {provider: list(models.keys()) for provider, models in PRICING_CONFIG.items()}


def update_pricing_config(new_config: dict) -> bool:
    """
    Update pricing configuration (admin only operation).

    Args:
        new_config: New pricing configuration

    Returns:
        True if update successful
    """
    global PRICING_CONFIG

    try:
        # Validate new config structure
        for provider, models in new_config.items():
            if not isinstance(models, dict):
                raise ValueError(f"Invalid config for provider {provider}")

            for model_id, pricing in models.items():
                if (
                    not isinstance(pricing, dict)
                    or "input" not in pricing
                    or "output" not in pricing
                ):
                    raise ValueError(f"Invalid pricing for model {model_id}")

                if not isinstance(pricing["input"], (int, float)) or not isinstance(
                    pricing["output"], (int, float)
                ):
                    raise ValueError(f"Invalid pricing values for model {model_id}")

        # Update config
        PRICING_CONFIG.update(new_config)
        logger.info("Pricing configuration updated successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to update pricing configuration: {e}")
        return False


# Environment-based config overrides
def load_pricing_overrides():
    """Load pricing overrides from environment variables (for testing/staging)."""
    override_prefix = "LLM_PRICING_OVERRIDE_"

    for env_var, value in os.environ.items():
        if env_var.startswith(override_prefix):
            try:
                # Parse env var: LLM_PRICING_OVERRIDE_ANTHROPIC_CLAUDE_SONNET_INPUT=2.5
                parts = env_var[len(override_prefix) :].lower().split("_")
                if len(parts) >= 4:
                    provider = parts[0]
                    model = "_".join(parts[1:-1])  # Handle multi-part model names
                    rate_type = parts[-1]  # input or output

                    if provider in PRICING_CONFIG and model in PRICING_CONFIG[provider]:
                        if rate_type in ["input", "output"]:
                            PRICING_CONFIG[provider][model][rate_type] = float(value)
                            logger.info(
                                f"Pricing override: {provider}/{model}/{rate_type} = {value}"
                            )

            except Exception as e:
                logger.warning(f"Invalid pricing override {env_var}: {e}")


# Load overrides on import
load_pricing_overrides()
