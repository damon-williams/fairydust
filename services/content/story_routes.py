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
from models import (
    StoryConfigResponse,
    StoryDeleteResponse,
    StoryErrorResponse,
    StoryFavoriteRequest,
    StoryFavoriteResponse,
    StoryGenerationRequest,
    StoryGenerationResponseNew,
    StoryGenre,
    StoryLength,
    StoriesListResponse,
    TargetAudience,
    TokenUsage,
    UserStoryNew,
)

from shared.auth_middleware import TokenData, get_current_user
from shared.database import Database, get_db
from shared.llm_pricing import calculate_llm_cost

router = APIRouter()

# Constants
STORY_DUST_COSTS = {
    StoryLength.SHORT: 2,
    StoryLength.MEDIUM: 4,
    StoryLength.LONG: 6,
}

WORD_COUNT_TARGETS = {
    StoryLength.SHORT: (300, 500),
    StoryLength.MEDIUM: (600, 1000),
    StoryLength.LONG: (1000, 1500),
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
    print(f"📂 STORY: Genre: {request.genre}, Length: {request.story_length}", flush=True)

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
        print(f"👤 STORY: Retrieved user context", flush=True)

        # Generate story using LLM
        (
            story_content,
            title,
            word_count,
            estimated_reading_time,
            model_used,
            tokens_used,
            cost,
        ) = await _generate_story_llm(
            request=request,
            user_context=user_context,
        )

        if not story_content:
            return StoryErrorResponse(error="Failed to generate story. Please try again.")

        print(f"🤖 STORY: Generated story: {title}", flush=True)

        # Save story to database
        story_id = await _save_story(
            db=db,
            user_id=request.user_id,
            title=title,
            content=story_content,
            genre=request.genre,
            story_length=request.story_length,
            target_audience=request.target_audience,
            word_count=word_count,
            characters=request.characters,
            session_id=request.session_id,
            model_used=model_used,
            tokens_used=tokens_used,
            cost=cost,
            dust_cost=dust_cost,
            setting=request.setting,
            theme=request.theme,
            custom_prompt=request.custom_prompt,
        )

        # Consume DUST after successful generation and saving
        dust_consumed = await _consume_dust(request.user_id, dust_cost, auth_token, db)
        if not dust_consumed:
            print(f"❌ STORY: Failed to consume DUST for user {request.user_id}", flush=True)
            return StoryErrorResponse(error="Payment processing failed")

        new_balance = user_balance - dust_cost
        print(
            f"💰 STORY: Consumed {dust_cost} DUST from user {request.user_id}",
            flush=True,
        )

        # Build response
        story = UserStoryNew(
            id=story_id,
            title=title,
            content=story_content,
            genre=request.genre,
            story_length=request.story_length,
            target_audience=request.target_audience,
            word_count=word_count,
            estimated_reading_time=estimated_reading_time,
            created_at=datetime.utcnow(),
            is_favorited=False,
            metadata={
                "characters": [char.dict() for char in request.characters],
                "setting": request.setting,
                "theme": request.theme,
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
            new_dust_balance=new_balance,
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
    genre: Optional[StoryGenre] = Query(None, description="Filter by genre"),
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
            SELECT id, title, content, genre, story_length, target_audience, 
                   word_count, is_favorited, created_at, metadata
            FROM user_stories
            WHERE user_id = $1
        """
        params = [user_id]
        param_count = 1

        if genre:
            param_count += 1
            base_query += f" AND genre = ${param_count}"
            params.append(genre.value)

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

        if genre:
            count_query += " AND genre = $2"
            count_params.append(genre.value)

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
                genre=StoryGenre(row["genre"]),
                story_length=StoryLength(row["story_length"]),
                target_audience=TargetAudience(row["target_audience"] or "family"),
                word_count=row["word_count"] or 0,
                estimated_reading_time=estimated_reading_time,
                created_at=row["created_at"],
                is_favorited=row["is_favorited"],
                metadata=row["metadata"] or {},
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
            RETURNING id, title, content, genre, story_length, target_audience, 
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
            genre=StoryGenre(result["genre"]),
            story_length=StoryLength(result["story_length"]),
            target_audience=TargetAudience(result["target_audience"] or "family"),
            word_count=result["word_count"] or 0,
            estimated_reading_time=estimated_reading_time,
            created_at=result["created_at"],
            is_favorited=result["is_favorited"],
            metadata=result["metadata"] or {},
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
    Get available genres, story lengths, and DUST costs.
    """
    print(f"⚙️ STORY: Getting story configuration", flush=True)

    try:
        config = {
            "genres": [genre.value for genre in StoryGenre],
            "story_lengths": [
                {
                    "label": "Short",
                    "value": "short",
                    "words": "300-500",
                    "dust": STORY_DUST_COSTS[StoryLength.SHORT],
                },
                {
                    "label": "Medium",
                    "value": "medium",
                    "words": "600-1000",
                    "dust": STORY_DUST_COSTS[StoryLength.MEDIUM],
                },
                {
                    "label": "Long",
                    "value": "long",
                    "words": "1000-1500",
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

        print(f"✅ STORY: Returning story configuration", flush=True)
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
                f"https://fairydust-ledger-production.up.railway.app/balance/{user_id}",
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


async def _consume_dust(user_id: uuid.UUID, amount: int, auth_token: str, db: Database) -> bool:
    """Consume DUST for story generation via Ledger Service"""
    print(f"🔍 STORY_DUST: Attempting to consume {amount} DUST for user {user_id}", flush=True)
    try:
        # Get the proper app UUID
        app_id = await _get_app_id(db)

        # Generate idempotency key to prevent double-charging
        idempotency_key = f"story_gen_{str(user_id).replace('-', '')[:16]}_{int(time.time())}"

        async with httpx.AsyncClient() as client:
            payload = {
                "user_id": str(user_id),
                "amount": amount,
                "app_id": app_id,
                "action": "story_generation",
                "idempotency_key": idempotency_key,
                "metadata": {"service": "content", "feature": "story_generation"},
            }

            response = await client.post(
                "https://fairydust-ledger-production.up.railway.app/transactions/consume",
                json=payload,
                headers={"Authorization": auth_token},
                timeout=10.0,
            )

            if response.status_code != 200:
                response_text = response.text
                print(f"❌ STORY_DUST: Error response: {response_text}", flush=True)
                return False

            print("✅ STORY_DUST: DUST consumption successful", flush=True)
            return True
    except Exception as e:
        print(f"❌ STORY_DUST: Exception consuming DUST: {str(e)}", flush=True)
        return False


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
    min_words, max_words = WORD_COUNT_TARGETS[request.story_length]
    target_words = (min_words + max_words) // 2

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

    # Build prompt
    prompt = f"""Generate a {request.genre.value} story that is {request.story_length.value} length (target: {target_words} words) for {request.target_audience.value} audience.

{character_text}"""

    if request.setting:
        prompt += f"\nSetting: {request.setting}"

    if request.theme:
        prompt += f"\nTheme: {request.theme}"

    if request.custom_prompt:
        prompt += f"\nSpecial request: {request.custom_prompt}"

    if user_context != "general user":
        prompt += f"\nPersonalization context: {user_context}"

    prompt += f"""

Story requirements:
- Target word count: {target_words} words
- Genre: {request.genre.value}
- Audience: {request.target_audience.value}
- Include a clear title at the beginning
- Make it engaging and age-appropriate
- If characters are provided, make them central to the story
- Include dialogue and vivid descriptions
- Ensure the story has a satisfying conclusion

Format the story with:
TITLE: [Story Title]

[Story content with paragraphs, dialogue, and descriptions]"""

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
) -> tuple[Optional[str], str, int, str, str, dict, float]:
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

        # Make API call based on provider
        async with httpx.AsyncClient(timeout=30.0) as client:
            if provider == "anthropic":
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "Content-Type": "application/json",
                        "x-api-key": os.getenv("ANTHROPIC_API_KEY", ""),
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

                    print(f"✅ STORY_LLM: Generated story successfully", flush=True)
                    return (
                        content,
                        title,
                        word_count,
                        estimated_reading_time,
                        model_id,
                        tokens_used,
                        cost,
                    )

                else:
                    print(
                        f"❌ STORY_LLM: Anthropic API error {response.status_code}: {response.text}",
                        flush=True,
                    )
                    return None, "", 0, "", model_id, {}, 0.0

            else:
                print(
                    f"⚠️ STORY_LLM: Unsupported provider {provider}, falling back to Anthropic",
                    flush=True,
                )
                # Fallback to Anthropic with default model
                return await _generate_story_llm(request, user_context)

    except Exception as e:
        print(f"❌ STORY_LLM: Error generating story: {str(e)}", flush=True)
        return None, "", 0, "", "claude-3-5-sonnet-20241022", {}, 0.0


async def _save_story(
    db: Database,
    user_id: uuid.UUID,
    title: str,
    content: str,
    genre: StoryGenre,
    story_length: StoryLength,
    target_audience: TargetAudience,
    word_count: int,
    characters: list,
    session_id: Optional[uuid.UUID],
    model_used: str,
    tokens_used: dict,
    cost: float,
    dust_cost: int,
    setting: Optional[str],
    theme: Optional[str],
    custom_prompt: Optional[str],
) -> uuid.UUID:
    """Save story to database"""
    try:
        story_id = uuid.uuid4()

        metadata = {
            "characters": [char.dict() for char in characters],
            "setting": setting,
            "theme": theme,
            "custom_prompt": custom_prompt,
            "session_id": str(session_id) if session_id else None,
            "model_used": model_used,
            "tokens_used": tokens_used.get("total", 0),
            "cost_usd": cost,
            "dust_cost": dust_cost,
        }

        insert_query = """
            INSERT INTO user_stories (
                id, user_id, title, content, genre, story_length, target_audience,
                characters_involved, metadata, dust_cost, word_count, 
                created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10, $11, 
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """

        await db.execute(
            insert_query,
            story_id,
            user_id,
            title,
            content,
            genre.value,
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
