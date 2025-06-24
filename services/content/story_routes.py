# services/content/story_routes.py
import json
import time
import httpx
import re
import logging
from datetime import datetime, timedelta
from typing import Optional, List
from uuid import UUID, uuid4
from fastapi import APIRouter, HTTPException, Depends, Query, status, BackgroundTasks
from fastapi.security import HTTPBearer

logger = logging.getLogger(__name__)

from models import (
    StoryGenerationRequest, StoryGenerationResponse, UserStory, StoriesResponse,
    StoryFavoriteRequest, StoryStatistics, StoryCharacter, StoryGenre, 
    StoryLength, TargetAudience, StoryGenerationMetadata, ErrorResponse
)
from shared.database import get_db, Database
from shared.auth_middleware import get_current_user, TokenData
from shared.json_utils import parse_story_data, safe_json_dumps
from rate_limiting import check_story_generation_rate_limit, check_api_rate_limit_only
from content_safety import content_safety_filter

security = HTTPBearer()
router = APIRouter()

# Constants
DUST_COSTS = {
    StoryLength.SHORT: 2,
    StoryLength.MEDIUM: 4,
    StoryLength.LONG: 6
}

WORD_COUNT_TARGETS = {
    StoryLength.SHORT: (300, 500),
    StoryLength.MEDIUM: (600, 1000),
    StoryLength.LONG: (1000, 1500)
}

GENRE_INSTRUCTIONS = {
    StoryGenre.ADVENTURE: "Include exciting challenges, discovery, and brave journeys.",
    StoryGenre.FANTASY: "Add magical elements, mythical creatures, and wonder.",
    StoryGenre.ROMANCE: "Focus on relationships, emotional connection, and heartwarming moments.",
    StoryGenre.COMEDY: "Include humor, funny situations, and lighthearted moments appropriate for the audience.",
    StoryGenre.MYSTERY: "Create intrigue, problem-solving, and suspenseful discovery.",
    StoryGenre.FAMILY: "Emphasize family bonds, togetherness, and meaningful relationships.",
    StoryGenre.BEDTIME: "Use a gentle, calming tone with positive, peaceful endings."
}

async def get_user_dust_balance(user_id: UUID) -> int:
    """Check user's DUST balance via Ledger Service"""
    # For now, return a mock balance - in production this would call the Ledger Service
    # TODO: Implement actual Ledger Service integration
    return 100  # Mock balance

async def consume_dust(user_id: UUID, amount: int, description: str, story_metadata: dict) -> bool:
    """Consume DUST via Ledger Service"""
    try:
        # TODO: Replace with actual Ledger Service call
        # async with httpx.AsyncClient() as client:
        #     response = await client.post(
        #         f"{LEDGER_SERVICE_URL}/transactions/consume",
        #         json={
        #             "user_id": str(user_id),
        #             "app_id": "fairydust-story",
        #             "amount": amount,
        #             "description": description,
        #             "metadata": story_metadata
        #         }
        #     )
        #     return response.status_code == 200
        return True  # Mock success
    except Exception:
        return False

async def get_llm_model_config() -> dict:
    """Get LLM configuration for story generation (with caching)"""
    from shared.app_config_cache import get_app_config_cache
    
    app_id = "fairydust-story"
    
    # Try to get from cache first
    cache = await get_app_config_cache()
    cached_config = await cache.get_model_config(app_id)
    
    if cached_config:
        return {
            "primary_provider": cached_config.get("primary_provider", "anthropic"),
            "primary_model_id": cached_config.get("primary_model_id", "claude-3-5-sonnet-20241022"),
            "primary_parameters": cached_config.get("primary_parameters", {
                "temperature": 0.8,
                "max_tokens": 2000,
                "top_p": 0.9
            })
        }
    
    # Cache miss - use default config and cache it
    default_config = {
        "primary_provider": "anthropic",
        "primary_model_id": "claude-3-5-sonnet-20241022",
        "primary_parameters": {
            "temperature": 0.8,
            "max_tokens": 2000,
            "top_p": 0.9
        }
    }
    
    # Cache the default config for future requests
    await cache.set_model_config(app_id, default_config)
    
    return default_config

async def log_llm_usage(user_id: UUID, model_info: dict, tokens_used: int, cost: float, latency_ms: int):
    """Log LLM usage to Apps Service"""
    # TODO: Replace with actual Apps Service call
    # POST /llm/usage
    pass

