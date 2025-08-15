# shared/llm_pricing.py
"""
Centralized LLM pricing calculator for fairydust platform.
All costs calculated server-side only - never accept costs from client APIs.
Pricing is now configurable through the Admin Portal via system_config table.
"""

import json
import logging
import os
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class LLMProvider(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


# Global cache for pricing configuration
_pricing_cache: Optional[dict] = None
_cache_timestamp: Optional[float] = None
CACHE_TTL = 300  # 5 minutes


# Pricing per million tokens (input/output) for LLMs, per image for image models - Updated 2024
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
        "claude-3-opus-20240229": {"input": 15.0, "output": 75.0},  # Legacy opus model
    },
    "openai": {
        # GPT models - per million tokens
        "gpt-5": {"input": 1.25, "output": 10.0},
        "gpt-5-mini": {"input": 0.25, "output": 2.0},
        "gpt-5-nano": {"input": 0.05, "output": 0.40},
        "gpt-4o": {"input": 2.5, "output": 10.0},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    },
    "image": {
        # Image models - per image generation
        "black-forest-labs/flux-1.1-pro": {"cost": 0.04},
        "black-forest-labs/flux-schnell": {"cost": 0.003},  # $3.00 per 1000 images
        "bytedance/seedream-3": {"cost": 0.008},  # Estimated cost per image
        "runwayml/gen4-image": {"cost": 0.05},
        "runwayml/gen4-image-turbo": {"cost": 0.03},
    },
    "video": {
        # Video models - per video generation
        "bytedance/seedance-1-pro": {
            "480p": {"cost_per_second": 0.03},
            "1080p": {"cost_per_second": 0.15},
        },
        "minimax/video-01": {"cost": 0.50},  # Fixed cost per video
    },
}

# Default fallback rates (per million tokens) if model not found
DEFAULT_RATES = {
    "anthropic": {"input": 3.0, "output": 15.0},  # Sonnet-level pricing
    "openai": {"input": 5.0, "output": 15.0},  # GPT-4o pricing
}


async def load_pricing_from_db():
    """Load pricing configuration from database"""
    global _pricing_cache, _cache_timestamp
    import time

    current_time = time.time()

    # Check cache validity
    if (
        _pricing_cache is not None
        and _cache_timestamp is not None
        and current_time - _cache_timestamp < CACHE_TTL
    ):
        return _pricing_cache

    try:
        # Import here to avoid circular imports
        from shared.database import get_db

        # Create database connection
        async for db in get_db():
            try:
                config_row = await db.fetch_one(
                    "SELECT value FROM system_config WHERE key = 'model_pricing'"
                )

                if config_row and config_row["value"]:
                    pricing_config = json.loads(config_row["value"])

                    # Update cache
                    _pricing_cache = pricing_config
                    _cache_timestamp = current_time

                    logger.info("✅ Loaded pricing configuration from database")
                    return pricing_config
                else:
                    logger.warning("⚠️ No pricing configuration found in database, using fallback")
                    break

            except Exception as e:
                logger.error(f"❌ Failed to load pricing from database: {e}")
                break

    except Exception as e:
        logger.error(f"❌ Database connection failed for pricing: {e}")

    # Fallback to hard-coded pricing if database is unavailable
    logger.warning("🔄 Using fallback pricing configuration")
    return PRICING_CONFIG


def get_pricing_config():
    """Get current pricing configuration (sync version for non-async contexts)"""
    global _pricing_cache

    if _pricing_cache is not None:
        return _pricing_cache

    # Return hard-coded config as fallback for sync contexts
    logger.warning("🔄 Using hard-coded pricing configuration (sync context)")
    return PRICING_CONFIG


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

    # Get current pricing config (uses cache if available)
    pricing_config = get_pricing_config()

    # Check if provider exists
    if provider not in pricing_config:
        logger.warning(f"Unknown provider '{provider}', using default rates")
        return DEFAULT_RATES.get("anthropic", {"input": 3.0, "output": 15.0})

    provider_config = pricing_config[provider]

    # Check if model exists for provider
    if model_id not in provider_config:
        available_models = list(provider_config.keys())
        logger.warning(
            f"Unknown model '{model_id}' for provider '{provider}'. "
            f"Available models: {available_models}. Using default rates for {provider}."
        )
        return DEFAULT_RATES.get(provider, {"input": 3.0, "output": 15.0})

    return provider_config[model_id]


