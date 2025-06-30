# services/content/story_routes.py
import json
import os
import re
import time
import uuid
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request

# Service URL configuration based on environment
environment = os.getenv('ENVIRONMENT', 'staging')
base_url_suffix = 'production' if environment == 'production' else 'staging'
ledger_url = f"https://fairydust-ledger-{base_url_suffix}.up.railway.app"

from models import (
    StoriesListResponse,
    StoryConfigResponse,
    StoryDeleteResponse,
    StoryErrorResponse,
    StoryFavoriteRequest,
    StoryFavoriteResponse,
    StoryGenerationRequest,
    StoryGenerationResponseNew,
    StoryLength,
    TargetAudience,
    TokenUsage,
    UserStoryNew,
)

from shared.auth_middleware import TokenData, get_current_user
from shared.database import Database, get_db
from shared.json_utils import parse_jsonb_field
from shared.llm_pricing import calculate_llm_cost
from shared.llm_usage_logger import calculate_prompt_hash, create_request_metadata, log_llm_usage

router = APIRouter()

# Constants - Reading time based
STORY_DUST_COSTS = {
    StoryLength.QUICK: 2,   # 2-3 minute read
    StoryLength.MEDIUM: 4,  # 5-7 minute read  
    StoryLength.LONG: 6,    # 8-12 minute read
}

READING_TIME_WORD_TARGETS = {
    StoryLength.QUICK: (400, 600),     # ~2-3 min reading time
    StoryLength.MEDIUM: (1000, 1400),  # ~5-7 min reading time
    StoryLength.LONG: (1600, 2400),    # ~8-12 min reading time
}

STORY_RATE_LIMIT = 10  # Max 10 stories per hour per user