def build_story_prompt(request: StoryGenerationRequest) -> str:
    """Build the LLM prompt for story generation"""
    min_words, max_words = WORD_COUNT_TARGETS[request.story_length]
    
    # Build character descriptions
    character_descriptions = []
    for char in request.characters:
        desc = f"- {char.name} ({char.relationship}"
        if char.age:
            desc += f", age {char.age}"
        desc += ")"
        if char.traits:
            desc += f": {', '.join(char.traits)}"
        character_descriptions.append(desc)
    
    character_list = "\n".join(character_descriptions)
    
    # Build prompt
    prompt = f"""Generate a {request.story_length.value} {request.genre.value} story featuring the following characters:

{character_list}

Story Requirements:
- Length: {min_words}-{max_words} words approximately
- Audience: {request.target_audience.value if request.target_audience else 'family'}
- Genre: {request.genre.value}"""

    if request.setting:
        prompt += f"\n- Setting: {request.setting}"
    
    if request.theme:
        prompt += f"\n- Theme: {request.theme}"
    
    if request.custom_prompt:
        prompt += f"\n- Include: {request.custom_prompt}"
    
    prompt += f"""

Guidelines:
- Keep content appropriate for {request.target_audience.value if request.target_audience else 'family'} audience
- Showcase each character's unique traits and personality
- Create engaging dialogue and vivid descriptions
- Include a clear beginning, middle, and end with a satisfying resolution
- Make the story personal and meaningful to the characters
- {GENRE_INSTRUCTIONS.get(request.genre, 'Create an engaging and appropriate story.')}

Return the story with a compelling title in this format:
TITLE: [Story Title]

[Story content starts here...]
"""
    
    return prompt

async def call_llm_service(prompt: str, model_config: dict) -> tuple[str, dict]:
    """Call the LLM service to generate story content"""
    from shared.llm_pricing import calculate_llm_cost
    start_time = time.time()
    
    try:
        # TODO: Replace with actual LLM service call
        # This would use the model_config to call Anthropic/OpenAI APIs
        
        # Mock response for development
        mock_response = """TITLE: The Magical Adventure of Sarah and Dad

Sarah bounced excitedly as she followed her dad through the enchanted forest. The eight-year-old's eyes sparkled with curiosity as she spotted a shimmering dragon hiding behind a massive oak tree.

"Dad, look!" Sarah whispered, tugging on her father's sleeve. "That dragon looks sad."

Her father, wise and protective as always, approached carefully. "Let's see what's wrong, little explorer," he said with his trademark gentle smile.

The dragon lifted its head, revealing tears that sparkled like diamonds. "I've lost my way home," the creature explained in a voice like tinkling bells. "The magical paths have shifted, and I can't find my family."

Sarah's brave heart immediately wanted to help. "We'll help you!" she declared, her love for animals shining through. "Right, Dad?"

Her father nodded, understanding that this was a perfect opportunity to teach his daughter about kindness and courage. Together, they embarked on a wonderful journey through the magical forest, using Sarah's keen observation skills and her dad's wisdom to help their new friend find the way home.

As the sun set, painting the sky in brilliant colors, they had successfully reunited the dragon with its family. The dragon family thanked them with a special gift - a small crystal that would always guide them when they needed help.

Walking home hand in hand, Sarah looked up at her dad. "That was the best adventure ever!" she said.

"And the best part," her father replied, "was sharing it with my brave, kind daughter."

As they reached home, both Sarah and her dad knew they would treasure this magical day forever, knowing that the greatest adventures are the ones we share with the people we love most."""

        # Extract title and content
        lines = mock_response.strip().split('\n')
        title = lines[0].replace('TITLE: ', '') if lines[0].startswith('TITLE: ') else "Generated Story"
        content = '\n'.join(lines[1:]).strip() if len(lines) > 1 else mock_response
        
        # Calculate realistic token usage
        prompt_tokens = len(prompt.split())
        completion_tokens = len(content.split())
        total_tokens = prompt_tokens + completion_tokens
        generation_time = int((time.time() - start_time) * 1000)
        
        # Calculate real cost using centralized pricing
        provider = model_config.get("primary_provider", "anthropic")
        model_id = model_config.get("primary_model_id", "claude-3-5-sonnet-20241022")
        calculated_cost = calculate_llm_cost(
            provider=provider,
            model_id=model_id,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens
        )
        
        generation_metadata = {
            "model_used": model_id,
            "tokens_used": total_tokens,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "generation_time_ms": generation_time,
            "cost_usd": calculated_cost
        }
        
        return title + "\n\n" + content, generation_metadata
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Story generation failed: {str(e)}"
        )

