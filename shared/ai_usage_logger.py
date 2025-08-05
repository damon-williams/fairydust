# shared/ai_usage_logger.py
"""
Unified AI usage logging for text, image, and video models.
Tracks usage metrics for analytics and billing purposes.
"""

import hashlib
import json
import logging
from typing import Any, Optional
from uuid import UUID, uuid4

from shared.database import Database

logger = logging.getLogger(__name__)


class AIUsageLogger:
    """Centralized logging for all AI model usage"""

    def __init__(self, db: Database):
        self.db = db

    async def log_text_usage(
        self,
        user_id: UUID,
        app_id: UUID,
        provider: str,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        latency_ms: int,
        prompt_text: str,
        finish_reason: str = "stop",
        was_fallback: bool = False,
        fallback_reason: Optional[str] = None,
        request_metadata: Optional[dict[str, Any]] = None,
    ) -> UUID:
        """
        Log text model (LLM) usage

        Args:
            user_id: User who made the request
            app_id: App that processed the request
            provider: Model provider (anthropic, openai)
            model_id: Specific model identifier
            prompt_tokens: Number of input tokens
            completion_tokens: Number of output tokens
            cost_usd: Actual cost at time of generation (NEVER recalculate)
            latency_ms: Response time in milliseconds
            prompt_text: The actual prompt for hashing
            finish_reason: How the generation finished (stop, length, etc.)
            was_fallback: Whether fallback model was used
            fallback_reason: Why fallback was needed
            request_metadata: Additional context (action, user data, etc.)

        Returns:
            UUID of the created log entry
        """
        usage_id = uuid4()
        total_tokens = prompt_tokens + completion_tokens
        prompt_hash = hashlib.sha256(prompt_text.encode()).hexdigest()

        await self.db.execute(
            """
            INSERT INTO ai_usage_logs (
                id, user_id, app_id, model_type, provider, model_id,
                prompt_tokens, completion_tokens, total_tokens,
                cost_usd, latency_ms, prompt_hash, finish_reason,
                was_fallback, fallback_reason, request_metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16::jsonb)
            """,
            usage_id,
            user_id,
            app_id,
            "text",
            provider,
            model_id,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            cost_usd,
            latency_ms,
            prompt_hash,
            finish_reason,
            was_fallback,
            fallback_reason,
            json.dumps(request_metadata or {}),
        )

        logger.info(
            f"✅ Logged text usage: {provider}/{model_id} - {total_tokens} tokens - ${cost_usd:.6f}"
        )
        return usage_id

    async def log_image_usage(
        self,
        user_id: UUID,
        app_id: UUID,
        provider: str,
        model_id: str,
        images_generated: int,
        image_dimensions: str,
        cost_usd: float,
        latency_ms: int,
        prompt_text: str,
        finish_reason: str = "completed",
        was_fallback: bool = False,
        fallback_reason: Optional[str] = None,
        request_metadata: Optional[dict[str, Any]] = None,
    ) -> UUID:
        """
        Log image model usage

        Args:
            user_id: User who made the request
            app_id: App that processed the request
            provider: Model provider (black-forest-labs, runwayml, etc.)
            model_id: Specific model identifier
            images_generated: Number of images created
            image_dimensions: Image size (e.g., "1024x1024")
            cost_usd: Actual cost at time of generation (NEVER recalculate)
            latency_ms: Response time in milliseconds
            prompt_text: The image generation prompt for hashing
            finish_reason: How the generation finished
            was_fallback: Whether fallback model was used
            fallback_reason: Why fallback was needed
            request_metadata: Additional context (action, style, etc.)

        Returns:
            UUID of the created log entry
        """
        usage_id = uuid4()
        prompt_hash = hashlib.sha256(prompt_text.encode()).hexdigest()

        await self.db.execute(
            """
            INSERT INTO ai_usage_logs (
                id, user_id, app_id, model_type, provider, model_id,
                images_generated, image_dimensions,
                cost_usd, latency_ms, prompt_hash, finish_reason,
                was_fallback, fallback_reason, request_metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15::jsonb)
            """,
            usage_id,
            user_id,
            app_id,
            "image",
            provider,
            model_id,
            images_generated,
            image_dimensions,
            cost_usd,
            latency_ms,
            prompt_hash,
            finish_reason,
            was_fallback,
            fallback_reason,
            json.dumps(request_metadata or {}),
        )

        logger.info(
            f"✅ Logged image usage: {provider}/{model_id} - {images_generated} images - ${cost_usd:.6f}"
        )
        return usage_id

    async def log_video_usage(
        self,
        user_id: UUID,
        app_id: UUID,
        provider: str,
        model_id: str,
        videos_generated: int,
        video_duration_seconds: float,
        video_resolution: str,
        cost_usd: float,
        latency_ms: int,
        prompt_text: str,
        finish_reason: str = "completed",
        was_fallback: bool = False,
        fallback_reason: Optional[str] = None,
        request_metadata: Optional[dict[str, Any]] = None,
    ) -> UUID:
        """
        Log video model usage

        Args:
            user_id: User who made the request
            app_id: App that processed the request
            provider: Model provider (runwayml, etc.)
            model_id: Specific model identifier
            videos_generated: Number of videos created
            video_duration_seconds: Length of video(s) in seconds
            video_resolution: Video quality (e.g., "1080p")
            cost_usd: Actual cost at time of generation (NEVER recalculate)
            latency_ms: Response time in milliseconds
            prompt_text: The video generation prompt for hashing
            finish_reason: How the generation finished
            was_fallback: Whether fallback model was used
            fallback_reason: Why fallback was needed
            request_metadata: Additional context (action, style, etc.)

        Returns:
            UUID of the created log entry
        """
        usage_id = uuid4()
        prompt_hash = hashlib.sha256(prompt_text.encode()).hexdigest()

        await self.db.execute(
            """
            INSERT INTO ai_usage_logs (
                id, user_id, app_id, model_type, provider, model_id,
                videos_generated, video_duration_seconds, video_resolution,
                cost_usd, latency_ms, prompt_hash, finish_reason,
                was_fallback, fallback_reason, request_metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16::jsonb)
            """,
            usage_id,
            user_id,
            app_id,
            "video",
            provider,
            model_id,
            videos_generated,
            video_duration_seconds,
            video_resolution,
            cost_usd,
            latency_ms,
            prompt_hash,
            finish_reason,
            was_fallback,
            fallback_reason,
            json.dumps(request_metadata or {}),
        )

        logger.info(
            f"✅ Logged video usage: {provider}/{model_id} - {videos_generated} videos - ${cost_usd:.6f}"
        )
        return usage_id


async def get_ai_usage_logger(db: Database) -> AIUsageLogger:
    """Factory function to create AIUsageLogger instance"""
    return AIUsageLogger(db)


# Convenience functions for backward compatibility
async def log_llm_usage(
    db: Database,
    user_id: UUID,
    app_id: UUID,
    provider: str,
    model_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float,
    latency_ms: int,
    prompt_text: str,
    finish_reason: str = "stop",
    was_fallback: bool = False,
    fallback_reason: Optional[str] = None,
    request_metadata: Optional[dict[str, Any]] = None,
) -> UUID:
    """Backward compatibility function for LLM usage logging"""
    logger_instance = await get_ai_usage_logger(db)
    return await logger_instance.log_text_usage(
        user_id=user_id,
        app_id=app_id,
        provider=provider,
        model_id=model_id,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        prompt_text=prompt_text,
        finish_reason=finish_reason,
        was_fallback=was_fallback,
        fallback_reason=fallback_reason,
        request_metadata=request_metadata,
    )