async def get_model_pricing_async(provider: str, model_id: str) -> dict[str, float]:
    """
    Async version of get_model_pricing that loads fresh config from database.

    Args:
        provider: LLM provider (anthropic, openai)
        model_id: Model identifier

    Returns:
        Dict with 'input' and 'output' rates per million tokens
    """
    provider = provider.lower()

    # Load fresh pricing config from database
    pricing_config = await load_pricing_from_db()

    # Check if provider exists
    if provider not in pricing_config:
        logger.warning(f"Unknown provider '{provider}', using default rates")
        return DEFAULT_RATES.get("anthropic", {"input": 3.0, "output": 15.0})

    provider_config = pricing_config[provider]

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

    ⚠️  IMPORTANT: This function uses CURRENT pricing configuration.
    ⚠️  NEVER use this to recalculate historical usage costs.
    ⚠️  Historical LLM usage logs should preserve their original cost_usd values.

    Args:
        provider: LLM provider (anthropic, openai)
        model_id: Model identifier
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        batch_processing: Whether this is batch processing (50% discount)

    Returns:
        Cost in USD (rounded to 6 decimal places) using CURRENT pricing
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


def calculate_image_cost(model_id: str, image_count: int = 1) -> float:
    """
    Calculate image generation cost based on model and image count.

    ⚠️  IMPORTANT: This function uses CURRENT pricing configuration.
    ⚠️  NEVER use this to recalculate historical image generation costs.
    ⚠️  Historical image usage logs should preserve their original cost values.

    Args:
        model_id: Image model identifier (e.g., "black-forest-labs/flux-1.1-pro")
        image_count: Number of images to generate

    Returns:
        Cost in USD (rounded to 6 decimal places) using CURRENT pricing
    """
    if image_count <= 0:
        raise ValueError("Image count must be positive")

    # Get pricing for image model
    if "image" not in PRICING_CONFIG or model_id not in PRICING_CONFIG["image"]:
        logger.warning(f"Unknown image model '{model_id}', using default cost of $0.025")
        return round(0.025 * image_count, 6)

    model_cost = PRICING_CONFIG["image"][model_id]["cost"]
    total_cost = model_cost * image_count

    return round(total_cost, 6)


def get_image_model_pricing(model_id: str) -> float:
    """
    Get per-image cost for a specific image model.

    Args:
        model_id: Image model identifier

    Returns:
        Cost per image in USD
    """
    pricing_config = get_pricing_config()

    if "image" not in pricing_config or model_id not in pricing_config["image"]:
        logger.warning(f"Unknown image model '{model_id}', using default cost")
        return 0.025

    return pricing_config["image"][model_id]["cost"]


async def get_image_model_pricing_async(model_id: str) -> float:
    """
    Async version of get_image_model_pricing that loads fresh config from database.

    Args:
        model_id: Image model identifier

    Returns:
        Cost per image in USD
    """
    pricing_config = await load_pricing_from_db()

    if "image" not in pricing_config or model_id not in pricing_config["image"]:
        logger.warning(f"Unknown image model '{model_id}', using default cost")
        return 0.025

    return pricing_config["image"][model_id]["cost"]


def get_video_model_pricing(model_id: str, resolution: str = "1080p") -> dict:
    """
    Get pricing information for a specific video model.

    Args:
        model_id: Video model identifier
        resolution: Video resolution for models that support it

    Returns:
        Dict with pricing information
    """
    pricing_config = get_pricing_config()

    if "video" not in pricing_config or model_id not in pricing_config["video"]:
        logger.warning(f"Unknown video model '{model_id}', using default pricing")
        return {"cost": 0.10, "type": "fixed"}

    model_pricing = pricing_config["video"][model_id]

    if model_id == "bytedance/seedance-1-pro":
        if resolution not in model_pricing:
            resolution = "1080p"
        return {
            "cost_per_second": model_pricing[resolution]["cost_per_second"],
            "type": "per_second",
            "resolution": resolution,
        }
    elif model_id == "minimax/video-01":
        return {"cost": model_pricing["cost"], "type": "fixed"}
    else:
        return model_pricing


async def get_video_model_pricing_async(model_id: str, resolution: str = "1080p") -> dict:
    """
    Async version of get_video_model_pricing that loads fresh config from database.

    Args:
        model_id: Video model identifier
        resolution: Video resolution for models that support it

    Returns:
        Dict with pricing information
    """
    pricing_config = await load_pricing_from_db()

    if "video" not in pricing_config or model_id not in pricing_config["video"]:
        logger.warning(f"Unknown video model '{model_id}', using default pricing")
        return {"cost": 0.10, "type": "fixed"}

    model_pricing = pricing_config["video"][model_id]

    if model_id == "bytedance/seedance-1-pro":
        if resolution not in model_pricing:
            resolution = "1080p"
        return {
            "cost_per_second": model_pricing[resolution]["cost_per_second"],
            "type": "per_second",
            "resolution": resolution,
        }
    elif model_id == "minimax/video-01":
        return {"cost": model_pricing["cost"], "type": "fixed"}
    else:
        return model_pricing