def count_words(text: str) -> int:
    """Count words in text"""
    return len(re.findall(r'\b\w+\b', text))

def extract_title_and_content(generated_text: str) -> tuple[str, str]:
    """Extract title and content from generated text"""
    lines = generated_text.strip().split('\n')
    
    # Look for TITLE: prefix
    if lines[0].startswith('TITLE: '):
        title = lines[0].replace('TITLE: ', '').strip()
        content = '\n'.join(lines[1:]).strip()
    else:
        # Use first line as title if no TITLE: prefix
        title = lines[0].strip()
        content = '\n'.join(lines[1:]).strip() if len(lines) > 1 else generated_text
    
    return title, content

async def log_story_generation(
    db: Database,
    user_id: UUID,
    story_id: Optional[UUID],
    prompt: str,
    model_info: dict,
    success: bool,
    error_message: Optional[str] = None
):
    """Log story generation attempt"""
    log_id = uuid4()
    await db.execute("""
        INSERT INTO story_generation_logs (
            id, user_id, story_id, generation_prompt, llm_model,
            tokens_used, generation_time_ms, success, error_message
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
    """, 
        log_id, user_id, story_id, prompt, 
        model_info.get("model_used"),
        model_info.get("tokens_used"),
        model_info.get("generation_time_ms"),
        success, error_message
    )

# Note: parse_story_data now imported from shared.json_utils

# API Endpoints

