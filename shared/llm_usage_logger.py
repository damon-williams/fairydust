# shared/llm_usage_logger.py
"""
Centralized LLM usage logging utility for fairydust services.
Logs usage data to the Apps Service for analytics and cost tracking.
"""

import time
from typing import Optional
from uuid import UUID

import httpx


async def log_llm_usage(
    user_id: UUID,
    app_id: str,
    provider: str,
    model_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    cost_usd: float,
    latency_ms: int,
    prompt_hash: Optional[str] = None,
    finish_reason: Optional[str] = "stop",
    was_fallback: bool = False,
    fallback_reason: Optional[str] = None,
    request_metadata: Optional[dict] = None,
    auth_token: Optional[str] = None,
) -> bool:
    """
    Log LLM usage to Apps Service for analytics and cost tracking.

    Args:
        user_id: User who initiated the request
        app_id: App ID or slug (e.g., 'fairydust-story')
        provider: LLM provider ('anthropic', 'openai')
        model_id: Model used (e.g., 'claude-3-5-sonnet-20241022')
        prompt_tokens: Number of input tokens
        completion_tokens: Number of output tokens
        total_tokens: Total tokens used
        cost_usd: Calculated cost in USD
        latency_ms: Request latency in milliseconds
        prompt_hash: Optional hash of the prompt for deduplication
        finish_reason: Reason generation finished ('stop', 'length', etc.)
        was_fallback: Whether a fallback model was used
        fallback_reason: Reason for fallback if applicable
        request_metadata: Additional metadata about the request
        auth_token: JWT token for service-to-service auth

    Returns:
        bool: True if logging succeeded, False otherwise
    """
    if request_metadata is None:
        request_metadata = {}

    # Prepare the usage log payload
    usage_payload = {
        "user_id": str(user_id),
        "app_id": app_id,
        "provider": provider,
        "model_id": model_id,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost_usd": cost_usd,
        "latency_ms": latency_ms,
        "prompt_hash": prompt_hash,
        "finish_reason": finish_reason,
        "was_fallback": was_fallback,
        "fallback_reason": fallback_reason,
        "request_metadata": request_metadata,
    }

    try:
        # Apps Service URL
        apps_service_url = "https://fairydust-apps-production.up.railway.app"

        headers = {
            "Content-Type": "application/json",
        }

        # Add authorization header if provided
        if auth_token:
            headers["Authorization"] = auth_token

        print(
            f"📊 LLM_USAGE: Logging usage for {app_id} - {model_id} ({total_tokens} tokens, ${cost_usd:.6f})",
            flush=True,
        )

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{apps_service_url}/llm/usage",
                headers=headers,
                json=usage_payload,
            )

            if response.status_code == 201:
                print(f"✅ LLM_USAGE: Successfully logged usage for {app_id}", flush=True)
                return True
            else:
                print(
                    f"⚠️ LLM_USAGE: Failed to log usage - HTTP {response.status_code}: {response.text}",
                    flush=True,
                )
                return False

    except httpx.TimeoutException:
        print(f"⚠️ LLM_USAGE: Timeout logging usage for {app_id}", flush=True)
        return False
    except httpx.ConnectError:
        print(f"⚠️ LLM_USAGE: Connection error logging usage for {app_id}", flush=True)
        return False
    except Exception as e:
        print(f"⚠️ LLM_USAGE: Error logging usage for {app_id}: {str(e)}", flush=True)
        return False


def calculate_prompt_hash(prompt: str) -> str:
    """
    Calculate a hash of the prompt for deduplication and caching analysis.

    Args:
        prompt: The LLM prompt string

    Returns:
        str: SHA-256 hash of the prompt (first 16 characters)
    """
    import hashlib

    # Create SHA-256 hash of the prompt
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    # Return first 16 characters for storage efficiency
    return prompt_hash[:16]


def create_request_metadata(
    action: str,
    parameters: Optional[dict] = None,
    user_context: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict:
    """
    Create standardized request metadata for LLM usage logging.

    Args:
        action: The action being performed (e.g., 'story_generation', 'recipe_creation')
        parameters: Request parameters (genre, complexity, etc.)
        user_context: User personalization context
        session_id: Session ID for tracking

    Returns:
        Dict: Formatted metadata dictionary
    """
    metadata = {
        "action": action,
        "timestamp": time.time(),
    }

    if parameters:
        metadata["parameters"] = parameters

    if user_context:
        metadata["user_context"] = user_context

    if session_id:
        metadata["session_id"] = session_id

    return metadata