@router.post("/apps/story/generate")
async def generate_story(
    request: StoryGenerationRequest,
    http_request: Request,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """
    Generate a new story using LLM and automatically save it to user's collection.
    """
    print(f"📖 STORY: Starting generation for user {request.user_id}", flush=True)
    print(f"📂 STORY: Length: {request.story_length}", flush=True)

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

        # Get DUST cost for story length
        dust_cost = STORY_DUST_COSTS[request.story_length]

        # Verify user has enough DUST
        user_balance = await _get_user_balance(request.user_id, auth_token)
        if user_balance < dust_cost:
            print(
                f"💰 STORY: Insufficient DUST balance: {user_balance} < {dust_cost}",
                flush=True,
            )
            return StoryErrorResponse(
                error="Insufficient DUST balance",
                current_balance=user_balance,
                required_amount=dust_cost,
            )

        # Get user context for personalization
        user_context = await _get_user_context(db, request.user_id)
        print("👤 STORY: Retrieved user context", flush=True)

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
        ) = await _generate_story_llm(
            request=request,
            user_context=user_context,
        )

        if not story_content:
            return StoryErrorResponse(error="Failed to generate story. Please try again.")

        print(f"🤖 STORY: Generated story: {title}", flush=True)

        # Log LLM usage for analytics (background task)
        try:
            # Calculate prompt hash for the story generation
            full_prompt = _build_story_prompt(request, user_context)
            prompt_hash = calculate_prompt_hash(full_prompt)

            # Create request metadata
            request_metadata = create_request_metadata(
                action="story_generation",
                parameters={
                    "story_length": request.story_length.value,
                    "target_audience": request.target_audience.value,
                    "character_count": len(request.characters),
                    "has_custom_prompt": bool(request.custom_prompt),
                },
                user_context=user_context if user_context != "general user" else None,
                session_id=str(request.session_id) if request.session_id else None,
            )

            # Log usage asynchronously (don't block story generation on logging failures)
            await log_llm_usage(
                user_id=request.user_id,
                app_id="fairydust-story",
                provider="anthropic",
                model_id=model_used,
                prompt_tokens=tokens_used.get("prompt", 0),
                completion_tokens=tokens_used.get("completion", 0),
                total_tokens=tokens_used.get("total", 0),
                cost_usd=cost,
                latency_ms=latency_ms,
                prompt_hash=prompt_hash,
                finish_reason="stop",
                was_fallback=False,
                fallback_reason=None,
                request_metadata=request_metadata,
                auth_token=auth_token,
            )
        except Exception as e:
            print(f"⚠️ STORY: Failed to log LLM usage: {str(e)}", flush=True)
            # Continue with story generation even if logging fails

        # Save story to database
        story_id = await _save_story(
            db=db,
            user_id=request.user_id,
            title=title,
            content=story_content,
            story_length=request.story_length,
            target_audience=request.target_audience,
            word_count=word_count,
            characters=request.characters,
            session_id=request.session_id,
            model_used=model_used,
            tokens_used=tokens_used,
            cost=cost,
            dust_cost=dust_cost,
            custom_prompt=request.custom_prompt,
        )

        print(f"✅ STORY: Generated story for user {request.user_id} (DUST handled by client)", flush=True)

        # Build response
        story = UserStoryNew(
            id=story_id,
            title=title,
            content=story_content,
            story_length=request.story_length,
            target_audience=request.target_audience,
            word_count=word_count,
            estimated_reading_time=estimated_reading_time,
            created_at=datetime.utcnow(),
            is_favorited=False,
            metadata={
                "characters": [char.dict() for char in request.characters],
                "custom_prompt": request.custom_prompt,
                "dust_cost": dust_cost,
            },
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
            new_dust_balance=user_balance,
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
                   word_count, is_favorited, created_at, metadata
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
                    "dust": STORY_DUST_COSTS[StoryLength.QUICK],
                },
                {
                    "label": "Medium Story", 
                    "value": "medium",
                    "reading_time": "5-7 minutes",
                    "words": "1000-1400",
                    "dust": STORY_DUST_COSTS[StoryLength.MEDIUM],
                },
                {
                    "label": "Long Story",
                    "value": "long", 
                    "reading_time": "8-12 minutes",
                    "words": "1600-2400",
                    "dust": STORY_DUST_COSTS[StoryLength.LONG],
                },
            ],
            "target_audiences": [audience.value for audience in TargetAudience],
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
            "age_ranges": ["child", "teen", "adult", "senior"],
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
async def _get_user_balance(user_id: uuid.UUID, auth_token: str) -> int:
    """Get user's current DUST balance via Ledger Service"""
    print(f"🔍 STORY_BALANCE: Checking DUST balance for user {user_id}", flush=True)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{ledger_url}/balance/{user_id}",
                headers={"Authorization": auth_token},
                timeout=10.0,
            )

            if response.status_code == 200:
                balance_data = response.json()
                balance = balance_data.get("balance", 0)
                print(f"✅ STORY_BALANCE: User {user_id} has {balance} DUST", flush=True)
                return balance
            else:
                print(f"❌ STORY_BALANCE: Ledger service error: {response.text}", flush=True)
                return 0
    except Exception as e:
        print(f"❌ STORY_BALANCE: Exception getting balance: {str(e)}", flush=True)
        return 0


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
    """Get user context for personalization"""
    try:
        # Get user profile data
        profile_query = """
            SELECT field_name, field_value
            FROM user_profile_data
            WHERE user_id = $1
        """

        profile_rows = await db.fetch_all(profile_query, user_id)

        # Get people in my life
        people_query = """
            SELECT name, relationship, age_range
            FROM people_in_my_life
            WHERE user_id = $1
        """

        people_rows = await db.fetch_all(people_query, user_id)

        # Build context string
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

        if people_rows:
            people_list = []
            for row in people_rows:
                person_desc = f"{row['name']} ({row['relationship']}"
                if row["age_range"]:
                    person_desc += f", {row['age_range']}"
                person_desc += ")"
                people_list.append(person_desc)

            if people_list:
                context_parts.append(f"People: {', '.join(people_list[:3])}")

        return "; ".join(context_parts) if context_parts else "general user"

    except Exception as e:
        print(f"⚠️ STORY_CONTEXT: Error getting user context: {str(e)}", flush=True)
        return "general user"