@router.post("/users/{user_id}/stories/generate", response_model=StoryGenerationResponse)
async def generate_story(
    user_id: UUID,
    request: StoryGenerationRequest,
    background_tasks: BackgroundTasks,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Generate a new personalized story"""
    print(f"🚀 STORY_GENERATE: Starting story generation for user {user_id}, genre={request.genre.value}, length={request.story_length.value}", flush=True)
    
    # Verify user can only generate stories for themselves
    if current_user.user_id != str(user_id):
        print(f"🚨 STORY_GENERATE: User {current_user.user_id} attempted to generate story for different user {user_id}", flush=True)
        raise HTTPException(status_code=403, detail="Can only generate stories for yourself")
    
    # Check rate limits
    print(f"🔍 STORY_GENERATE: Checking rate limits for user {user_id}", flush=True)
    await check_story_generation_rate_limit(user_id)
    print(f"✅ STORY_GENERATE: Rate limit check passed for user {user_id}", flush=True)
    
    # Validate content safety
    print(f"🔍 STORY_GENERATE: Validating content safety for user {user_id}", flush=True)
    is_safe, safety_issues = content_safety_filter.validate_request(request)
    if not is_safe:
        print(f"🚨 STORY_GENERATE: Content safety failed for user {user_id}: {safety_issues}", flush=True)
        raise HTTPException(
            status_code=400,
            detail=f"Content safety validation failed: {'; '.join(safety_issues)}"
        )
    print(f"✅ STORY_GENERATE: Content safety validation passed for user {user_id}", flush=True)
    
    # Check DUST cost and balance
    dust_cost = DUST_COSTS[request.story_length]
    print(f"🔍 STORY_GENERATE: Checking DUST balance for user {user_id}, cost={dust_cost}", flush=True)
    user_balance = await get_user_dust_balance(user_id)
    
    if user_balance < dust_cost:
        print(f"💰 STORY_GENERATE: Insufficient DUST for user {user_id}: need {dust_cost}, have {user_balance}", flush=True)
        raise HTTPException(
            status_code=402,
            detail=f"Insufficient DUST balance. Need {dust_cost}, have {user_balance}"
        )
    print(f"💰 STORY_GENERATE: DUST balance check passed for user {user_id}: {user_balance} >= {dust_cost}", flush=True)
    
    # Get LLM configuration
    model_config = await get_llm_model_config()
    
    # Build prompt
    prompt = build_story_prompt(request)
    
    # Generate story
    try:
        print(f"🤖 STORY_GENERATE: Calling LLM service for user {user_id}", flush=True)
        generated_text, generation_metadata = await call_llm_service(prompt, model_config)
        title, content = extract_title_and_content(generated_text)
        print(f"✅ STORY_GENERATE: LLM generation completed for user {user_id}, tokens={generation_metadata.get('tokens_used')}", flush=True)
        
        # Filter generated content for safety
        filtered_content, content_warnings = content_safety_filter.filter_generated_content(
            content, request.target_audience or TargetAudience.FAMILY
        )
        
        # Use filtered content
        content = filtered_content
        word_count = count_words(content)
        
        # Log content warnings if any
        if content_warnings:
            print(f"⚠️ STORY_GENERATE: Content warnings for user {user_id}: {content_warnings}", flush=True)
        
        # Consume DUST
        dust_consumed = await consume_dust(
            user_id, dust_cost, 
            f"Generated {request.story_length.value} {request.genre.value} story",
            {
                "story_genre": request.genre.value,
                "story_length": request.story_length.value,
                "characters_count": len(request.characters)
            }
        )
        
        if not dust_consumed:
            raise HTTPException(
                status_code=500,
                detail="Failed to process DUST payment"
            )
        
        # Save story to database
        story_id = uuid4()
        print(f"💾 STORY_GENERATE: Saving story to database for user {user_id}, story_id={story_id}", flush=True)
        await db.execute("""
            INSERT INTO user_stories (
                id, user_id, title, content, genre, story_length,
                characters_involved, metadata, dust_cost, word_count
            ) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9, $10)
        """,
            story_id, user_id, title, content, request.genre.value, request.story_length.value,
            safe_json_dumps([char.dict() for char in request.characters]),
            safe_json_dumps({
                "setting": request.setting,
                "theme": request.theme,
                "custom_prompt": request.custom_prompt,
                "target_audience": request.target_audience.value if request.target_audience else "family"
            }),
            dust_cost, word_count
        )
        print(f"✅ STORY_GENERATE: Story saved successfully for user {user_id}, story_id={story_id}, word_count={word_count}", flush=True)
        
        # Log generation success
        await log_story_generation(
            db, user_id, story_id, prompt, generation_metadata, True
        )
        
        # Log LLM usage in background
        background_tasks.add_task(
            log_llm_usage, user_id, generation_metadata,
            generation_metadata["tokens_used"], generation_metadata.get("cost_usd", 0),
            generation_metadata["generation_time_ms"]
        )
        
        # Fetch the created story
        story_data = await db.fetch_one("SELECT * FROM user_stories WHERE id = $1", story_id)
        story_dict = parse_story_data(story_data)
        
        story = UserStory(**story_dict)
        
        print(f"🎉 STORY_GENERATE: Story generation completed successfully for user {user_id}, story_id={story_id}", flush=True)
        return StoryGenerationResponse(
            story=story,
            generation_metadata=StoryGenerationMetadata(**generation_metadata)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ STORY_GENERATE: Story generation failed for user {user_id}: {str(e)}", flush=True)
        import traceback
        print(f"❌ STORY_GENERATE: Traceback: {traceback.format_exc()}", flush=True)
        # Log generation failure
        await log_story_generation(
            db, user_id, None, prompt, model_config, False, str(e)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Story generation failed: {str(e)}"
        )

@router.get("/users/{user_id}/stories", response_model=StoriesResponse)
async def get_user_stories(
    user_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    genre: Optional[StoryGenre] = Query(None),
    favorited_only: bool = Query(False),
    sort: str = Query("created_at_desc", pattern="^(created_at_desc|created_at_asc|title_asc)$"),
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Get paginated list of user's stories"""
    # Check rate limits
    await check_api_rate_limit_only(user_id)
    
    # Verify user can only access their own stories
    if current_user.user_id != str(user_id):
        raise HTTPException(status_code=403, detail="Can only access your own stories")
    
    # Build query conditions
    conditions = ["user_id = $1"]
    params = [user_id]
    param_count = 2
    
    if genre:
        conditions.append(f"genre = ${param_count}")
        params.append(genre.value)
        param_count += 1
    
    if favorited_only:
        conditions.append(f"is_favorited = ${param_count}")
        params.append(True)
        param_count += 1
    
    where_clause = " AND ".join(conditions)
    
    # Build sort clause
    sort_mapping = {
        "created_at_desc": "created_at DESC",
        "created_at_asc": "created_at ASC", 
        "title_asc": "title ASC"
    }
    order_clause = sort_mapping[sort]
    
    # Get total count
    count_result = await db.fetch_one(f"""
        SELECT COUNT(*) as total FROM user_stories WHERE {where_clause}
    """, *params)
    total_count = count_result["total"]
    
    # Get stories
    stories_data = await db.fetch_all(f"""
        SELECT * FROM user_stories 
        WHERE {where_clause}
        ORDER BY {order_clause}
        LIMIT ${param_count} OFFSET ${param_count + 1}
    """, *params, limit, offset)
    
    stories = []
    for story_data in stories_data:
        story_dict = parse_story_data(story_data)
        stories.append(UserStory(**story_dict))
    
    has_more = (offset + limit) < total_count
    
    return StoriesResponse(
        stories=stories,
        total_count=total_count,
        has_more=has_more
    )

