# shared/llm_client.py
"""
Centralized LLM client with retry logic and automatic fallback for fairydust services.
Handles Anthropic and OpenAI providers with robust error handling and monitoring.
"""

import asyncio
import os
import time
from typing import Optional
from uuid import UUID

import httpx

from shared.llm_pricing import calculate_llm_cost


class LLMError(Exception):
    """Base exception for LLM client errors"""

    def __init__(
        self, message: str, provider: str = None, status_code: int = None, retry_after: int = None
    ):
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.retry_after = retry_after


class LLMClient:
    """
    Centralized LLM client with automatic retry logic and provider fallback.

    Handles transient errors (429, 502, 503, 529) with exponential backoff,
    and automatically falls back to secondary providers when primary fails.
    """

    def __init__(self):
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self.openai_key = os.getenv("OPENAI_API_KEY")

        if not self.anthropic_key and not self.openai_key:
            raise ValueError("At least one LLM API key must be configured")

    async def generate_completion(
        self,
        prompt: str,
        app_config: dict,
        user_id: UUID,
        app_id: str,
        action: str,
        request_metadata: Optional[dict] = None,
    ) -> tuple[str, dict]:
        """
        Generate completion with automatic retry and fallback logic.

        Args:
            prompt: The prompt to send to the LLM
            app_config: App configuration including provider, model, and parameters
            user_id: User ID for logging
            app_id: App ID for logging
            action: Action slug for logging
            request_metadata: Additional metadata for logging

        Returns:
            Tuple[str, Dict]: (completion_text, generation_metadata)

        Raises:
            LLMError: When all providers and retries are exhausted
        """
        start_time = time.time()

        # Extract configuration
        primary_provider = app_config.get("primary_provider", "anthropic")
        primary_model = app_config.get("primary_model_id", "claude-3-5-sonnet-20241022")
        parameters = app_config.get("primary_parameters", {})
        fallback_models = app_config.get("fallback_models", [])

        # Build provider attempt list
        providers_to_try = self._build_provider_list(
            primary_provider, primary_model, fallback_models
        )

        last_error = None

        for attempt_num, (provider, model_id) in enumerate(providers_to_try):
            is_fallback = attempt_num > 0

            try:
                print(
                    f"🤖 LLM_CLIENT: Attempt {attempt_num + 1}/{len(providers_to_try)} - {provider}/{model_id}"
                )

                completion, usage_data = await self._make_api_call(
                    provider, model_id, prompt, parameters
                )

                # Calculate metrics
                generation_time_ms = int((time.time() - start_time) * 1000)
                cost_usd = calculate_llm_cost(
                    provider, model_id, usage_data["prompt_tokens"], usage_data["completion_tokens"]
                )

                # Log successful usage
                await self._log_usage(
                    user_id=user_id,
                    app_id=app_id,
                    provider=provider,
                    model_id=model_id,
                    usage_data=usage_data,
                    cost_usd=cost_usd,
                    latency_ms=generation_time_ms,
                    was_fallback=is_fallback,
                    fallback_reason=f"Primary provider failed: {str(last_error)}"[:100]
                    if is_fallback
                    else None,
                    action=action,
                    request_metadata=request_metadata,
                )

                # Success logging now handled by usage logger with more detail

                # Return completion and metadata
                return completion, {
                    "provider": provider,
                    "model_id": model_id,
                    "tokens_used": usage_data,
                    "cost_usd": cost_usd,
                    "generation_time_ms": generation_time_ms,
                    "was_fallback": is_fallback,
                    "attempt_number": attempt_num + 1,
                }

            except LLMError as e:
                last_error = e
                print(f"❌ LLM_CLIENT: {provider}/{model_id} failed: {e}")

                # If this was a retryable error and not the last attempt, continue
                if self._is_retryable_error(e) and attempt_num < len(providers_to_try) - 1:
                    # Wait before next attempt
                    retry_delay = self._calculate_retry_delay(attempt_num, e.retry_after)
                    if retry_delay > 0:
                        print(f"⏳ LLM_CLIENT: Waiting {retry_delay}s before next attempt...")
                        await asyncio.sleep(retry_delay)
                    continue

                # Non-retryable error or last attempt
                if attempt_num == len(providers_to_try) - 1:
                    print(f"💥 LLM_CLIENT: All providers exhausted. Last error: {e}")
                    break

        # All attempts failed
        raise LLMError(f"All LLM providers failed. Last error: {str(last_error)}")

    def _build_provider_list(
        self, primary_provider: str, primary_model: str, fallback_models: list[dict]
    ) -> list[tuple[str, str]]:
        """Build ordered list of (provider, model) pairs to try"""
        providers = [(primary_provider, primary_model)]

        # Add fallback models from configuration
        for fallback in fallback_models:
            provider = fallback.get("provider")
            model = fallback.get("model_id")
            if provider and model and (provider, model) not in providers:
                providers.append((provider, model))

        # Add default fallbacks if not already present
        defaults = [
            ("openai", "gpt-4o"),
            ("anthropic", "claude-3-5-sonnet-20241022"),
            ("openai", "gpt-4o-mini"),
        ]

        for provider, model in defaults:
            if (provider, model) not in providers and self._has_provider_key(provider):
                providers.append((provider, model))

        # Filter to only providers we have keys for
        return [(p, m) for p, m in providers if self._has_provider_key(p)]

    def _has_provider_key(self, provider: str) -> bool:
        """Check if we have an API key for the given provider"""
        if provider == "anthropic":
            return bool(self.anthropic_key)
        elif provider == "openai":
            return bool(self.openai_key)
        return False

    async def _make_api_call(
        self, provider: str, model_id: str, prompt: str, parameters: dict
    ) -> tuple[str, dict]:
        """Make the actual API call to the specified provider"""

        # Extract parameters with defaults
        max_tokens = parameters.get("max_tokens", 1000)
        temperature = parameters.get("temperature", 0.7)
        top_p = parameters.get("top_p", 0.9)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if provider == "anthropic":
                    return await self._call_anthropic(
                        client, model_id, prompt, max_tokens, temperature, top_p
                    )
                elif provider == "openai":
                    return await self._call_openai(
                        client, model_id, prompt, max_tokens, temperature, top_p
                    )
                else:
                    raise LLMError(f"Unsupported provider: {provider}")

        except httpx.TimeoutException:
            raise LLMError(f"Timeout calling {provider} API", provider=provider, status_code=408)
        except httpx.ConnectError:
            raise LLMError(
                f"Connection error to {provider} API", provider=provider, status_code=503
            )

    async def _call_anthropic(
        self,
        client: httpx.AsyncClient,
        model_id: str,
        prompt: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
    ) -> tuple[str, dict]:
        """Make API call to Anthropic"""

        if not self.anthropic_key:
            raise LLMError("Anthropic API key not configured", provider="anthropic")

        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.anthropic_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": model_id,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p,
                "messages": [{"role": "user", "content": prompt}],
            },
        )

        if response.status_code == 200:
            result = response.json()
            # Safely access nested response structure
            try:
                content = result["content"][0]["text"].strip()
            except (KeyError, IndexError, TypeError) as e:
                raise LLMError(f"Invalid Anthropic response structure: {e}", provider="anthropic")

            usage = result.get("usage", {})
            usage_data = {
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            }

            return content, usage_data

        else:
            # Parse error response
            try:
                error_data = response.json()
                error_type = error_data.get("error", {}).get("type", "unknown_error")
                error_message = error_data.get("error", {}).get("message", response.text)
            except (ValueError, KeyError, TypeError):
                error_type = "unknown_error"
                error_message = f"Failed to parse error response: {response.text}"

            # Determine retry_after for rate limiting
            retry_after = None
            if response.status_code == 429:
                try:
                    retry_after = int(response.headers.get("retry-after", 60))
                except (ValueError, TypeError):
                    retry_after = 60  # Default if header is not a valid integer
            elif response.status_code == 529:
                retry_after = 5  # Quick retry for overloaded to avoid frontend timeout

            raise LLMError(
                f"Anthropic API error {response.status_code}: {error_message}",
                provider="anthropic",
                status_code=response.status_code,
                retry_after=retry_after,
            )

    async def _call_openai(
        self,
        client: httpx.AsyncClient,
        model_id: str,
        prompt: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
    ) -> tuple[str, dict]:
        """Make API call to OpenAI"""

        if not self.openai_key:
            raise LLMError("OpenAI API key not configured", provider="openai")

        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.openai_key}",
            },
            json={
                "model": model_id,
                "max_completion_tokens": max_tokens,  # Updated parameter name for newer OpenAI models
                "temperature": temperature,
                "top_p": top_p,
                "messages": [{"role": "user", "content": prompt}],
            },
        )

        if response.status_code == 200:
            result = response.json()
            # Safely access nested response structure
            try:
                content = result["choices"][0]["message"]["content"].strip()
            except (KeyError, IndexError, TypeError) as e:
                raise LLMError(f"Invalid OpenAI response structure: {e}", provider="openai")

            usage = result.get("usage", {})
            usage_data = {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }

            return content, usage_data

        else:
            # Parse error response
            try:
                error_data = response.json()
                error_message = error_data.get("error", {}).get("message", response.text)
            except (ValueError, KeyError, TypeError):
                error_message = f"Failed to parse error response: {response.text}"

            # Determine retry_after for rate limiting
            retry_after = None
            if response.status_code == 429:
                try:
                    retry_after = int(response.headers.get("retry-after", 60))
                except (ValueError, TypeError):
                    retry_after = 60  # Default if header is not a valid integer

            raise LLMError(
                f"OpenAI API error {response.status_code}: {error_message}",
                provider="openai",
                status_code=response.status_code,
                retry_after=retry_after,
            )

    def _is_retryable_error(self, error: LLMError) -> bool:
        """Determine if an error should trigger a retry/fallback"""
        if not error.status_code:
            return True  # Network errors, timeouts

        # Retryable HTTP status codes
        retryable_codes = {
            408,  # Request timeout
            429,  # Rate limit
            500,  # Internal server error
            502,  # Bad gateway
            503,  # Service unavailable
            504,  # Gateway timeout
            529,  # Service overloaded (Anthropic)
        }

        return error.status_code in retryable_codes

    def _calculate_retry_delay(self, attempt_num: int, retry_after: Optional[int] = None) -> float:
        """Calculate delay before next retry using exponential backoff"""
        if retry_after:
            return min(retry_after, 120)  # Respect retry-after but cap at 2 minutes

        # Exponential backoff: 1s, 2s, 4s, 8s, etc.
        base_delay = min(2**attempt_num, 60)  # Cap at 60 seconds

        # Add some jitter to avoid thundering herd
        import random

        jitter = random.uniform(0.1, 0.3) * base_delay

        return base_delay + jitter

    async def _log_usage(
        self,
        user_id: UUID,
        app_id: str,
        provider: str,
        model_id: str,
        usage_data: dict,
        cost_usd: float,
        latency_ms: int,
        was_fallback: bool,
        fallback_reason: Optional[str],
        action: str,
        request_metadata: Optional[dict],
    ):
        """Log LLM usage with fallback information"""
        from shared.llm_usage_logger import create_request_metadata, log_llm_usage

        # Create or update request metadata
        if not request_metadata:
            request_metadata = {}

        if action:
            request_metadata = create_request_metadata(
                action=action,
                parameters=request_metadata.get("parameters", {}),
                user_context=request_metadata.get("user_context"),
                session_id=request_metadata.get("session_id"),
            )

        # Log usage (don't fail if logging fails)
        try:
            await log_llm_usage(
                user_id=user_id,
                app_id=app_id,
                provider=provider,
                model_id=model_id,
                prompt_tokens=usage_data["prompt_tokens"],
                completion_tokens=usage_data["completion_tokens"],
                total_tokens=usage_data["total_tokens"],
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                was_fallback=was_fallback,
                fallback_reason=fallback_reason,
                request_metadata=request_metadata,
            )
        except Exception as e:
            print(f"⚠️ LLM_CLIENT: Failed to log usage: {e}")


# Global instance
llm_client = LLMClient()