async def _get_llm_model_config() -> dict:
    """Get LLM configuration for story app (with caching)"""
    from shared.app_config_cache import get_app_config_cache

    app_id = "fairydust-story"

    # Try to get from cache first
    cache = await get_app_config_cache()
    cached_config = await cache.get_model_config(app_id)

    if cached_config:
        return {
            "primary_provider": cached_config.get("primary_provider", "anthropic"),
            "primary_model_id": cached_config.get("primary_model_id", "claude-3-5-sonnet-20241022"),
            "primary_parameters": cached_config.get(
                "primary_parameters", {"temperature": 0.8, "max_tokens": 2000, "top_p": 0.9}
            ),
        }

    # Cache miss - use default config and cache it
    default_config = {
        "primary_provider": "anthropic",
        "primary_model_id": "claude-3-5-sonnet-20241022",
        "primary_parameters": {"temperature": 0.8, "max_tokens": 2000, "top_p": 0.9},
    }

    # Cache the default config for future requests
    await cache.set_model_config(app_id, default_config)

    return default_config


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


def _build_story_prompt(request: StoryGenerationRequest, user_context: str) -> str:
    """Build the LLM prompt for story generation"""
    min_words, max_words = READING_TIME_WORD_TARGETS[request.story_length]
    target_words = (min_words + max_words) // 2
    
    # Convert story length to readable format
    length_descriptions = {
        StoryLength.QUICK: "2-3 minute read (~500 words)",
        StoryLength.MEDIUM: "5-7 minute read (~1200 words)", 
        StoryLength.LONG: "8-12 minute read (~2000 words)"
    }

    # Build character descriptions
    character_descriptions = []
    if request.characters:
        for char in request.characters:
            desc = f"- {char.name} ({char.relationship}"
            if char.age_range:
                desc += f", {char.age_range}"
            desc += ")"
            if char.traits:
                desc += f", traits: {', '.join(char.traits)}"
            character_descriptions.append(desc)

    character_text = (
        f"Characters to include:\n{chr(10).join(character_descriptions)}"
        if character_descriptions
        else "No specific characters required - create original characters as needed."
    )

    # Create varied, unpredictable prompt
    prompt = f"""You are a master storyteller with infinite creativity. Create a truly unique and surprising story for {request.target_audience.value} audience that takes about {length_descriptions[request.story_length]} to read.

{character_text}"""

    if request.custom_prompt:
        prompt += f"\nSpecial request: {request.custom_prompt}"

    if user_context != "general user":
        prompt += f"\nPersonalization context: {user_context}"

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
- Avoid overused settings like "magical kingdoms" or "haunted houses"
- Be specific and unusual: a 24-hour laundromat, underwater research station, food truck at a music festival, retirement home game night, etc.
- Use settings that serve the story and create natural conflict or intrigue

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

Format the story with:
TITLE: [Creative, intriguing title]

[Story content with rich details, natural dialogue, and compelling narrative]

Remember: Your goal is to create something memorable and unique that readers haven't seen before. Be bold, creative, and surprising while staying appropriate for the audience."""

    return prompt


def _count_words(text: str) -> int:
    """Count words in text"""
    return len(re.findall(r"\b\w+\b", text))


def _extract_title_and_content(generated_text: str) -> tuple[str, str]:
    """Extract title and content from generated text"""
    lines = generated_text.strip().split("\n")

    # Look for TITLE: prefix
    if lines[0].startswith("TITLE: "):
        title = lines[0].replace("TITLE: ", "").strip()
        content = "\n".join(lines[1:]).strip()
    else:
        # Use first line as title if no TITLE: prefix
        title = lines[0].strip()
        content = "\n".join(lines[1:]).strip() if len(lines) > 1 else generated_text

    return title, content


