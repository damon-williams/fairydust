# services/content/story_routes.py
import asyncio
import json
import os
import re
import uuid
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

# Service URL configuration
environment = os.getenv("ENVIRONMENT", "staging")
base_url_suffix = "production" if environment == "production" else "staging"
identity_url = f"https://fairydust-identity-{base_url_suffix}.up.railway.app"

# Content service no longer manages DUST - all DUST handling is external
import httpx
from langsmith import traceable
from models import (
    StoriesListResponse,
    StoryCharacter,
    StoryConfigResponse,
    StoryDeleteResponse,
    StoryErrorResponse,
    StoryFavoriteRequest,
    StoryFavoriteResponse,
    StoryGenerationRequest,
    StoryGenerationResponseNew,
    StoryImageBatchResponse,
    StoryImageStatus,
    StoryImageStatusResponse,
    StoryLength,
    TargetAudience,
    TokenUsage,
    UserStoryNew,
)
from story_image_generator import story_image_generator
from story_image_service import story_image_service

from shared.auth_middleware import TokenData, get_current_user
from shared.database import Database, get_db
from shared.json_utils import parse_jsonb_field
from shared.llm_client import LLMError, llm_client
from shared.llm_usage_logger import calculate_prompt_hash, create_request_metadata

router = APIRouter()

# Constants - Reading time targets for story generation

READING_TIME_WORD_TARGETS = {
    StoryLength.QUICK: (400, 600),  # ~2-3 min reading time
    StoryLength.MEDIUM: (1000, 1400),  # ~5-7 min reading time
    StoryLength.LONG: (1600, 2400),  # ~8-12 min reading time
}

STORY_RATE_LIMIT = 10  # Max 10 stories per hour per user