def calculate_video_cost(
    model_id: str, video_count: int = 1, duration_seconds: float = 1.0, resolution: str = "1080p"
) -> float:
    """
    Calculate video generation cost based on model, video count, duration, and resolution.

    ⚠️  IMPORTANT: This function uses CURRENT pricing configuration.
    ⚠️  NEVER use this to recalculate historical video generation costs.
    ⚠️  Historical video usage logs should preserve their original cost values.

    Args:
        model_id: Video model identifier (e.g., "bytedance/seedance-1-pro")
        video_count: Number of videos to generate
        duration_seconds: Duration of each video in seconds
        resolution: Video resolution ("480p" or "1080p")

    Returns:
        Cost in USD (rounded to 6 decimal places) using CURRENT pricing
    """
    if video_count <= 0:
        raise ValueError("Video count must be positive")
    if duration_seconds <= 0:
        raise ValueError("Video duration must be positive")

    pricing_config = get_pricing_config()

    if "video" not in pricing_config or model_id not in pricing_config["video"]:
        logger.warning(f"Unknown video model '{model_id}', using default cost of $0.10 per video")
        return round(0.10 * video_count, 6)

    model_pricing = pricing_config["video"][model_id]

    # Handle SeeDance-1-Pro duration and resolution-based pricing
    if model_id == "bytedance/seedance-1-pro":
        if resolution not in model_pricing:
            logger.warning(f"Unknown resolution '{resolution}' for {model_id}, using 1080p pricing")
            resolution = "1080p"

        cost_per_second = model_pricing[resolution]["cost_per_second"]
        total_cost = cost_per_second * duration_seconds * video_count

    # Handle MiniMax Video-01 fixed pricing
    elif model_id == "minimax/video-01":
        model_cost = model_pricing["cost"]
        total_cost = model_cost * video_count

    # Handle unknown model structure
    else:
        if "cost" in model_pricing:
            total_cost = model_pricing["cost"] * video_count
        else:
            logger.warning(f"Unknown pricing structure for '{model_id}', using default cost")
            return round(0.10 * video_count, 6)

    return round(total_cost, 6)


def get_all_supported_models() -> dict[str, list]:
    """Get list of all supported models by provider."""
    pricing_config = get_pricing_config()
    return {provider: list(models.keys()) for provider, models in pricing_config.items()}


def get_model_type_from_id(model_id: str) -> str:
    """
    Determine model type from model ID.

    Args:
        model_id: Model identifier

    Returns:
        Model type: 'text', 'image', or 'video'
    """
    pricing_config = get_pricing_config()

    # Check if it's an image model
    if model_id in pricing_config.get("image", {}):
        return "image"

    # Check if it's a video model
    if model_id in pricing_config.get("video", {}):
        return "video"

    # Check if it's a text model (in anthropic or openai)
    for provider in ["anthropic", "openai"]:
        if model_id in pricing_config.get(provider, {}):
            return "text"

    # Default to text for unknown models
    return "text"


def get_all_models_with_type() -> list[dict]:
    """
    Get all supported models with their types and pricing info.

    Returns:
        List of dicts with model info including type, provider, model_id, and pricing
    """
    pricing_config = get_pricing_config()
    models = []

    # Add text models
    for provider in ["anthropic", "openai"]:
        if provider in pricing_config:
            for model_id, pricing in pricing_config[provider].items():
                models.append(
                    {
                        "provider": provider,
                        "model_id": model_id,
                        "model_type": "text",
                        "pricing": pricing,
                    }
                )

    # Add image models
    if "image" in pricing_config:
        for model_id, pricing in pricing_config["image"].items():
            # Extract provider from model_id (e.g., "black-forest-labs/flux-1.1-pro")
            provider = model_id.split("/")[0] if "/" in model_id else "unknown"
            models.append(
                {
                    "provider": provider,
                    "model_id": model_id,
                    "model_type": "image",
                    "pricing": pricing,
                }
            )

    # Add video models
    if "video" in pricing_config:
        for model_id, pricing in pricing_config["video"].items():
            # Extract provider from model_id
            provider = model_id.split("/")[0] if "/" in model_id else "unknown"
            models.append(
                {
                    "provider": provider,
                    "model_id": model_id,
                    "model_type": "video",
                    "pricing": pricing,
                }
            )

    return models


def invalidate_pricing_cache():
    """Invalidate the pricing configuration cache"""
    global _pricing_cache, _cache_timestamp
    _pricing_cache = None
    _cache_timestamp = None
    logger.info("🔄 Pricing cache invalidated")


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