async def _generate_story_llm(
    request: StoryGenerationRequest,
    user_context: str,
) -> tuple[Optional[str], str, int, str, str, dict, float, int]:
    """Generate story using LLM"""
    try:
        # Get LLM model configuration from database/cache
        model_config = await _get_llm_model_config()

        provider = model_config.get("primary_provider", "anthropic")
        model_id = model_config.get("primary_model_id", "claude-3-5-sonnet-20241022")
        parameters = model_config.get("primary_parameters", {})

        temperature = parameters.get("temperature", 0.8)
        max_tokens = parameters.get("max_tokens", 2000)
        top_p = parameters.get("top_p", 0.9)

        # Build prompt
        prompt = _build_story_prompt(request, user_context)

        print(f"🤖 STORY_LLM: Generating with {provider} model {model_id}", flush=True)

        # Check API key
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            print("❌ STORY_LLM: Missing ANTHROPIC_API_KEY environment variable", flush=True)
            return None, "", 0, "", model_id, {}, 0.0, 0

        print(f"🔑 STORY_LLM: API key configured (length: {len(api_key)})", flush=True)

        # Track request latency
        start_time = time.time()

        # Make API call based on provider
        async with httpx.AsyncClient(timeout=60.0) as client:
            if provider == "anthropic":
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "Content-Type": "application/json",
                        "x-api-key": api_key,
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
                    generated_text = result["content"][0]["text"].strip()

                    # Extract title and content
                    title, content = _extract_title_and_content(generated_text)
                    word_count = _count_words(content)
                    estimated_reading_time = _calculate_reading_time(word_count)

                    # Calculate tokens and cost
                    usage = result.get("usage", {})
                    prompt_tokens = usage.get("input_tokens", 0)
                    completion_tokens = usage.get("output_tokens", 0)
                    total_tokens = prompt_tokens + completion_tokens

                    tokens_used = {
                        "prompt": prompt_tokens,
                        "completion": completion_tokens,
                        "total": total_tokens,
                    }

                    cost = calculate_llm_cost(
                        "anthropic", model_id, prompt_tokens, completion_tokens
                    )

                    # Calculate latency
                    latency_ms = int((time.time() - start_time) * 1000)

                    print(
                        f"✅ STORY_LLM: Generated story successfully (latency: {latency_ms}ms)",
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
                    )

                else:
                    print(
                        f"❌ STORY_LLM: Anthropic API error {response.status_code}: {response.text}",
                        flush=True,
                    )
                    latency_ms = int((time.time() - start_time) * 1000)
                    return None, "", 0, "", model_id, {}, 0.0, latency_ms

            else:
                print(
                    f"⚠️ STORY_LLM: Unsupported provider {provider}, falling back to Anthropic",
                    flush=True,
                )
                # Fallback to Anthropic with default model
                return await _generate_story_llm(request, user_context)

    except Exception as e:
        print(f"❌ STORY_LLM: Error generating story: {str(e)}", flush=True)
        print(f"❌ STORY_LLM: Error type: {type(e).__name__}", flush=True)
        print(f"❌ STORY_LLM: Error details: {repr(e)}", flush=True)
        import traceback

        print(f"❌ STORY_LLM: Traceback: {traceback.format_exc()}", flush=True)
        return None, "", 0, "", "claude-3-5-sonnet-20241022", {}, 0.0, 0


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
    dust_cost: int,
    custom_prompt: Optional[str],
) -> uuid.UUID:
    """Save story to database"""
    try:
        story_id = uuid.uuid4()

        metadata = {
            "characters": [char.dict() for char in characters],
            "custom_prompt": custom_prompt,
            "session_id": str(session_id) if session_id else None,
            "model_used": model_used,
            "tokens_used": tokens_used.get("total", 0),
            "cost_usd": cost,
            "dust_cost": dust_cost,
        }

        insert_query = """
            INSERT INTO user_stories (
                id, user_id, title, content, story_length, target_audience,
                characters_involved, metadata, dust_cost, word_count,
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
            dust_cost,
            word_count,
        )

        print(f"✅ STORY_SAVE: Saved story {story_id}", flush=True)
        return story_id

    except Exception as e:
        print(f"❌ STORY_SAVE: Error saving story: {str(e)}", flush=True)
        raise HTTPException(status_code=500, detail="Failed to save story")