@router.post("/apps/story/generate")
@traceable(run_type="chain", name="story-generation")
async def generate_story(
    request: StoryGenerationRequest,
    http_request: Request,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """
    Generate a new story using LLM and automatically save it to user's collection.
    """
    # Add metadata for LangSmith tracing
    metadata = {
        "user_id": str(request.user_id),
        "story_length": request.story_length.value,
        "target_audience": request.target_audience.value,
        "character_count": len(request.characters),
        "include_images": request.include_images,
        "has_custom_prompt": bool(request.custom_prompt),
        "has_selected_people": bool(request.selected_people),
    }

    print(f"📖 STORY: Starting generation for user {request.user_id}", flush=True)
    print(
        f"📂 STORY: Length: {request.story_length}, Audience: {request.target_audience}", flush=True
    )
    print(f"🌙 STORY: Bedtime story: {request.is_bedtime_story}", flush=True)

    # Verify user can only generate stories for themselves
    if current_user.user_id != str(request.user_id):
        print(
            f"🚨 STORY: User {current_user.user_id} attempted to generate story for different user {request.user_id}",
            flush=True,
        )
        return StoryErrorResponse(error="Can only generate stories for yourself")

    try:
        # Extract Authorization header for service-to-service calls
        auth_token = http_request.headers.get("authorization", "")
        if not auth_token:
            return StoryErrorResponse(error="Authorization header required")

        # Check rate limiting
        rate_limit_exceeded = await _check_rate_limit(db, request.user_id)
        if rate_limit_exceeded:
            return StoryErrorResponse(
                error=f"Rate limit exceeded. Maximum {STORY_RATE_LIMIT} stories per hour."
            )

        # Get user context for personalization
        user_context = await _get_user_context(db, request.user_id)
        print("👤 STORY: Retrieved user context", flush=True)

        # Characters are now fully resolved by frontend - no processing needed
        print(f"🎭 STORY: Received {len(request.characters)} fully resolved characters:")
        for char in request.characters:
            has_photo = "✅" if char.photo_url else "❌"
            print(f"   - {char.name} ({char.relationship}) - Photo: {has_photo}")
        
        # Count characters with photos for logging
        characters_with_photos = [c for c in request.characters if c.photo_url]
        print(f"📸 STORY: {len(characters_with_photos)} characters have photos for image generation")
        
        # Use request directly since characters are pre-resolved
        updated_request = request

        # Generate story using LLM
        (
            story_content,
            title,
            word_count,
            estimated_reading_time,
            model_used,
            tokens_used,
            cost,
            latency_ms,
            provider_used,
        ) = await _generate_story_llm(
            request=updated_request,  # Use merged characters
            user_context=user_context,
            db=db,
        )

        if not story_content:
            return StoryErrorResponse(error="Failed to generate story. Please try again.")

        print(f"🤖 STORY: Generated story: {title}", flush=True)
        # LLM usage logging is now handled by the centralized client

        # Save story to database using merged characters
        story_id = await _save_story(
            db=db,
            user_id=request.user_id,
            title=title,
            content=story_content,
            story_length=updated_request.story_length,
            target_audience=updated_request.target_audience,
            word_count=word_count,
            characters=merged_characters,  # Save merged characters (includes My People with photos)
            session_id=updated_request.session_id,
            model_used=model_used,
            tokens_used=tokens_used,
            cost=cost,
            custom_prompt=updated_request.custom_prompt,
        )

        print(f"✅ STORY: Generated story for user {request.user_id}", flush=True)

        # Handle image generation if requested
        final_content = story_content
        image_ids = []
        has_images = False

        if request.include_images:
            print(f"🎨 STORY: Processing images for story {story_id}", flush=True)
            print(
                f"🎨 STORY: Story length: {len(story_content)} chars, expected {updated_request.story_length.value}",
                flush=True,
            )
            try:
                # Extract story metadata for better image generation
                story_metadata = _extract_story_metadata(story_content, updated_request.target_audience)
                print(f"📊 STORY: Extracted metadata - Theme: {story_metadata['theme']}, Genre: {story_metadata['genre']}")
                
                # If no characters were provided, extract them from the story
                if not updated_request.characters:
                    extracted_characters = _extract_characters_from_story(story_content)
                    print(f"🎭 STORY: Extracted {len(extracted_characters)} characters from story: {[c.name for c in extracted_characters]}")
                    characters_for_images = extracted_characters
                else:
                    characters_for_images = updated_request.characters
                
                # Extract scenes for image generation using characters
                scenes = story_image_service.extract_image_scenes(
                    story_content, updated_request.story_length, characters_for_images
                )

                # Insert image markers into story content
                final_content = story_image_service.insert_image_markers(story_content, scenes)
                image_ids = [scene["image_id"] for scene in scenes]
                has_images = True

                # Update story in database with image markers and metadata
                await _update_story_with_images(db, story_id, final_content, image_ids, has_images)

                # Start background image generation (don't await - let it run async)
                # Now merged_characters includes photo URLs from My People!
                asyncio.create_task(
                    story_image_generator.generate_story_images_background(
                        story_id=str(story_id),
                        user_id=str(request.user_id),
                        scenes=scenes,
                        characters=characters_for_images,  # Use characters (merged or extracted)
                        target_audience=updated_request.target_audience,
                        db=db,
                        full_story_content=story_content,
                        story_theme=story_metadata['theme'],
                        story_genre=story_metadata['genre'],
                        story_context=story_metadata['context'],
                    )
                )

                print(
                    f"🚀 STORY: Started background image generation for {len(scenes)} images",
                    flush=True,
                )

            except Exception as e:
                print(f"❌ STORY: Failed to process images: {str(e)}", flush=True)
                # Continue without images rather than failing the whole request
                has_images = False
                image_ids = []

        # Build response
        story = UserStoryNew(
            id=story_id,
            title=title,
            content=final_content,
            story_length=request.story_length,
            target_audience=request.target_audience,
            word_count=word_count,
            estimated_reading_time=estimated_reading_time,
            created_at=datetime.utcnow(),
            is_favorited=False,
            metadata={
                "characters": [char.dict() for char in request.characters],
                "custom_prompt": request.custom_prompt,
            },
            has_images=has_images,
            images_complete=False,  # Images are generating in background
            image_ids=image_ids if has_images else None,
        )

        return StoryGenerationResponseNew(
            story=story,
            model_used=model_used,
            tokens_used=TokenUsage(
                prompt=tokens_used.get("prompt", 0),
                completion=tokens_used.get("completion", 0),
                total=tokens_used.get("total", 0),
            ),
            cost=cost,
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ STORY: Unexpected error: {str(e)}", flush=True)
        print(f"❌ STORY: Error type: {type(e).__name__}", flush=True)
        return StoryErrorResponse(error="Internal server error during story generation")


@router.get("/users/{user_id}/stories")
async def get_user_stories(
    user_id: uuid.UUID,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
    limit: int = Query(50, ge=1, le=100, description="Number of results to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    story_length: Optional[StoryLength] = Query(None, description="Filter by story length"),
    target_audience: Optional[TargetAudience] = Query(
        None, description="Filter by target audience"
    ),
    favorites_only: bool = Query(False, description="Return only favorited stories"),
    search: Optional[str] = Query(None, description="Search in story title and content"),
):
    """
    Retrieve all saved stories for a user, sorted by favorites first, then creation date descending.
    """
    print(f"📋 STORY: Getting stories for user {user_id}", flush=True)

    # Verify user can only access their own stories
    if current_user.user_id != str(user_id):
        print(
            f"🚨 STORY: User {current_user.user_id} attempted to access stories for different user {user_id}",
            flush=True,
        )
        return StoryErrorResponse(error="Can only access your own stories")

    try:
        # Build query with filters
        base_query = """
            SELECT id, title, content, story_length, target_audience,
                   word_count, is_favorited, created_at, metadata,
                   has_images, images_complete, image_data, story_summary
            FROM user_stories
            WHERE user_id = $1
        """
        params = [user_id]
        param_count = 1

        if story_length:
            param_count += 1
            base_query += f" AND story_length = ${param_count}"
            params.append(story_length.value)

        if target_audience:
            param_count += 1
            base_query += f" AND target_audience = ${param_count}"
            params.append(target_audience.value)

        if favorites_only:
            base_query += " AND is_favorited = TRUE"

        if search:
            param_count += 1
            base_query += f" AND (title ILIKE ${param_count} OR content ILIKE ${param_count})"
            search_pattern = f"%{search}%"
            params.append(search_pattern)

        # Order by favorites first, then creation date descending
        base_query += " ORDER BY is_favorited DESC, created_at DESC"

        # Add pagination
        param_count += 1
        base_query += f" LIMIT ${param_count}"
        params.append(limit)

        param_count += 1
        base_query += f" OFFSET ${param_count}"
        params.append(offset)

        # Execute query
        rows = await db.fetch_all(base_query, *params)

        # Get total counts
        count_query = """
            SELECT
                COUNT(*) as total_count,
                COUNT(*) FILTER (WHERE is_favorited = TRUE) as favorites_count
            FROM user_stories
            WHERE user_id = $1
        """
        count_params = [user_id]

        if story_length:
            param_idx = len(count_params) + 1
            count_query += f" AND story_length = ${param_idx}"
            count_params.append(story_length.value)

        if target_audience:
            param_idx = len(count_params) + 1
            count_query += f" AND target_audience = ${param_idx}"
            count_params.append(target_audience.value)

        if search:
            param_idx = len(count_params) + 1
            count_query += f" AND (title ILIKE ${param_idx} OR content ILIKE ${param_idx})"
            count_params.append(search_pattern)

        count_result = await db.fetch_one(count_query, *count_params)
        total_count = count_result["total_count"] if count_result else 0
        favorites_count = count_result["favorites_count"] if count_result else 0

        # Build response
        stories = []
        for row in rows:
            estimated_reading_time = _calculate_reading_time(row["word_count"] or 0)

            # Parse image data
            image_data = parse_jsonb_field(row["image_data"], {}, "image_data") or {}
            image_ids = image_data.get("image_ids", []) if row["has_images"] else []

            story = UserStoryNew(
                id=row["id"],
                title=row["title"],
                content=row["content"],
                story_length=StoryLength(row["story_length"]),
                target_audience=TargetAudience(row["target_audience"] or "kids"),
                word_count=row["word_count"] or 0,
                estimated_reading_time=estimated_reading_time,
                created_at=row["created_at"],
                is_favorited=row["is_favorited"],
                metadata=parse_jsonb_field(row["metadata"]) or {},
                has_images=row["has_images"] or False,
                images_complete=row["images_complete"] or False,
                image_ids=image_ids if image_ids else None,
            )
            stories.append(story)

        print(f"✅ STORY: Returning {len(stories)} stories", flush=True)

        return StoriesListResponse(
            stories=stories,
            total_count=total_count,
            favorites_count=favorites_count,
        )

    except Exception as e:
        print(f"❌ STORY: Error getting stories: {str(e)}", flush=True)
        return StoryErrorResponse(error="Failed to retrieve stories")


@router.post("/users/{user_id}/stories/{story_id}/favorite")
async def toggle_story_favorite(
    user_id: uuid.UUID,
    story_id: uuid.UUID,
    request: StoryFavoriteRequest,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """
    Toggle the favorite status of a saved story.
    """
    print(
        f"⭐ STORY: Toggling favorite for story {story_id} to {request.is_favorited}",
        flush=True,
    )

    # Verify user can only modify their own stories
    if current_user.user_id != str(user_id):
        print(
            f"🚨 STORY: User {current_user.user_id} attempted to modify story for different user {user_id}",
            flush=True,
        )
        return StoryErrorResponse(error="Can only modify your own stories")

    try:
        # Update favorite status
        update_query = """
            UPDATE user_stories
            SET is_favorited = $1, updated_at = CURRENT_TIMESTAMP
            WHERE id = $2 AND user_id = $3
            RETURNING id, title, content, story_length, target_audience,
                      word_count, is_favorited, created_at, metadata
        """

        result = await db.fetch_one(update_query, request.is_favorited, story_id, user_id)

        if not result:
            return StoryErrorResponse(error="Story not found", story_id=story_id)

        estimated_reading_time = _calculate_reading_time(result["word_count"] or 0)
        story = UserStoryNew(
            id=result["id"],
            title=result["title"],
            content=result["content"],
            story_length=StoryLength(result["story_length"]),
            target_audience=TargetAudience(result["target_audience"] or "kids"),
            word_count=result["word_count"] or 0,
            estimated_reading_time=estimated_reading_time,
            created_at=result["created_at"],
            is_favorited=result["is_favorited"],
            metadata=parse_jsonb_field(result["metadata"]) or {},
        )

        print(f"✅ STORY: Updated favorite status for story {story_id}", flush=True)

        return StoryFavoriteResponse(story=story)

    except Exception as e:
        print(f"❌ STORY: Error updating favorite: {str(e)}", flush=True)
        return StoryErrorResponse(error="Failed to update favorite status")


@router.delete("/users/{user_id}/stories/{story_id}")
async def delete_story(
    user_id: uuid.UUID,
    story_id: uuid.UUID,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """
    Remove a saved story from user's collection.
    """
    print(f"🗑️ STORY: Deleting story {story_id}", flush=True)

    # Verify user can only delete their own stories
    if current_user.user_id != str(user_id):
        print(
            f"🚨 STORY: User {current_user.user_id} attempted to delete story for different user {user_id}",
            flush=True,
        )
        return StoryErrorResponse(error="Can only delete your own stories")

    try:
        # Delete story
        delete_query = """
            DELETE FROM user_stories
            WHERE id = $1 AND user_id = $2
        """

        result = await db.execute(delete_query, story_id, user_id)

        # Check if any rows were affected
        if "DELETE 0" in result:
            return StoryErrorResponse(error="Story not found", story_id=story_id)

        print(f"✅ STORY: Deleted story {story_id}", flush=True)

        return StoryDeleteResponse()

    except Exception as e:
        print(f"❌ STORY: Error deleting story: {str(e)}", flush=True)
        return StoryErrorResponse(error="Failed to delete story")


@router.get("/apps/story/config")
async def get_story_config():
    """
    Get available story lengths (reading times), and DUST costs.
    """
    print("⚙️ STORY: Getting story configuration", flush=True)

    try:
        config = {
            "story_lengths": [
                {
                    "label": "Quick Read",
                    "value": "quick",
                    "reading_time": "2-3 minutes",
                    "words": "400-600",
                },
                {
                    "label": "Medium Story",
                    "value": "medium",
                    "reading_time": "5-7 minutes",
                    "words": "1000-1400",
                },
                {
                    "label": "Long Story",
                    "value": "long",
                    "reading_time": "8-12 minutes",
                    "words": "1600-2400",
                },
            ],
            "target_audiences": [
                {
                    "label": "Toddler",
                    "value": "toddler",
                    "age_range": "2-4 years",
                    "description": "Very simple language, familiar objects and concepts",
                },
                {
                    "label": "Preschool",
                    "value": "preschool",
                    "age_range": "4-6 years",
                    "description": "Simple vocabulary with gentle lessons about friendship and kindness",
                },
                {
                    "label": "Early Elementary",
                    "value": "early_elementary",
                    "age_range": "6-9 years",
                    "description": "Age-appropriate adventures with themes of courage and teamwork",
                },
                {
                    "label": "Late Elementary",
                    "value": "late_elementary",
                    "age_range": "9-12 years",
                    "description": "More sophisticated stories with character growth and mild challenges",
                },
                {
                    "label": "Teen",
                    "value": "teen",
                    "age_range": "13+ years",
                    "description": "Complex themes of identity, relationships, and personal growth",
                },
            ],
            "character_relationships": [
                "protagonist",
                "daughter",
                "son",
                "spouse",
                "parent",
                "sibling",
                "friend",
                "pet",
                "grandparent",
                "cousin",
                "teacher",
                "neighbor",
            ],
            "common_traits": [
                "brave",
                "curious",
                "kind",
                "funny",
                "creative",
                "smart",
                "athletic",
                "musical",
                "artistic",
                "adventurous",
                "gentle",
                "energetic",
            ],
        }

        print("✅ STORY: Returning story configuration", flush=True)
        return StoryConfigResponse(config=config)

    except Exception as e:
        print(f"❌ STORY: Error getting config: {str(e)}", flush=True)
        return StoryErrorResponse(error="Failed to retrieve story configuration")


# Helper functions
async def _get_app_id(db: Database) -> str:
    """Get the UUID for the fairydust-story app"""
    result = await db.fetch_one("SELECT id FROM apps WHERE slug = $1", "fairydust-story")
    if not result:
        raise HTTPException(
            status_code=500,
            detail="fairydust-story app not found in database. Please create the app first.",
        )
    return str(result["id"])


async def _check_rate_limit(db: Database, user_id: uuid.UUID) -> bool:
    """Check if user has exceeded rate limit for story generation"""
    try:
        # Count generations in the last hour
        query = """
            SELECT COUNT(*) as generation_count
            FROM user_stories
            WHERE user_id = $1
            AND created_at > NOW() - INTERVAL '1 hour'
        """

        result = await db.fetch_one(query, user_id)
        generation_count = result["generation_count"] if result else 0

        if generation_count >= STORY_RATE_LIMIT:
            print(
                f"⚠️ STORY_RATE_LIMIT: User {user_id} exceeded rate limit: {generation_count}/{STORY_RATE_LIMIT}",
                flush=True,
            )
            return True

        print(
            f"✅ STORY_RATE_LIMIT: User {user_id} within limit: {generation_count}/{STORY_RATE_LIMIT}",
            flush=True,
        )
        return False

    except Exception as e:
        print(f"❌ STORY_RATE_LIMIT: Error checking rate limit: {str(e)}", flush=True)
        # Default to allowing if we can't check (fail open)
        return False


async def _get_user_context(db: Database, user_id: uuid.UUID) -> str:
    """Get user context for personalization (interests only, NOT people)"""
    try:
        # Get user profile data (interests only)
        profile_query = """
            SELECT field_name, field_value
            FROM user_profile_data
            WHERE user_id = $1
        """

        profile_rows = await db.fetch_all(profile_query, user_id)

        # Build context string - ONLY include interests, NOT people
        # People should only be included when explicitly requested as Characters
        context_parts = []

        if profile_rows:
            interests = []
            for row in profile_rows:
                if row["field_name"] == "interests":
                    field_value = row["field_value"]
                    if isinstance(field_value, str):
                        interests.extend(field_value.split(","))
                    elif isinstance(field_value, list):
                        interests.extend(field_value)

            if interests:
                context_parts.append(f"Interests: {', '.join(interests[:5])}")

        # REMOVED: Automatic inclusion of "My People" data
        # My People should only be factored in when explicitly requested as Characters

        return "; ".join(context_parts) if context_parts else "general user"

    except Exception as e:
        print(f"⚠️ STORY_CONTEXT: Error getting user context: {str(e)}", flush=True)
        return "general user"


async def _get_llm_model_config() -> dict:
    """Get LLM configuration for story app (with caching)"""
    from shared.app_config_cache import get_app_config_cache
    from shared.database import get_db

    app_slug = "fairydust-story"

    # First, get the app UUID from the slug
    db = await get_db()
    app_result = await db.fetch_one("SELECT id FROM apps WHERE slug = $1", app_slug)

    if not app_result:
        print(f"❌ STORY_CONFIG: App with slug '{app_slug}' not found in database", flush=True)
        # Return default config if app not found
        return {
            "primary_provider": "anthropic",
            "primary_model_id": "claude-3-5-sonnet-20241022",
            "primary_parameters": {"temperature": 0.8, "max_tokens": 3000, "top_p": 0.9},
        }

    app_id = str(app_result["id"])
    print(f"🔍 STORY_CONFIG: Resolved {app_slug} to UUID {app_id}", flush=True)

    # Try to get from cache first
    cache = await get_app_config_cache()
    cached_config = await cache.get_model_config(app_id)

    if cached_config:
        print("✅ STORY_CONFIG: Found cached config", flush=True)
        print(f"✅ STORY_CONFIG: Provider: {cached_config.get('primary_provider')}", flush=True)
        print(f"✅ STORY_CONFIG: Model: {cached_config.get('primary_model_id')}", flush=True)
        print(f"✅ STORY_CONFIG: Full cached config: {cached_config}", flush=True)

        config = {
            "primary_provider": cached_config.get("primary_provider", "anthropic"),
            "primary_model_id": cached_config.get("primary_model_id", "claude-3-5-sonnet-20241022"),
            "primary_parameters": cached_config.get(
                "primary_parameters", {"temperature": 0.8, "max_tokens": 3000, "top_p": 0.9}
            ),
        }

        print(f"✅ STORY_CONFIG: Returning config: {config}", flush=True)
        return config

    # Cache miss - check database directly
    print("⚠️ STORY_CONFIG: Cache miss, checking database directly", flush=True)

    try:
        # Don't need to get_db again, we already have it
        db_config = await db.fetch_one("SELECT * FROM app_model_configs WHERE app_id = $1", app_id)

        if db_config:
            print("📊 STORY_CONFIG: Found database config", flush=True)
            print(f"📊 STORY_CONFIG: DB Provider: {db_config['primary_provider']}", flush=True)
            print(f"📊 STORY_CONFIG: DB Model: {db_config['primary_model_id']}", flush=True)

            # Parse and cache the database config
            from shared.json_utils import parse_model_config_field

            parsed_config = {
                "primary_provider": db_config["primary_provider"],
                "primary_model_id": db_config["primary_model_id"],
                "primary_parameters": parse_model_config_field(
                    dict(db_config), "primary_parameters"
                )
                or {"temperature": 0.8, "max_tokens": 3000, "top_p": 0.9},
            }

            # Cache the database config
            await cache.set_model_config(app_id, parsed_config)
            print(f"✅ STORY_CONFIG: Cached database config: {parsed_config}", flush=True)

            return parsed_config

    except Exception as e:
        print(f"❌ STORY_CONFIG: Database error: {e}", flush=True)

    # Fallback to default config
    print("🔄 STORY_CONFIG: Using default config (no cache, no database)", flush=True)
    default_config = {
        "primary_provider": "anthropic",
        "primary_model_id": "claude-3-5-sonnet-20241022",
        "primary_parameters": {"temperature": 0.8, "max_tokens": 3000, "top_p": 0.9},
    }

    # Cache the default config for future requests
    await cache.set_model_config(app_id, default_config)
    print(f"✅ STORY_CONFIG: Cached default config: {default_config}", flush=True)

    return default_config


@traceable(run_type="llm", name="theme-variety-analysis")
async def _get_recent_themes_guidance(db: Database, user_id: uuid.UUID) -> str:
    """Get AI-powered guidance to avoid repeating recent story themes using story summaries"""
    try:
        # Get last 4 stories from this user with their summaries
        recent_stories = await db.fetch_all(
            """
            SELECT title, story_summary, target_audience, created_at
            FROM user_stories
            WHERE user_id = $1 AND story_summary IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 4
            """,
            user_id,
        )

        if not recent_stories or len(recent_stories) < 2:
            return "ENSURE VARIETY: Create something fresh and engaging."

        print(
            f"🔍 STORY_THEMES: Analyzing {len(recent_stories)} recent stories for theme variety",
            flush=True,
        )

        # Prepare story summaries for AI analysis
        story_summaries = []
        for i, story in enumerate(recent_stories):
            days_ago = i  # 0 = most recent, 1 = yesterday, etc.
            summary_entry = f"Story {i+1} ({days_ago} stories ago): '{story['title']}' - {story['story_summary']}"
            story_summaries.append(summary_entry)

        summaries_text = "\n".join(story_summaries)

        # Use AI to analyze themes and provide variety guidance
        analysis_prompt = f"""Analyze these recent user stories and identify patterns or repeated themes that should be avoided in the next story:

{summaries_text}

Based on this analysis, provide specific guidance for generating a new story that avoids repetition. Focus on:
1. Different character types/relationships
2. New settings or environments
3. Fresh plot themes or conflicts
4. Varied emotional tones

Provide guidance in this format:
"AVOID REPETITION: [specific themes to avoid]. CREATE INSTEAD: [suggestions for fresh elements]."

If stories are sufficiently varied, respond with:
"ENSURE VARIETY: Stories show good diversity, continue with creative freedom."

Response:"""

        # Get AI analysis using fast model
        app_config = {
            "primary_provider": "anthropic",
            "primary_model_id": "claude-3-5-haiku-20241022",
            "primary_parameters": {"temperature": 0.4, "max_tokens": 150, "top_p": 0.9},
        }

        content, metadata = await llm_client.generate_completion(
            prompt=analysis_prompt,
            app_config=app_config,
            user_id=user_id,
            app_id="fairydust-story",
            action="theme_variety_analysis",
            request_metadata={"purpose": "theme_variety_analysis"},
        )

        guidance = content.strip() if content else ""

        # Clean up response
        if guidance and len(guidance) > 20:
            # Remove any extra formatting
            guidance = guidance.replace('"', "").strip()
            print(f"🎯 STORY_THEMES: AI guidance: {guidance[:100]}...", flush=True)
            return guidance
        else:
            # Fallback if AI analysis fails
            print("⚠️ STORY_THEMES: AI analysis failed, using fallback", flush=True)
            return "ENSURE VARIETY: Create something fresh with new characters and settings."

    except Exception as e:
        print(f"⚠️ STORY_THEMES: Error in AI theme analysis: {e}", flush=True)
        return "ENSURE VARIETY: Create something fresh and different."


def _calculate_reading_time(word_count: int) -> str:
    """Calculate estimated reading time based on word count"""
    # Average reading speed: 200 words per minute
    minutes = max(1, round(word_count / 200))
    if minutes == 1:
        return "1 minute"
    elif minutes <= 5:
        return f"{minutes} minutes"
    else:
        return f"{minutes} minutes"


@traceable(run_type="tool", name="story-prompt-builder")
async def _build_story_prompt(
    request: StoryGenerationRequest, user_context: str, db: Database
) -> str:
    """Build the LLM prompt for story generation"""
    min_words, max_words = READING_TIME_WORD_TARGETS[request.story_length]
    target_words = (min_words + max_words) // 2

    # Convert story length to readable format
    length_descriptions = {
        StoryLength.QUICK: "2-3 minute read (~500 words)",
        StoryLength.MEDIUM: "5-7 minute read (~1200 words)",
        StoryLength.LONG: "8-12 minute read (~2000 words)",
    }

    # Build character descriptions
    character_descriptions = []
    if request.characters:
        print(f"🎭 STORY_PROMPT: Building prompt with {len(request.characters)} characters:")
        for char in request.characters:
            print(f"   - {char.name} ({char.relationship})")
            # Handle pets vs people differently
            if char.entry_type == "pet":
                desc = f"- {char.name} (pet"
                if char.species:
                    desc += f", {char.species}"
                if char.birth_date:
                    # Calculate age from birth date
                    from datetime import date

                    birth = date.fromisoformat(char.birth_date)
                    age = (date.today() - birth).days // 365
                    desc += f", {age} years old"
                desc += f", relationship to family: {char.relationship})"
            else:
                # Handle people (original logic)
                if char.relationship and char.relationship.lower() in ["yourself", "protagonist"]:
                    # Special handling for the protagonist
                    desc = f"- {char.name} (the main character/protagonist - this is the story's narrator)"
                else:
                    desc = f"- {char.name} ({char.relationship}"
                    if char.birth_date:
                        # Calculate age from birth date
                        from datetime import date

                        birth = date.fromisoformat(char.birth_date)
                        age = (date.today() - birth).days // 365
                        desc += f", {age} years old"
                    desc += ")"

            if char.traits:
                desc += f", traits: {', '.join(char.traits)}"
            character_descriptions.append(desc)

    character_text = (
        f"Characters to include:\n{chr(10).join(character_descriptions)}"
        if character_descriptions
        else "No specific characters required - create original characters as needed."
    )

    # Create varied, unpredictable prompt with audience-specific guidance
    audience_guidance = {
        TargetAudience.TODDLER: "toddlers (ages 2-4). Use very simple language, repetitive phrases, basic concepts like colors and shapes. Focus on familiar objects, animals, and simple emotions. Keep sentences short.",
        TargetAudience.PRESCHOOL: "preschoolers (ages 4-6). Use simple vocabulary with some new words. Focus on friendship, family, basic problem-solving, and discovery. Include gentle lessons about sharing, kindness, and curiosity.",
        TargetAudience.EARLY_ELEMENTARY: "early elementary children (ages 6-9). Use age-appropriate vocabulary with opportunities to learn new words. Focus on adventure, friendship, school experiences, and overcoming small challenges. Include themes of courage, teamwork, and learning.",
        TargetAudience.LATE_ELEMENTARY: "late elementary children (ages 9-12). Use more sophisticated vocabulary and complex sentence structures. Explore themes of friendship, identity, responsibility, and problem-solving. Include mild challenges, mystery elements, and character growth.",
        TargetAudience.TEEN: "teenagers (ages 13+). Use mature language and complex themes. Explore identity, relationships, coming-of-age challenges, and personal growth. Include realistic situations and emotional depth.",
    }

    # Add bedtime story guidance if applicable
    bedtime_guidance = ""
    if request.is_bedtime_story:
        if request.target_audience in [TargetAudience.TODDLER, TargetAudience.PRESCHOOL]:
            bedtime_guidance = " This is a BEDTIME STORY for young children - create a very calm, soothing narrative with gentle, familiar themes. Use soft, rhythmic language with repetitive, comforting phrases. Focus on peaceful bedtime routines, cozy settings, and reassuring endings. Avoid any excitement, conflict, or stimulating elements."
        else:
            bedtime_guidance = " This is a BEDTIME STORY - create a calm, soothing narrative with gentle themes. Avoid exciting action or scary elements. Focus on peaceful, comforting scenarios that help wind down for sleep. Use soft, rhythmic language and end on a tranquil, reassuring note."

    # Add randomness seed to prevent repetitive patterns
    import random

    # Generate variety prompts to break patterns
    variety_seeds = [
        "Create something completely different from typical children's stories.",
        "Surprise readers with an unexpected adventure.",
        "Tell a story that breaks conventional patterns.",
        "Focus on an unusual character or situation.",
        "Explore a creative setting or scenario.",
        "Use an inventive storytelling approach.",
        "Create a story with unexpected elements.",
        "Tell a tale that stands out from the ordinary.",
    ]

    # Add creativity boosters to avoid repetitive themes
    creativity_boosters = [
        "AVOID geometric shapes as main characters unless specifically requested.",
        "AVOID color-based character names (Red Circle, Blue Square, etc.) unless in character list.",
        "Focus on realistic characters, animals, or fantasy beings with personalities.",
        "Create characters with distinct names, backgrounds, and motivations.",
        "Avoid abstract or educational concepts as primary story elements.",
    ]

    selected_variety = random.choice(variety_seeds)
    selected_creativity = random.choice(creativity_boosters)

    # Use AI analysis of recent story summaries to avoid repetitive themes
    recent_themes_guidance = await _get_recent_themes_guidance(db, request.user_id)

    print(f"🎲 STORY_VARIETY: Applied variety seed: {selected_variety}", flush=True)
    print(f"🎨 STORY_CREATIVITY: Applied creativity booster: {selected_creativity}", flush=True)
    if recent_themes_guidance and "AVOID REPETITION" in recent_themes_guidance:
        print(f"🚫 STORY_REPETITION: {recent_themes_guidance}", flush=True)

    prompt = f"""You are a master storyteller with infinite creativity. {selected_variety} Create a truly unique and surprising story for {audience_guidance[request.target_audience]}{bedtime_guidance} The story should take about {length_descriptions[request.story_length]} to read.

IMPORTANT: {selected_creativity}

{recent_themes_guidance}

{character_text}"""
    
    # Add protagonist instructions if "yourself" character is present
    has_protagonist = any(char.relationship and char.relationship.lower() in ["yourself", "protagonist"] for char in request.characters) if request.characters else False
    if has_protagonist:
        prompt += "\n\nIMPORTANT: The story should be told from a third-person perspective, but the protagonist character listed above must be actively involved in the story's events, not just observing. Make them central to the action and adventure."

    if request.custom_prompt:
        prompt += f"\nSpecial request: {request.custom_prompt}"

    # Only add personalization context if no specific characters are provided
    # This avoids confusion between character list and people context
    if user_context != "general user" and not request.characters:
        prompt += f"\nPersonalization context: {user_context}"

    # Add different creative requirements based on bedtime story flag
    if request.is_bedtime_story:
        prompt += f"""

BEDTIME STORY CREATIVE REQUIREMENTS:
- Target word count: {target_words} words (for {length_descriptions[request.story_length]})
- Audience: {request.target_audience.value}
- CALMING NARRATIVE: Create gentle, predictable story patterns that soothe rather than surprise
- PEACEFUL THEMES: Focus on comfort, safety, love, and tranquility
- SIMPLE STRUCTURE: Use clear, straightforward storytelling without complex twists or excitement
- GENRE SELECTION: Choose calming genres like gentle fantasy, nature stories, family tales, or peaceful adventures
- SOOTHING SETTINGS: Use cozy, familiar, or naturally peaceful environments (bedrooms, gardens, quiet forests, starlit skies) - NEVER use laundromats
- GENTLE LANGUAGE: Use soft, rhythmic prose that flows smoothly and calmly
- COMFORTING ENDINGS: Conclude with reassurance, safety, and peaceful resolution
- OUTPUT ONLY THE STORY: Do not include any analysis, commentary, or explanations about the story"""
    else:
        prompt += f"""

CREATIVE REQUIREMENTS:
- Target word count: {target_words} words (for {length_descriptions[request.story_length]})
- Audience: {request.target_audience.value}
- BREAK THE MOLD: Avoid predictable story patterns, clichés, and formulaic plots
- SURPRISE THE READER: Include unexpected twists, unusual perspectives, or creative narrative devices
- VARY YOUR APPROACH: Choose from different storytelling styles randomly:
  * First person, second person, or third person narration
  * Multiple perspectives or unreliable narrator
  * Experimental formats (diary entries, text messages, news reports, etc.)
  * Time jumps, flashbacks, or non-linear storytelling
  * Stories within stories or meta-fiction elements

GENRE VARIETY (pick unexpectedly):
- Mix genres creatively (sci-fi comedy, fantasy mystery, historical thriller, etc.)
- Try unusual combinations: slice-of-life with magical realism, workplace drama with supernatural elements
- Consider: adventure, mystery, comedy, sci-fi, fantasy, slice-of-life, historical fiction, magical realism, psychological thriller, coming-of-age, workplace drama, family saga, etc.

SETTING CREATIVITY:
- Avoid overused settings like "magical kingdoms", "haunted houses", or "laundromats"
- Be specific and unusual: underwater research station, food truck at a music festival, retirement home game night, artist's studio, bookbinding workshop, lighthouse, observatory, etc.
- Use settings that serve the story and create natural conflict or intrigue
- AVOID laundromats as story settings entirely

PLOT INNOVATION:
- Start in the middle of action or at an unusual moment
- Subvert reader expectations about character roles and story direction
- Create organic conflicts that arise from character relationships and setting
- End with satisfaction but avoid overly neat resolutions

LANGUAGE AND STYLE:
- Match tone to your chosen genre and approach
- Use vivid, specific details rather than generic descriptions
- Include natural dialogue that reveals character
- Vary sentence structure and pacing for engagement

CHARACTER GUIDANCE:
- For human characters: Develop their personalities, motivations, and relationships naturally
- For pet characters: Portray them authentically with species-appropriate behaviors while allowing for story magic
- Pets can be central characters with agency, not just companions
- Consider the unique perspective pets might have on situations
- Balance realistic animal behavior with the narrative needs of your story

CRITICAL OUTPUT REQUIREMENTS:
- Output ONLY the story title and story content
- Do NOT include any meta-commentary, analysis, or explanations about the story
- Do NOT explain why the story is age-appropriate or educational
- Do NOT include notes about language choices, themes, or writing techniques
- Do NOT add any text in brackets like "[This story uses...]"
- The story should speak for itself without explanation

Format the story with:
TITLE: [Creative, intriguing title]

[Story content with rich details, natural dialogue, and compelling narrative]

Remember: Your goal is to create something memorable and unique that readers haven't seen before. Be bold, creative, and surprising while staying appropriate for the audience. OUTPUT ONLY THE STORY - NO META-COMMENTARY OR ANALYSIS."""

    return prompt


def _count_words(text: str) -> int:
    """Count words in text"""
    return len(re.findall(r"\b\w+\b", text))


def _extract_title_and_content(generated_text: str) -> tuple[str, str]:
    """Extract title and content from generated text, removing any meta-commentary"""
    lines = generated_text.strip().split("\n")

    # Look for TITLE: prefix
    if lines[0].startswith("TITLE: "):
        title = lines[0].replace("TITLE: ", "").strip()
        content = "\n".join(lines[1:]).strip()
    else:
        # Use first line as title if no TITLE: prefix
        title = lines[0].strip()
        content = "\n".join(lines[1:]).strip() if len(lines) > 1 else generated_text

    # Clean up title formatting - remove markdown and common formatting issues
    title = _clean_title_formatting(title)

    # Remove any meta-commentary or analysis from the content
    content = _remove_meta_commentary(content)

    return title, content


def _clean_title_formatting(title: str) -> str:
    """Clean up title formatting to remove markdown and unwanted formatting"""
    # Remove markdown bold formatting
    title = re.sub(r"\*\*(.*?)\*\*", r"\1", title)

    # Remove markdown italic formatting
    title = re.sub(r"\*(.*?)\*", r"\1", title)

    # Remove any remaining TITLE: prefix that might be embedded
    title = re.sub(r"^.*?TITLE:\s*", "", title, flags=re.IGNORECASE)

    # Remove leading/trailing quotes
    title = title.strip("\"'")

    # Remove extra whitespace
    title = re.sub(r"\s+", " ", title).strip()

    return title


def _remove_meta_commentary(content: str) -> str:
    """Remove meta-commentary and analysis from story content"""

    original_length = len(content)

    # Remove content in brackets that looks like meta-commentary
    # Examples: "[This story uses simple language...]", "[The narrative explores...]"
    content = re.sub(r"\[This story[^\]]*\]", "", content, flags=re.IGNORECASE)
    content = re.sub(r"\[The story[^\]]*\]", "", content, flags=re.IGNORECASE)
    content = re.sub(r"\[The narrative[^\]]*\]", "", content, flags=re.IGNORECASE)
    content = re.sub(r"\[Note:[^\]]*\]", "", content, flags=re.IGNORECASE)
    content = re.sub(r"\[This.*?appropriate[^\]]*\]", "", content, flags=re.IGNORECASE)
    content = re.sub(r"\[.*?age[- ]appropriate[^\]]*\]", "", content, flags=re.IGNORECASE)
    content = re.sub(r"\[.*?educational[^\]]*\]", "", content, flags=re.IGNORECASE)

    # Remove standalone analytical paragraphs at the end
    # Look for patterns like paragraphs that start with analysis keywords
    analysis_patterns = [
        r"\n\n.*?This story.*?appropriate.*?\.",
        r"\n\n.*?The narrative.*?language.*?\.",
        r"\n\n.*?This tale.*?teaches.*?\.",
        r"\n\n.*?The story.*?demonstrates.*?\.",
        r"\n\n.*?This adventure.*?explores.*?\.",
        r"\n\n.*?repetitive.*?language.*?\.",
        r"\n\n.*?simple.*?vocabulary.*?\.",
        r"\n\n.*?age[- ]appropriate.*?\.",
        r"\n\n.*?educational.*?value.*?\.",
        r"\n\n.*?teaches.*?lesson.*?\.",
    ]

    for pattern in analysis_patterns:
        content = re.sub(pattern, "", content, flags=re.IGNORECASE | re.DOTALL)

    # Remove any trailing analytical sentences that might not be caught above
    # Look for sentences that contain analysis keywords at the end of the content
    analytical_sentence_endings = [
        r"\.?\s*This story uses.*?\.$",
        r"\.?\s*The narrative.*?\.$",
        r"\.?\s*This tale.*?\.$",
        r"\.?\s*The story.*?appropriate.*?\.$",
        r"\.?\s*.*?repetitive language.*?\.$",
        r"\.?\s*.*?simple vocabulary.*?\.$",
    ]

    for pattern in analytical_sentence_endings:
        content = re.sub(pattern, ".", content, flags=re.IGNORECASE | re.DOTALL)

    # Clean up extra whitespace and empty lines, but preserve paragraph structure
    content = re.sub(r"\n\s*\n\s*\n+", "\n\n", content)  # Remove triple+ newlines, keep double
    content = re.sub(r"[ \t]+", " ", content)  # Normalize horizontal whitespace only
    content = re.sub(r"\n[ \t]+", "\n", content)  # Remove spaces at start of lines

    cleaned_length = len(content.strip())

    # Log if content was cleaned
    if cleaned_length < original_length:
        removed_chars = original_length - cleaned_length
        print(
            f"🧹 STORY_CLEAN: Removed {removed_chars} characters of meta-commentary from story",
            flush=True,
        )

    return content.strip()


async def _fetch_my_people_data(
    user_id: UUID, selected_people: list[UUID], auth_token: str
) -> list[dict]:
    """Fetch My People data from Identity Service including photo URLs"""
    if not selected_people:
        return []

    try:
        print(f"📸 STORY_PEOPLE: Fetching My People data for {len(selected_people)} people")

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{identity_url}/users/{user_id}/people",
                headers={"Authorization": auth_token},
                timeout=10.0,
            )

            if response.status_code == 200:
                all_people = response.json().get("people", [])

                # Filter to selected people and extract relevant data
                selected_people_data = []
                for person in all_people:
                    if person and person.get("id") in [str(pid) for pid in selected_people]:
                        # Extract basic info including new pet fields
                        entry_type = person.get("entry_type", "person")
                        person_data = {
                            "id": person.get("id"),
                            "name": person.get("name", ""),
                            "relationship": person.get("relationship", "friend"),
                            "birth_date": person.get("birth_date"),
                            "photo_url": person.get(
                                "photo_url"
                            ),  # This is the key field for images!
                            "entry_type": entry_type,
                            "species": person.get("species"),  # For pets: breed/animal type
                        }

                        # Extract traits from profile data or personality_description field
                        traits = []

                        # First check the direct personality_description field (simpler)
                        if person.get("personality_description"):
                            # Split personality description into trait-like chunks
                            desc_traits = [
                                t.strip() for t in person.get("personality_description").split(",")
                            ]
                            traits.extend(desc_traits[:5])  # Limit from description

                        # Also check profile_data for additional traits
                        for profile_item in person.get("profile_data", []):
                            if profile_item.get("category") == "personality":
                                personality_data = profile_item.get("field_value", {})
                                if isinstance(personality_data, dict):
                                    traits.extend(personality_data.get("traits", []))

                        # For pets, add species-appropriate default traits if none provided
                        if entry_type == "pet" and not traits and person_data["species"]:
                            species = person_data["species"].lower()
                            if "dog" in species:
                                traits = ["loyal", "playful", "friendly"]
                            elif "cat" in species:
                                traits = ["independent", "curious", "graceful"]
                            elif any(pet in species for pet in ["bird", "parrot"]):
                                traits = ["intelligent", "talkative", "colorful"]
                            elif any(pet in species for pet in ["fish", "goldfish"]):
                                traits = ["peaceful", "graceful", "calm"]
                            else:
                                traits = ["beloved", "special", "cherished"]
                            print(f"🐾 STORY_PEOPLE: Added default traits for {species}: {traits}")

                        person_data["traits"] = traits[:10]  # Limit to 10 traits
                        selected_people_data.append(person_data)

                print(
                    f"📸 STORY_PEOPLE: Successfully fetched {len(selected_people_data)} My People entries"
                )
                for person in selected_people_data:
                    has_photo = "✅" if person.get("photo_url") else "❌"
                    print(f"   {person['name']} ({person['relationship']}) - Photo: {has_photo}")

                return selected_people_data
            else:
                print(f"❌ STORY_PEOPLE: Identity service returned {response.status_code}")
                return []

    except Exception as e:
        print(f"❌ STORY_PEOPLE: Error fetching My People data: {e}")
        return []


async def _fetch_user_name(user_id: UUID, auth_token: str) -> Optional[str]:
    """Fetch user's first name from identity service"""
    try:
        # auth_token might already include "Bearer " prefix
        if not auth_token.startswith("Bearer "):
            auth_token = f"Bearer {auth_token}"
            
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": auth_token}
            print(f"🔍 STORY: Fetching user from {identity_url}/users/me")
            response = await client.get(
                f"{identity_url}/users/me",
                headers=headers
            )
            
            if response.status_code == 200:
                user_data = response.json()
                first_name = user_data.get("first_name")
                if first_name:
                    print(f"👤 STORY: Fetched user name: {first_name}")
                    return first_name
                else:
                    print("⚠️ STORY: User has no first name set")
            else:
                print(f"❌ STORY: Failed to fetch user data: {response.status_code}")
    except Exception as e:
        print(f"❌ STORY: Error fetching user name: {e}")
    
    return None


async def _merge_characters_and_people(
    custom_characters: list[StoryCharacter], my_people_data: list[dict]
) -> list[StoryCharacter]:
    """Merge custom characters with My People entries into unified character list"""

    merged_characters = []

    # Add custom characters (no photos)
    for char in custom_characters:
        merged_characters.append(char)

    # Convert My People entries to StoryCharacter format
    for person in my_people_data:
        story_char = StoryCharacter(
            name=person["name"],
            relationship=person["relationship"],
            birth_date=person.get("birth_date"),
            traits=person.get("traits", []),
            photo_url=person.get("photo_url"),  # Include photo URL!
            person_id=UUID(person["id"]) if person.get("id") else None,
            entry_type=person.get("entry_type", "person"),  # Include entry type
            species=person.get("species"),  # Include pet species info
        )
        merged_characters.append(story_char)

    print(
        f"🎭 STORY_CHARACTERS: Merged {len(custom_characters)} custom + {len(my_people_data)} My People = {len(merged_characters)} total characters"
    )

    # Log photo availability
    characters_with_photos = [c for c in merged_characters if c.photo_url]
    print(
        f"📸 STORY_CHARACTERS: {len(characters_with_photos)} characters have photos for image generation"
    )

    return merged_characters


def _extract_characters_from_story(story_content: str) -> list[StoryCharacter]:
    """Extract character names and species from story content using pattern matching"""
    
    characters = []
    import re
    
    # Enhanced patterns to capture names with species/descriptors
    enhanced_patterns = [
        # Pattern: "Name Species" (e.g., "Rosie Rabbit", "Mr. Whiskers the cat")
        r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:the\s+)?(?:rabbit|cat|dog|bear|squirrel|raccoon|fox|wolf|bird|duck|owl)',
        # Pattern: "Species Name" (e.g., "cat postal worker", "rabbit watched")  
        r'(?:rabbit|cat|dog|bear|squirrel|raccoon|fox|wolf|bird|duck|owl)\s+(?:postal\s+worker\s+|worker\s+|character\s+)?([A-Z][a-z]+)',
        # Pattern: Character descriptions with species
        r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)[^.]*?(?:rabbit|cat|dog|bear|squirrel|raccoon|fox|wolf|bird|duck|owl)',
    ]
    
    # Standard dialogue patterns for any character names
    dialogue_patterns = [
        r'"[^"]*?"\s*,?\s*([A-Z][a-z]+)\s+(?:said|asked|replied|whispered|shouted|exclaimed|called|cried)',
        r'([A-Z][a-z]+)\s+(?:said|asked|replied|whispered|shouted|exclaimed|called|cried)\s*,?\s*"',
        r'"[^"]*?"\s*(?:said|asked)\s*([A-Z][a-z]+)',
    ]
    
    # Action patterns for character behavior
    action_patterns = [
        r'([A-Z][a-z]+)\s+(?:walked|ran|jumped|smiled|looked|turned|went|came|saw|found|held|took|hopped|balanced|twirled)',
        r'([A-Z][a-z]+)\s+(?:was|were|had|could|would|should)',
        r'([A-Z][a-z]+)(?:\'s|\'re|\'ll|\'d)',
    ]
    
    character_info = {}  # name -> {count, species, traits}
    
    # Extract characters with species information
    for pattern in enhanced_patterns:
        matches = re.findall(pattern, story_content, re.IGNORECASE)
        for match in matches:
            name = match.strip().title()
            if len(name) > 1 and name.isalpha():
                if name not in character_info:
                    character_info[name] = {"count": 0, "species": None, "traits": []}
                character_info[name]["count"] += 3  # Higher weight for species mentions
                
                # Detect species from surrounding context
                name_context = story_content[max(0, story_content.find(match)-50):story_content.find(match)+100].lower()
                species_map = {
                    "rabbit": "rabbit", "cat": "cat", "dog": "dog", "bear": "bear",
                    "squirrel": "squirrel", "raccoon": "raccoon", "fox": "fox", 
                    "wolf": "wolf", "bird": "bird", "duck": "duck", "owl": "owl"
                }
                for species_key, species_value in species_map.items():
                    if species_key in name_context:
                        character_info[name]["species"] = species_value
                        break
    
    # Extract from dialogue patterns
    for pattern in dialogue_patterns:
        matches = re.findall(pattern, story_content, re.IGNORECASE)
        for match in matches:
            name = match.strip().title()
            if len(name) > 1 and name.isalpha():
                if name not in character_info:
                    character_info[name] = {"count": 0, "species": None, "traits": []}
                character_info[name]["count"] += 2
    
    # Extract from action patterns
    for pattern in action_patterns:
        matches = re.findall(pattern, story_content)
        for match in matches:
            name = match.strip()
            if len(name) > 1 and name.isalpha():
                if name not in character_info:
                    character_info[name] = {"count": 0, "species": None, "traits": []}
                character_info[name]["count"] += 1
    
    # Extract specific character names from compound names (like "Mr. Whiskers")
    compound_names = re.findall(r'(Mr\.\s+[A-Z][a-z]+|Mrs\.\s+[A-Z][a-z]+|Miss\s+[A-Z][a-z]+|[A-Z][a-z]+\s+[A-Z][a-z]+)', story_content)
    for compound in compound_names:
        name = compound.strip()
        if name not in character_info:
            character_info[name] = {"count": 0, "species": None, "traits": []}
        character_info[name]["count"] += 2
        
        # Check for species context around compound names
        name_context = story_content[max(0, story_content.find(compound)-100):story_content.find(compound)+100].lower()
        species_map = {
            "rabbit": "rabbit", "cat": "cat", "dog": "dog", "bear": "bear",
            "squirrel": "squirrel", "raccoon": "raccoon", "fox": "fox", 
            "wolf": "wolf", "bird": "bird", "duck": "duck", "owl": "owl"
        }
        for species_key, species_value in species_map.items():
            if species_key in name_context:
                character_info[name]["species"] = species_value
                break
    
    # Filter common words
    common_words = {
        'The', 'They', 'There', 'That', 'This', 'Then', 'When', 'Where', 'What', 'Who',
        'He', 'She', 'It', 'We', 'You', 'I', 'A', 'An', 'And', 'Or', 'But', 'So',
        'Little', 'Big', 'One', 'Two', 'New', 'Old', 'Good', 'Bad', 'Right', 'Left'
    }
    
    # Create StoryCharacter objects
    for name, info in character_info.items():
        if info["count"] >= 2 and name not in common_words and len(name) >= 2:
            # Extract basic traits from story context
            traits = []
            name_lower = name.lower()
            story_lower = story_content.lower()
            
            # Find descriptive words near character name
            name_pattern = rf'\b{re.escape(name_lower)}\b'
            for match in re.finditer(name_pattern, story_lower):
                start = max(0, match.start() - 100)
                end = min(len(story_lower), match.end() + 100)
                context = story_lower[start:end]
                
                # Common trait patterns
                if "curious" in context or "wondered" in context:
                    traits.append("curious")
                if "brave" in context or "courage" in context:
                    traits.append("brave")
                if "thoughtful" in context or "idea" in context:
                    traits.append("thoughtful")
                if "older" in context:
                    traits.append("older sibling")
                if "younger" in context or "little" in context:
                    traits.append("younger")
                if "excited" in context or "exclaimed" in context:
                    traits.append("excitable")
                if "helpful" in context or "help" in context:
                    traits.append("helpful")
                if "creative" in context or "idea" in context:
                    traits.append("creative")
            
            # Remove duplicates and limit traits
            traits = list(set(traits))[:3]
            
            # Determine entry_type based on species
            entry_type = "person"
            if info["species"]:
                entry_type = "pet" if info["species"] in ["cat", "dog"] else "character"
            
            character = StoryCharacter(
                name=name,
                relationship="story character",
                traits=traits if traits else ["friendly"],  # Default trait if none found
                entry_type=entry_type,
                species=info["species"]
            )
            characters.append(character)
    
    # Sort by mention count and limit to top 4
    characters = sorted(characters, key=lambda c: character_info[c.name]["count"], reverse=True)[:4]
    
    return characters


def _extract_story_metadata(story_content: str, target_audience: TargetAudience) -> dict:
    """Extract theme and genre from story content using keyword analysis"""
    
    story_lower = story_content.lower()
    
    # Theme detection based on story content
    theme_keywords = {
        "friendship": ["friend", "together", "help", "share", "care", "support"],
        "adventure": ["journey", "explore", "discover", "adventure", "quest", "travel"],
        "family": ["family", "mother", "father", "parent", "grandma", "grandpa", "home"],
        "learning": ["learn", "school", "teach", "practice", "grow", "understand"],
        "courage": ["brave", "courage", "fear", "overcome", "strong", "bold"],
        "creativity": ["create", "imagine", "dream", "art", "build", "invent"],
        "kindness": ["kind", "help", "gentle", "love", "care", "sweet"],
        "nature": ["garden", "forest", "animals", "plants", "outdoors", "environment"],
        "magic": ["magic", "magical", "spell", "wizard", "fairy", "enchanted"],
        "mystery": ["mystery", "secret", "solve", "investigate", "clue", "detective"]
    }
    
    # Genre detection based on content and setting
    genre_keywords = {
        "fantasy": ["magic", "dragon", "fairy", "wizard", "castle", "enchanted", "potion"],
        "adventure": ["journey", "quest", "explore", "treasure", "danger", "rescue"],
        "mystery": ["mystery", "clue", "solve", "detective", "secret", "investigate"],
        "family": ["family", "home", "everyday", "routine", "sibling", "parent"],
        "nature": ["forest", "garden", "animals", "outdoors", "camping", "wildlife"],
        "school": ["school", "classroom", "teacher", "student", "homework", "learn"],
        "friendship": ["friends", "together", "play", "share", "teammate", "buddy"],
        "bedtime": ["sleep", "dream", "night", "cozy", "peaceful", "quiet"]
    }
    
    # Score themes
    theme_scores = {}
    for theme, keywords in theme_keywords.items():
        score = sum(1 for keyword in keywords if keyword in story_lower)
        if score > 0:
            theme_scores[theme] = score
    
    # Score genres
    genre_scores = {}
    for genre, keywords in genre_keywords.items():
        score = sum(1 for keyword in keywords if keyword in story_lower)
        if score > 0:
            genre_scores[genre] = score
    
    # Determine primary theme and genre
    primary_theme = max(theme_scores, key=theme_scores.get) if theme_scores else "adventure"
    primary_genre = max(genre_scores, key=genre_scores.get) if genre_scores else "family"
    
    # Add audience-based context
    audience_context = {
        TargetAudience.TODDLER: "Simple, gentle story for very young children",
        TargetAudience.PRESCHOOL: "Educational story with basic concepts",
        TargetAudience.EARLY_ELEMENTARY: "Adventure story with learning elements",
        TargetAudience.LATE_ELEMENTARY: "Complex story with character development",
        TargetAudience.TEEN: "Young adult story with mature themes"
    }
    
    return {
        "theme": primary_theme,
        "genre": primary_genre,
        "context": audience_context.get(target_audience, "Children's story")
    }


@traceable(run_type="llm", name="story-llm-generation")
async def _generate_story_llm(
    request: StoryGenerationRequest,
    user_context: str,
    db: Database,
) -> tuple[Optional[str], str, int, str, str, dict, float, int, str]:
    """Generate story using centralized LLM client - returns (content, title, word_count, reading_time, model_id, tokens, cost, latency_ms, provider)"""
    try:
        # Get LLM model configuration from database/cache
        model_config = await _get_llm_model_config()

        # Adjust max_tokens based on story length to prevent truncation
        base_max_tokens = model_config.get("primary_parameters", {}).get("max_tokens", 2000)
        story_length_multipliers = {
            StoryLength.QUICK: 1.0,  # ~500 words = ~667 tokens
            StoryLength.MEDIUM: 1.8,  # ~1200 words = ~1600 tokens
            StoryLength.LONG: 2.5,  # ~2000 words = ~2667 tokens
        }

        max_tokens = int(base_max_tokens * story_length_multipliers.get(request.story_length, 1.0))
        max_tokens = max(1000, min(max_tokens, 8000))  # Ensure reasonable bounds

        # Update parameters with adjusted max_tokens
        adjusted_config = model_config.copy()
        if "primary_parameters" not in adjusted_config:
            adjusted_config["primary_parameters"] = {}
        adjusted_config["primary_parameters"]["max_tokens"] = max_tokens

        print(
            f"🔧 STORY_LLM: Adjusted max_tokens to {max_tokens} for {request.story_length.value} story",
            flush=True,
        )

        # Build prompt
        prompt = await _build_story_prompt(request, user_context, db)

        # Calculate prompt hash for logging
        prompt_hash = calculate_prompt_hash(prompt)

        # Determine action slug for logging
        action_slug = f"story-{request.story_length.value}"
        if request.include_images:
            action_slug += "-illustrated"

        # Create request metadata
        request_metadata = create_request_metadata(
            action=action_slug,
            parameters={
                "story_length": request.story_length.value,
                "target_audience": request.target_audience.value,
                "character_count": len(request.characters),
                "has_custom_prompt": bool(request.custom_prompt),
                "include_images": request.include_images,
            },
            user_context=user_context if user_context != "general user" else None,
            session_id=str(request.session_id) if request.session_id else None,
        )

        # Add prompt hash to metadata
        request_metadata["prompt_hash"] = prompt_hash

        # Use centralized client for generation
        generated_text, generation_metadata = await llm_client.generate_completion(
            prompt=prompt,
            app_config=adjusted_config,
            user_id=request.user_id,
            app_id="fairydust-story",
            action=action_slug,
            request_metadata=request_metadata,
        )

        # Extract title and content from generated text
        title, content = _extract_title_and_content(generated_text)
        word_count = _count_words(content)
        estimated_reading_time = _calculate_reading_time(word_count)

        # Extract metadata from generation result
        provider = generation_metadata["provider"]
        model_id = generation_metadata["model_id"]
        tokens_used = generation_metadata["tokens_used"]
        cost = generation_metadata["cost_usd"]
        latency_ms = generation_metadata["generation_time_ms"]

        print(
            f"✅ STORY_LLM: Generated story successfully with {provider}/{model_id} (latency: {latency_ms}ms)",
            flush=True,
        )

        return (
            content,
            title,
            word_count,
            estimated_reading_time,
            model_id,
            tokens_used,
            cost,
            latency_ms,
            provider,
        )

    except LLMError as e:
        print(f"❌ STORY_LLM: LLM error: {str(e)}", flush=True)
        return None, "", 0, "", "claude-3-5-sonnet-20241022", {}, 0.0, 0, "anthropic"
    except Exception as e:
        print(f"❌ STORY_LLM: Unexpected error generating story: {str(e)}", flush=True)
        print(f"❌ STORY_LLM: Error type: {type(e).__name__}", flush=True)
        import traceback

        print(f"❌ STORY_LLM: Traceback: {traceback.format_exc()}", flush=True)
        return None, "", 0, "", "claude-3-5-sonnet-20241022", {}, 0.0, 0, "anthropic"


@traceable(run_type="llm", name="story-summary-generation")
async def _generate_story_summary(
    title: str, content: str, characters: list, target_audience: TargetAudience, user_id: uuid.UUID
) -> str:
    """Generate a concise summary of the story for theme tracking"""
    try:
        print(f"📝 STORY_SUMMARY: Generating summary for story '{title}'", flush=True)

        # Prepare character names for context
        character_names = [
            char.name if hasattr(char, "name") else str(char) for char in characters[:3]
        ]
        char_context = f" featuring {', '.join(character_names)}" if character_names else ""

        # Create a focused prompt for story summarization
        summary_prompt = f"""Summarize this {target_audience.value} story in 1-2 sentences, focusing on the main theme, setting, and plot elements. Be concise and capture what makes this story unique.

Title: {title}
Story: {content[:800]}...

Provide only the summary, no additional commentary:"""

        # Use the LLM client to generate summary
        app_config = {
            "primary_provider": "anthropic",
            "primary_model_id": "claude-3-5-haiku-20241022",
            "primary_parameters": {
                "temperature": 0.3,  # Lower temperature for consistent summaries
                "max_tokens": 100,
                "top_p": 0.9,
            },
        }

        content, metadata = await llm_client.generate_completion(
            prompt=summary_prompt,
            app_config=app_config,
            user_id=user_id,  # Use actual user_id for proper usage logging
            app_id="fairydust-story",
            action="story_summary_generation",
            request_metadata={"purpose": "story_summary_generation"},
        )

        summary = content.strip() if content else ""

        # Clean up summary - remove quotes and meta commentary
        summary = summary.strip('"').strip()
        if summary.startswith("Summary:") or summary.startswith("The story"):
            summary = summary.split(":", 1)[-1].strip() if ":" in summary else summary

        # Fallback if summary generation fails
        if not summary or len(summary) < 10:
            summary = f"A {target_audience.value} story about {', '.join(character_names[:2]) if character_names else 'adventure'}"

        print(f"✅ STORY_SUMMARY: Generated summary: {summary[:100]}...", flush=True)
        return summary

    except Exception as e:
        print(f"❌ STORY_SUMMARY: Error generating summary: {str(e)}", flush=True)
        # Return a simple fallback summary
        char_names = [char.name if hasattr(char, "name") else str(char) for char in characters[:2]]
        return f"A {target_audience.value} story" + (
            f" featuring {', '.join(char_names)}" if char_names else ""
        )


async def _save_story(
    db: Database,
    user_id: uuid.UUID,
    title: str,
    content: str,
    story_length: StoryLength,
    target_audience: TargetAudience,
    word_count: int,
    characters: list,
    session_id: Optional[uuid.UUID],
    model_used: str,
    tokens_used: dict,
    cost: float,
    custom_prompt: Optional[str],
) -> uuid.UUID:
    """Save story to database with AI-generated summary"""
    try:
        story_id = uuid.uuid4()

        # Generate story summary for theme tracking
        story_summary = await _generate_story_summary(
            title, content, characters, target_audience, user_id
        )

        metadata = {
            "characters": [char.dict() for char in characters],
            "custom_prompt": custom_prompt,
            "session_id": str(session_id) if session_id else None,
            "model_used": model_used,
            "tokens_used": tokens_used.get("total", 0),
            "cost_usd": cost,
        }

        insert_query = """
            INSERT INTO user_stories (
                id, user_id, title, content, story_length, target_audience,
                characters_involved, metadata, word_count, story_summary,
                created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9, $10,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """

        await db.execute(
            insert_query,
            story_id,
            user_id,
            title,
            content,
            story_length.value,
            target_audience.value,
            json.dumps([char.dict() for char in characters]),
            json.dumps(metadata),
            word_count,
            story_summary,
        )

        print(f"✅ STORY_SAVE: Saved story {story_id} with summary", flush=True)
        return story_id

    except Exception as e:
        print(f"❌ STORY_SAVE: Error saving story: {str(e)}", flush=True)
        raise HTTPException(status_code=500, detail="Failed to save story")


async def _update_story_with_images(
    db: Database, story_id: uuid.UUID, final_content: str, image_ids: list[str], has_images: bool
):
    """Update story with image markers and metadata"""
    try:
        image_data = {"image_ids": image_ids, "has_images": has_images, "images_complete": False}

        await db.execute(
            """
            UPDATE user_stories
            SET content = $1, has_images = $2, images_complete = $3, image_data = $4
            WHERE id = $5
            """,
            final_content,
            has_images,
            False,  # images_complete starts as False
            json.dumps(image_data),
            story_id,
        )

        print(f"✅ STORY_IMAGE_UPDATE: Updated story {story_id} with image metadata", flush=True)

    except Exception as e:
        print(f"❌ STORY_IMAGE_UPDATE: Failed to update story with images: {str(e)}", flush=True)
        raise


# Story Image Status Endpoints
@router.get("/stories/{story_id}/images/{image_id}", response_model=StoryImageStatusResponse)
async def get_story_image_status(
    story_id: str,
    image_id: str,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get status and URL of specific story image - includes cache control for failed images"""

    try:
        # Verify the story belongs to the user
        story = await db.fetch_one("SELECT user_id FROM user_stories WHERE id = $1", story_id)

        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        if current_user.user_id != str(story["user_id"]) and not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Access denied")

        # Get image status
        image_data = await db.fetch_one(
            "SELECT url, status FROM story_images WHERE story_id = $1 AND image_id = $2",
            story_id,
            image_id,
        )

        if not image_data:
            print(
                f"🔍 STORY_IMAGE_STATUS: Image {image_id} not found for story {story_id}", flush=True
            )
            return StoryImageStatusResponse(success=False, status="not_found", url=None)

        image_url = image_data["url"] if image_data["status"] == "completed" else None
        status = image_data["status"]

        # Log the URL being returned for debugging
        print(f"🔗 STORY_IMAGE_STATUS: Returning image status for {image_id}", flush=True)
        print(f"   Story ID: {story_id}", flush=True)
        print(f"   Status: {status}", flush=True)
        print(f"   URL: {image_url}", flush=True)
        if image_url:
            print(
                f"   URL Domain: {image_url.split('/')[2] if '://' in image_url else 'invalid-url'}",
                flush=True,
            )
            print(f"   Is images.fairydust.fun: {'images.fairydust.fun' in image_url}", flush=True)

        # Add warning for excessive polling of failed images
        if status == "failed":
            print(
                f"⚠️  STORY_IMAGE_STATUS: Client polling FAILED image {image_id} - should stop polling!",
                flush=True,
            )
            print(
                "   Suggestion: Client should implement exponential backoff or stop polling failed images",
                flush=True,
            )
        elif status == "processing":
            print(
                f"🔄 STORY_IMAGE_STATUS: Image {image_id} still processing - normal polling",
                flush=True,
            )
        elif status == "completed":
            print(
                f"✅ STORY_IMAGE_STATUS: Image {image_id} completed - client should stop polling",
                flush=True,
            )

        return StoryImageStatusResponse(status=status, url=image_url)

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ STORY_IMAGE_STATUS: Error getting image status: {str(e)}", flush=True)
        raise HTTPException(status_code=500, detail="Failed to get image status")


@router.get("/stories/{story_id}/images/batch", response_model=StoryImageBatchResponse)
async def get_story_images_batch_status(
    story_id: str,
    ids: str = Query(..., description="Comma-separated list of image IDs"),
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get status and URLs of multiple story images at once"""

    try:
        # Verify the story belongs to the user
        story = await db.fetch_one("SELECT user_id FROM user_stories WHERE id = $1", story_id)

        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        if current_user.user_id != str(story["user_id"]) and not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Access denied")

        # Parse image IDs
        image_ids = [img_id.strip() for img_id in ids.split(",") if img_id.strip()]

        if not image_ids:
            return StoryImageBatchResponse(images={})

        # Get all image statuses
        images = await db.fetch_all(
            """
            SELECT image_id, url, status
            FROM story_images
            WHERE story_id = $1 AND image_id = ANY($2)
            """,
            story_id,
            image_ids,
        )

        # Build response
        image_statuses = {}
        print(
            f"🔗 STORY_IMAGE_BATCH: Processing {len(images)} images for story {story_id}", flush=True
        )

        for image in images:
            image_url = image["url"] if image["status"] == "completed" else None

            # Log each image URL
            print(f"   Image {image['image_id']}: {image['status']}", flush=True)
            if image_url:
                print(f"     URL: {image_url}", flush=True)
                print(
                    f"     Domain: {image_url.split('/')[2] if '://' in image_url else 'invalid-url'}",
                    flush=True,
                )

            image_statuses[image["image_id"]] = StoryImageStatus(
                status=image["status"], url=image_url
            )

        # Add not_found status for missing images
        for image_id in image_ids:
            if image_id not in image_statuses:
                image_statuses[image_id] = StoryImageStatus(status="not_found", url=None)

        return StoryImageBatchResponse(images=image_statuses)

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ STORY_IMAGE_BATCH: Error getting batch image status: {str(e)}", flush=True)
        raise HTTPException(status_code=500, detail="Failed to get batch image status")