@router.get("/users/{user_id}/stories/{story_id}", response_model=UserStory)
async def get_story(
    user_id: UUID,
    story_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Get a specific story"""
    # Check rate limits
    await check_api_rate_limit_only(user_id)
    
    # Verify user can only access their own stories
    if current_user.user_id != str(user_id):
        raise HTTPException(status_code=403, detail="Can only access your own stories")
    
    story_data = await db.fetch_one("""
        SELECT * FROM user_stories 
        WHERE id = $1 AND user_id = $2
    """, story_id, user_id)
    
    if not story_data:
        raise HTTPException(status_code=404, detail="Story not found")
    
    story_dict = parse_story_data(story_data)
    return UserStory(**story_dict)

@router.put("/users/{user_id}/stories/{story_id}/favorite")
async def toggle_story_favorite(
    user_id: UUID,
    story_id: UUID,
    request: StoryFavoriteRequest,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Toggle story favorite status"""
    # Check rate limits
    await check_api_rate_limit_only(user_id)
    
    # Verify user can only modify their own stories
    if current_user.user_id != str(user_id):
        raise HTTPException(status_code=403, detail="Can only modify your own stories")
    
    # Verify story exists and belongs to user
    story = await db.fetch_one("""
        SELECT id FROM user_stories 
        WHERE id = $1 AND user_id = $2
    """, story_id, user_id)
    
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    
    # Update favorite status
    await db.execute("""
        UPDATE user_stories 
        SET is_favorited = $1, updated_at = CURRENT_TIMESTAMP
        WHERE id = $2 AND user_id = $3
    """, request.is_favorited, story_id, user_id)
    
    return {
        "success": True,
        "is_favorited": request.is_favorited
    }

@router.delete("/users/{user_id}/stories/{story_id}")
async def delete_story(
    user_id: UUID,
    story_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Delete a story"""
    # Check rate limits
    await check_api_rate_limit_only(user_id)
    
    # Verify user can only delete their own stories
    if current_user.user_id != str(user_id):
        raise HTTPException(status_code=403, detail="Can only delete your own stories")
    
    # Verify story exists and belongs to user
    story = await db.fetch_one("""
        SELECT id FROM user_stories 
        WHERE id = $1 AND user_id = $2
    """, story_id, user_id)
    
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    
    # Delete story (this will also delete related generation logs due to CASCADE)
    await db.execute("""
        DELETE FROM user_stories 
        WHERE id = $1 AND user_id = $2
    """, story_id, user_id)
    
    return {
        "success": True,
        "message": "Story deleted successfully"
    }

@router.get("/users/{user_id}/stories/stats", response_model=StoryStatistics)
async def get_story_statistics(
    user_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Get user's story statistics"""
    # Check rate limits
    await check_api_rate_limit_only(user_id)
    
    # Verify user can only access their own stats
    if current_user.user_id != str(user_id):
        raise HTTPException(status_code=403, detail="Can only access your own statistics")
    
    # Get basic stats
    stats = await db.fetch_one("""
        SELECT 
            COUNT(*) as total_stories,
            COUNT(*) FILTER (WHERE is_favorited = true) as favorite_stories,
            COALESCE(SUM(word_count), 0) as total_words,
            COALESCE(SUM(dust_cost), 0) as dust_spent
        FROM user_stories 
        WHERE user_id = $1
    """, user_id)
    
    # Get genre breakdown
    genre_stats = await db.fetch_all("""
        SELECT genre, COUNT(*) as count
        FROM user_stories 
        WHERE user_id = $1
        GROUP BY genre
        ORDER BY count DESC
    """, user_id)
    
    genres_explored = [stat["genre"] for stat in genre_stats]
    most_common_genre = genre_stats[0]["genre"] if genre_stats else None
    
    # Get most common story length
    length_stats = await db.fetch_one("""
        SELECT story_length, COUNT(*) as count
        FROM user_stories 
        WHERE user_id = $1
        GROUP BY story_length
        ORDER BY count DESC
        LIMIT 1
    """, user_id)
    
    average_story_length = length_stats["story_length"] if length_stats else "medium"
    
    return StoryStatistics(
        total_stories=stats["total_stories"],
        favorite_stories=stats["favorite_stories"],
        total_words=stats["total_words"],
        genres_explored=genres_explored,
        most_common_genre=most_common_genre,
        dust_spent=stats["dust_spent"],
        average_story_length=average_story_length
    )