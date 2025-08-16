# services/content/fortune_routes.py
import json
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from models import (
    FortuneDeleteResponse,
    FortuneErrorResponse,
    FortuneFavoriteRequest,
    FortuneFavoriteResponse,
    FortuneGenerationRequest,
    FortuneGenerationResponse,
    FortuneHistoryResponse,
    FortuneProfileRequest,
    FortuneProfileResponse,
    FortuneReading,
    ReadingType,
    TokenUsage,
)

from shared.auth_middleware import TokenData, get_current_user
from shared.database import Database, get_db
from shared.llm_client import LLMError, llm_client
from shared.llm_usage_logger import create_request_metadata
from shared.uuid_utils import generate_uuid7

router = APIRouter()

# Constants
FORTUNE_RATE_LIMIT = 15  # Max 15 readings per hour per user

# Zodiac data
ZODIAC_SIGNS = {
    1: [("Capricorn", "Earth", "Saturn"), ("Aquarius", "Air", "Uranus")],
    2: [("Aquarius", "Air", "Uranus"), ("Pisces", "Water", "Neptune")],
    3: [("Pisces", "Water", "Neptune"), ("Aries", "Fire", "Mars")],
    4: [("Aries", "Fire", "Mars"), ("Taurus", "Earth", "Venus")],
    5: [("Taurus", "Earth", "Venus"), ("Gemini", "Air", "Mercury")],
    6: [("Gemini", "Air", "Mercury"), ("Cancer", "Water", "Moon")],
    7: [("Cancer", "Water", "Moon"), ("Leo", "Fire", "Sun")],
    8: [("Leo", "Fire", "Sun"), ("Virgo", "Earth", "Mercury")],
    9: [("Virgo", "Earth", "Mercury"), ("Libra", "Air", "Venus")],
    10: [("Libra", "Air", "Venus"), ("Scorpio", "Water", "Mars")],
    11: [("Scorpio", "Water", "Mars"), ("Sagittarius", "Fire", "Jupiter")],
    12: [("Sagittarius", "Fire", "Jupiter"), ("Capricorn", "Earth", "Saturn")],
}

ZODIAC_CUTOFFS = {
    1: 20,
    2: 19,
    3: 20,
    4: 20,
    5: 21,
    6: 21,
    7: 22,
    8: 23,
    9: 23,
    10: 23,
    11: 22,
    12: 21,
}


@router.post("/apps/fortune-teller/generate")
async def generate_fortune_reading(
    request: FortuneGenerationRequest,
    http_request: Request,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """
    Generate a personalized mystical fortune reading using AI and cosmic data.
    """
    print(f"🔮 FORTUNE: Starting generation for user {request.user_id}", flush=True)
    is_self_reading = request.target_person_id == request.user_id
    print(
        f"🔮 FORTUNE: Type: {request.reading_type}, Target: {request.target_person_id}, Self-reading: {is_self_reading}",
        flush=True,
    )

    # Verify user can only generate readings for themselves
    if current_user.user_id != str(request.user_id):
        print(
            f"🚨 FORTUNE: User {current_user.user_id} attempted to generate reading for different user {request.user_id}",
            flush=True,
        )
        return FortuneErrorResponse(error="Can only generate readings for yourself")

    try:
        # Extract Authorization header for service-to-service calls
        auth_token = http_request.headers.get("authorization", "")
        if not auth_token:
            return FortuneErrorResponse(error="Authorization header required")

        # Check rate limiting
        rate_limit_exceeded = await _check_rate_limit(db, request.user_id)
        if rate_limit_exceeded:
            return FortuneErrorResponse(
                error=f"Rate limit exceeded. Maximum {FORTUNE_RATE_LIMIT} readings per hour."
            )

        # Payment handled by frontend - content service focuses on content generation
        print("💰 FORTUNE: Payment handled by app - generating content", flush=True)

        # Calculate astrological data
        zodiac_sign, zodiac_element, ruling_planet = _calculate_zodiac(request.birth_date)
        life_path_number = _calculate_life_path_number(request.birth_date)

        # Calculate basic astrological data for prompts
        print(
            f"🌟 FORTUNE: Zodiac: {zodiac_sign} ({zodiac_element}), Life Path: {life_path_number}",
            flush=True,
        )

        # Generate fortune reading using LLM
        print("🤖 FORTUNE: Starting LLM generation", flush=True)
        try:
            result = await _generate_fortune_llm(
                request=request,
                zodiac_sign=zodiac_sign,
                zodiac_element=zodiac_element,
                ruling_planet=ruling_planet,
                life_path_number=life_path_number,
                auth_token=auth_token,
            )

            if not result:
                print("❌ FORTUNE: LLM generation failed", flush=True)
                return FortuneErrorResponse(
                    error="Failed to generate fortune reading. Please try again."
                )

            reading_content, generation_metadata = result
            provider_used = generation_metadata["provider"]
            model_used = generation_metadata["model_id"]
            tokens_used = generation_metadata["tokens_used"]
            cost = generation_metadata["cost_usd"]

            print("🤖 FORTUNE: Generated reading successfully", flush=True)

        except LLMError as e:
            print(f"❌ FORTUNE: LLM generation failed: {str(e)}", flush=True)
            return FortuneErrorResponse(
                error="Failed to generate fortune reading. Please try again."
            )
        except Exception as e:
            print(f"❌ FORTUNE: Unexpected error during generation: {str(e)}", flush=True)
            return FortuneErrorResponse(
                error="Failed to generate fortune reading. Please try again."
            )

        # Save reading to database
        # For self-readings, set target_person_id to NULL
        target_person_id = (
            None if request.target_person_id == request.user_id else request.target_person_id
        )

        reading_id = await _save_fortune_reading(
            db=db,
            user_id=request.user_id,
            target_person_id=target_person_id,
            target_person_name=request.name,
            reading_type=request.reading_type,
            question=request.question,
            content=reading_content,
            model_used=model_used,
            tokens_used=tokens_used,
            cost=cost,
        )

        print(f"✅ FORTUNE: Saved reading {reading_id}", flush=True)

        # Build response
        reading = FortuneReading(
            id=reading_id,
            content=reading_content,
            reading_type=request.reading_type,
            question=request.question,
            target_person_id=target_person_id,  # Use the processed target_person_id
            target_person_name=request.name,
            created_at=datetime.utcnow(),
            is_favorited=False,
        )

        return FortuneGenerationResponse(
            reading=reading,
            model_used=model_used,
            tokens_used=TokenUsage(
                prompt=tokens_used.get("prompt_tokens", 0),
                completion=tokens_used.get("completion_tokens", 0),
                total=tokens_used.get("total_tokens", 0),
            ),
            cost=cost,
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ FORTUNE: Unexpected error: {str(e)}", flush=True)
        return FortuneErrorResponse(error="Internal server error during fortune generation")


# Helper functions


async def _check_rate_limit(db: Database, user_id: UUID) -> bool:
    """Check if user has exceeded rate limit for fortune generation"""
    try:
        # Count generations in the last hour
        query = """
            SELECT COUNT(*) as generation_count
            FROM fortune_readings
            WHERE user_id = $1
            AND created_at > NOW() - INTERVAL '1 hour'
        """

        result = await db.fetch_one(query, user_id)
        generation_count = result["generation_count"] if result else 0

        if generation_count >= FORTUNE_RATE_LIMIT:
            print(
                f"⚠️ FORTUNE_RATE_LIMIT: User {user_id} exceeded rate limit: {generation_count}/{FORTUNE_RATE_LIMIT}",
                flush=True,
            )
            return True

        print(
            f"✅ FORTUNE_RATE_LIMIT: User {user_id} within limit: {generation_count}/{FORTUNE_RATE_LIMIT}",
            flush=True,
        )
        return False

    except Exception as e:
        print(f"❌ FORTUNE_RATE_LIMIT: Error checking rate limit: {str(e)}", flush=True)
        # Default to allowing if we can't check (fail open)
        return False


def _calculate_zodiac(birth_date: str) -> tuple[str, str, str]:
    """Calculate zodiac sign, element, and ruling planet from birth date"""
    try:
        birth_date_obj = datetime.strptime(birth_date, "%Y-%m-%d").date()
        month = birth_date_obj.month
        day = birth_date_obj.day

        # Get zodiac sign based on month and day
        if day <= ZODIAC_CUTOFFS[month]:
            # First sign of the month
            sign, element, planet = ZODIAC_SIGNS[month][0]
        else:
            # Second sign of the month
            sign, element, planet = ZODIAC_SIGNS[month][1]

        return sign, element, planet
    except Exception as e:
        print(f"❌ FORTUNE_ZODIAC: Error calculating zodiac: {str(e)}", flush=True)
        return "Unknown", "Unknown", "Unknown"


def _calculate_life_path_number(birth_date: str) -> int:
    """Calculate life path number from birth date using numerology"""
    try:
        # Remove dashes and sum all digits
        numbers = [int(d) for d in birth_date.replace("-", "")]
        total = sum(numbers)

        # Reduce to single digit (except master numbers 11, 22, 33)
        while total > 9 and total not in [11, 22, 33]:
            total = sum(int(d) for d in str(total))

        return total
    except Exception as e:
        print(f"❌ FORTUNE_NUMEROLOGY: Error calculating life path: {str(e)}", flush=True)
        return 1


# Removed cosmic influences - no longer needed for simplified fortune responses


# Removed lucky elements - no longer needed for simplified fortune responses


def _build_fortune_prompt(
    request: FortuneGenerationRequest,
    zodiac_sign: str,
    zodiac_element: str,
    ruling_planet: str,
    life_path_number: int,
) -> str:
    """Build the LLM prompt for fortune generation with distinct formats for different reading types"""

    # Build different prompts based on reading type
    if request.reading_type == ReadingType.DAILY:
        return _build_daily_fortune_prompt(
            request,
            zodiac_sign,
            zodiac_element,
            ruling_planet,
            life_path_number,
        )
    else:
        return _build_question_fortune_prompt(
            request,
            zodiac_sign,
            zodiac_element,
            ruling_planet,
            life_path_number,
        )


def _build_daily_fortune_prompt(
    request: FortuneGenerationRequest,
    zodiac_sign: str,
    zodiac_element: str,
    ruling_planet: str,
    life_path_number: int,
) -> str:
    """Build bite-sized daily fortune prompt (30-60 words)"""

    import random

    # Vary the fortune style randomly for more variety
    styles = [
        "mystical and intuitive",
        "practical and grounded",
        "playful and energetic",
        "wise and reflective",
        "bold and encouraging",
        "gentle and nurturing",
        "direct and confident",
        "poetic and inspiring",
    ]

    approaches = [
        "focus on an unexpected opportunity",
        "highlight a personal strength to embrace",
        "suggest a mindful action to take",
        "reveal a hidden blessing in today",
        "point to a connection worth nurturing",
        "encourage a creative breakthrough",
        "warn of a gentle challenge to overcome",
        "illuminate a moment of clarity ahead",
    ]

    tones = [
        "like a trusted friend giving advice",
        "like ancient wisdom speaking directly to them",
        "like a gentle nudge from the universe",
        "like cosmic energy flowing through words",
        "like their higher self offering guidance",
        "like a whisper from their intuition",
        "like the voice of their {zodiac_element} element",
        "like {ruling_planet} speaking through the stars",
    ]

    selected_style = random.choice(styles)
    selected_approach = random.choice(approaches)
    selected_tone = random.choice(tones)

    prompt = f"""Create a unique daily fortune for {request.name}, a {zodiac_sign} with life path {life_path_number}.

CREATIVE DIRECTION:
- Style: {selected_style}
- Approach: {selected_approach}
- Tone: {selected_tone}
- Element energy: {zodiac_element}

VARIATION REQUIREMENTS:
- 30-60 words maximum
- AVOID generic phrases like "embrace your", "trust your journey", "the universe aligns"
- BREAK THE MOLD: Use unexpected metaphors, fresh perspectives, or surprising insights
- VARY YOUR LANGUAGE: Sometimes poetic, sometimes conversational, sometimes mystical
- MAKE IT SPECIFIC: Reference concrete actions, emotions, or situations
- BE UNPREDICTABLE: Start with unusual openings, use different sentence structures

Examples of fresh approaches:
- "Your {zodiac_element} nature whispers secrets today..."
- "Life path {life_path_number} energy creates an opening for..."
- "Something shifts in your favor when you..."
- "Today's rhythm matches your {zodiac_sign} heartbeat..."
- "The space between thoughts holds your answer..."

CRITICAL: Return ONLY the fortune text itself. Do not include any explanations, commentary, or analysis about why the fortune is unique or how it avoids clichés. Just the fortune."""

    return prompt


def _build_question_fortune_prompt(
    request: FortuneGenerationRequest,
    zodiac_sign: str,
    zodiac_element: str,
    ruling_planet: str,
    life_path_number: int,
) -> str:
    """Build detailed question response prompt (100-200 words)"""

    import random

    # Add variety to question responses too
    response_styles = [
        "like a wise oracle revealing hidden truths",
        "like a cosmic counselor offering deep insight",
        "like ancient wisdom filtered through modern understanding",
        "like their spirit guides speaking through the stars",
        "like the universe answering through elemental wisdom",
        "like a mystical mentor who sees their soul clearly",
        "like cosmic forces aligning to offer guidance",
        "like their higher self speaking from the future",
    ]

    structural_approaches = [
        "Start with what their {zodiac_element} element reveals, then dive deeper",
        "Begin with their life path {life_path_number} lesson, then apply it specifically",
        "Open with a cosmic truth, then make it personal and actionable",
        "Start with their {zodiac_sign} strength, then address the challenge",
        "Begin with the energy around them now, then reveal the path forward",
        "Open with what {ruling_planet} is teaching them, then offer practical steps",
        "Start with a deeper truth about their question, then illuminate options",
        "Begin with their soul's perspective, then bridge to everyday reality",
    ]

    wisdom_angles = [
        "Focus on the hidden opportunity within their question",
        "Reveal the spiritual lesson their situation is teaching",
        "Illuminate the timing and cosmic patterns at play",
        "Explore how their past experiences inform this moment",
        "Examine the relationship dynamics and energy flows",
        "Uncover the fear or limiting belief that needs releasing",
        "Highlight their intuitive knowing they may be ignoring",
        "Show how this situation serves their highest growth",
    ]

    selected_style = random.choice(response_styles)
    selected_structure = random.choice(structural_approaches)
    selected_angle = random.choice(wisdom_angles)

    prompt = f"""Provide mystical guidance for {request.name}'s question: "{request.question}"

PERSON'S COSMIC BLUEPRINT:
- {zodiac_sign} ({zodiac_element} element, ruled by {ruling_planet})
- Life Path: {life_path_number}
- Birth: {request.birth_date}"""

    if request.birth_time:
        prompt += f"\n- Time: {request.birth_time}"

    if request.birth_location:
        prompt += f"\n- Location: {request.birth_location}"

    prompt += f"""

CREATIVE GUIDANCE FRAMEWORK:
- Response Style: {selected_style}
- Structure: {selected_structure}
- Wisdom Angle: {selected_angle}

VARIETY REQUIREMENTS:
- 100-200 words of meaningful insight
- AVOID CLICHÉS: No "everything happens for a reason", "trust the process", "follow your heart"
- FRESH LANGUAGE: Use unexpected metaphors, original insights, surprising perspectives
- SPECIFIC WISDOM: Connect their astrological profile to their exact situation
- AUTHENTIC VOICE: Sometimes mystical, sometimes direct, sometimes poetic
- PRACTICAL MAGIC: Bridge spiritual insight with actionable guidance

STRUCTURAL VARIETY:
- Try different openings: questions, statements, cosmic observations
- Vary paragraph structure: single flow vs. distinct sections
- Mix sentence lengths: short punchy insights with flowing wisdom
- End with different energies: empowerment, reflection, invitation, certainty

CRITICAL OUTPUT INSTRUCTION: Return ONLY the mystical guidance response itself. Do not include any explanations, commentary, analysis, or meta-discussion about the reading. No phrases like "This fortune avoids clichés by..." or "Here's why this is unique...". Just provide the pure fortune response."""

    return prompt


async def _get_llm_model_config() -> dict:
    """Get LLM model configuration for fortune-teller app using normalized structure"""
    from shared.app_config_cache import get_app_config_cache
    from shared.database import get_db
    from shared.json_utils import parse_jsonb_field

    app_slug = "fairydust-fortune-teller"

    # First, get the app UUID from the slug
    db = await get_db()
    app_result = await db.fetch_one("SELECT id FROM apps WHERE slug = $1", app_slug)

    if not app_result:
        # Return default config if app not found
        return {
            "primary_provider": "anthropic",
            "primary_model_id": "claude-3-5-sonnet-20241022",
            "primary_parameters": {"temperature": 0.8, "max_tokens": 400, "top_p": 0.9},
        }

    app_id = str(app_result["id"])

    # Try to get from cache first (cache still uses legacy format)
    cache = await get_app_config_cache()
    cached_config = await cache.get_model_config(app_id)

    if cached_config:
        return {
            "primary_provider": cached_config.get("primary_provider", "anthropic"),
            "primary_model_id": cached_config.get("primary_model_id", "claude-3-5-sonnet-20241022"),
            "primary_parameters": cached_config.get(
                "primary_parameters", {"temperature": 0.8, "max_tokens": 400, "top_p": 0.9}
            ),
        }

    # Cache miss - fetch from new normalized database structure
    try:
        db_config = await db.fetch_one(
            """
            SELECT provider, model_id, parameters FROM app_model_configs
            WHERE app_id = $1 AND model_type = 'text' AND is_enabled = true
            """,
            app_result["id"],
        )

        if db_config:
            # Parse parameters from JSONB field
            parameters = parse_jsonb_field(
                db_config["parameters"],
                default={"temperature": 0.8, "max_tokens": 400, "top_p": 0.9},
                field_name="text_parameters",
            )

            # Format as legacy structure for LLM client compatibility
            parsed_config = {
                "primary_provider": db_config["provider"],
                "primary_model_id": db_config["model_id"],
                "primary_parameters": parameters,
            }

            # Cache the database config in legacy format
            await cache.set_model_config(app_id, parsed_config)
            return parsed_config

    except Exception as e:
        print(f"⚠️ FORTUNE_CONFIG: Error loading normalized config: {e}")

    # Fallback to default config
    default_config = {
        "primary_provider": "anthropic",
        "primary_model_id": "claude-3-5-sonnet-20241022",
        "primary_parameters": {"temperature": 0.8, "max_tokens": 400, "top_p": 0.9},
    }

    # Cache the default config for future requests
    await cache.set_model_config(app_id, default_config)
    return default_config


async def _generate_fortune_llm(
    request: FortuneGenerationRequest,
    zodiac_sign: str,
    zodiac_element: str,
    ruling_planet: str,
    life_path_number: int,
    auth_token: str,
) -> Optional[tuple[str, dict]]:
    """Generate fortune reading using centralized LLM client"""
    try:
        # Build prompt
        full_prompt = _build_fortune_prompt(
            request,
            zodiac_sign,
            zodiac_element,
            ruling_planet,
            life_path_number,
        )

        # Get model configuration
        model_config = await _get_llm_model_config()

        # Create request metadata with proper action slug based on reading type
        action_slug = (
            "fortune-daily" if request.reading_type == ReadingType.DAILY else "fortune-question"
        )
        request_metadata = create_request_metadata(
            action=action_slug,
            parameters={
                "reading_type": request.reading_type.value,
                "zodiac_sign": zodiac_sign,
                "life_path_number": life_path_number,
                "has_question": bool(request.question),
                "has_birth_time": bool(request.birth_time),
                "has_birth_location": bool(request.birth_location),
            },
            user_context=f"Fortune reading for {request.name}",
            session_id=None,
        )

        # Use centralized LLM client which handles retries, fallbacks, and logging
        completion, generation_metadata = await llm_client.generate_completion(
            prompt=full_prompt,
            app_config=model_config,
            user_id=request.user_id,
            app_id="fairydust-fortune-teller",
            action=action_slug,
            request_metadata=request_metadata,
        )

        return completion, generation_metadata

    except LLMError as e:
        print(f"❌ FORTUNE_LLM: LLM client error: {str(e)}", flush=True)
        raise
    except Exception as e:
        print(f"❌ FORTUNE_LLM: Unexpected error generating fortune: {str(e)}", flush=True)
        raise


async def _save_fortune_reading(
    db: Database,
    user_id: UUID,
    target_person_id: Optional[UUID],
    target_person_name: str,
    reading_type: ReadingType,
    question: Optional[str],
    content: str,
    model_used: str,
    tokens_used: dict,
    cost: float,
) -> UUID:
    """Save fortune reading to database"""
    try:
        reading_id = generate_uuid7()

        metadata = {
            "model_used": model_used,
            "tokens_used": tokens_used.get("total_tokens", 0),
            "cost_usd": cost,
        }

        insert_query = """
            INSERT INTO fortune_readings (
                id, user_id, target_person_id, target_person_name, reading_type,
                question, content, metadata, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """

        await db.execute(
            insert_query,
            reading_id,
            user_id,
            target_person_id,
            target_person_name,
            reading_type.value,
            question,
            content,
            json.dumps(metadata),
        )

        print(f"✅ FORTUNE_SAVE: Saved reading {reading_id}", flush=True)
        return reading_id

    except Exception as e:
        print(f"❌ FORTUNE_SAVE: Error saving reading: {str(e)}", flush=True)
        raise HTTPException(status_code=500, detail="Failed to save fortune reading")


@router.get("/users/{user_id}/fortune-readings")
async def get_user_fortune_readings(
    user_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
    limit: int = Query(20, ge=1, le=50, description="Number of results to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    favorites_only: bool = Query(False, description="Return only favorited readings"),
):
    """
    Retrieve all saved fortune readings for a user, sorted by favorites first, then creation date descending.
    """
    print(f"🔮 FORTUNE_HISTORY: Getting readings for user {user_id}", flush=True)

    # Verify user can only access their own readings
    if current_user.user_id != str(user_id):
        print(
            f"🚨 FORTUNE_HISTORY: User {current_user.user_id} attempted to access readings for different user {user_id}",
            flush=True,
        )
        return FortuneErrorResponse(error="Can only access your own fortune readings")

    try:
        # Build query with filters
        base_query = """
            SELECT id, content, reading_type, question, target_person_id, target_person_name,
                   is_favorited, created_at
            FROM fortune_readings
            WHERE user_id = $1
        """
        params = [user_id]

        if favorites_only:
            base_query += " AND is_favorited = TRUE"

        # Order by favorites first, then creation date descending
        base_query += " ORDER BY is_favorited DESC, created_at DESC"

        # Add pagination
        base_query += f" LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}"
        params.extend([limit, offset])

        # Execute query
        rows = await db.fetch_all(base_query, *params)

        # Get total counts
        count_query = """
            SELECT
                COUNT(*) as total_count,
                COUNT(*) FILTER (WHERE is_favorited = TRUE) as favorites_count
            FROM fortune_readings
            WHERE user_id = $1
        """

        count_result = await db.fetch_one(count_query, user_id)
        total_count = count_result["total_count"] if count_result else 0
        favorites_count = count_result["favorites_count"] if count_result else 0

        # Build response
        readings = []
        for row in rows:
            reading = FortuneReading(
                id=row["id"],
                content=row["content"],
                reading_type=ReadingType(row["reading_type"]),
                question=row["question"],
                target_person_id=row["target_person_id"],
                target_person_name=row["target_person_name"],
                created_at=row["created_at"],
                is_favorited=row["is_favorited"],
            )
            readings.append(reading)

        print(f"✅ FORTUNE_HISTORY: Returning {len(readings)} readings", flush=True)

        return FortuneHistoryResponse(
            readings=readings,
            total_count=total_count,
            favorites_count=favorites_count,
        )

    except Exception as e:
        print(f"❌ FORTUNE_HISTORY: Error getting readings: {str(e)}", flush=True)
        return FortuneErrorResponse(error="Failed to retrieve fortune readings")


@router.patch("/users/{user_id}/people/{person_id}/fortune-profile")
async def update_person_fortune_profile(
    user_id: UUID,
    person_id: UUID,
    request: FortuneProfileRequest,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """
    Update fortune profile data for a person in user's life.
    """
    print(f"🔮 FORTUNE_PROFILE: Updating profile for person {person_id}", flush=True)

    # Verify user can only modify their own people
    if current_user.user_id != str(user_id):
        print(
            f"🚨 FORTUNE_PROFILE: User {current_user.user_id} attempted to update profile for different user {user_id}",
            flush=True,
        )
        return FortuneErrorResponse(error="Can only update profiles for your own people")

    try:
        # Calculate astrological data
        zodiac_sign, zodiac_element, ruling_planet = _calculate_zodiac(request.birth_date)
        life_path_number = _calculate_life_path_number(request.birth_date)

        # Build fortune profile data
        fortune_profile = {
            "birth_date": request.birth_date,
            "birth_time": request.birth_time,
            "birth_location": request.birth_location,
            "zodiac_sign": zodiac_sign,
            "zodiac_element": zodiac_element,
            "ruling_planet": ruling_planet,
            "life_path_number": life_path_number,
            "gender": request.gender,
        }

        # Update person's profile data with fortune information
        update_query = """
            INSERT INTO person_profile_data (person_id, user_id, category, field_name, field_value, source, updated_at)
            VALUES ($1, $2, 'fortune', 'fortune_profile', $3::jsonb, 'user_input', CURRENT_TIMESTAMP)
            ON CONFLICT (person_id, field_name)
            DO UPDATE SET
                field_value = EXCLUDED.field_value,
                source = EXCLUDED.source,
                updated_at = CURRENT_TIMESTAMP
        """

        await db.execute(update_query, person_id, user_id, json.dumps(fortune_profile))

        # Get updated person data
        person_query = """
            SELECT piml.id, piml.name, piml.relationship, piml.birth_date,
                   ppd.field_value as fortune_profile
            FROM people_in_my_life piml
            LEFT JOIN person_profile_data ppd ON piml.id = ppd.person_id
                AND ppd.field_name = 'fortune_profile'
            WHERE piml.id = $1 AND piml.user_id = $2
        """

        person_result = await db.fetch_one(person_query, person_id, user_id)

        if not person_result:
            return FortuneErrorResponse(error="Person not found")

        # Build response
        person_data = {
            "id": str(person_result["id"]),
            "name": person_result["name"],
            "relationship": person_result["relationship"],
            "birth_date": str(person_result["birth_date"]) if person_result["birth_date"] else None,
            "fortune_profile": json.loads(person_result["fortune_profile"])
            if person_result["fortune_profile"]
            else None,
        }

        print(f"✅ FORTUNE_PROFILE: Updated profile for person {person_id}", flush=True)

        return FortuneProfileResponse(person=person_data)

    except Exception as e:
        print(f"❌ FORTUNE_PROFILE: Error updating profile: {str(e)}", flush=True)
        return FortuneErrorResponse(error="Failed to update fortune profile")


@router.post(
    "/users/{user_id}/fortune-readings/{reading_id}/favorite",
)
async def toggle_fortune_reading_favorite(
    user_id: UUID,
    reading_id: UUID,
    request: FortuneFavoriteRequest,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """
    Toggle the favorite status of a saved fortune reading.
    """
    print(
        f"⭐ FORTUNE_FAVORITE: Toggling favorite for reading {reading_id} to {request.is_favorited}",
        flush=True,
    )

    # Verify user can only modify their own readings
    if current_user.user_id != str(user_id):
        print(
            f"🚨 FORTUNE_FAVORITE: User {current_user.user_id} attempted to modify reading for different user {user_id}",
            flush=True,
        )
        return FortuneErrorResponse(error="Can only modify your own fortune readings")

    try:
        # Update favorite status
        update_query = """
            UPDATE fortune_readings
            SET is_favorited = $1, updated_at = CURRENT_TIMESTAMP
            WHERE id = $2 AND user_id = $3
            RETURNING id, content, reading_type, question, target_person_id, target_person_name,
                      is_favorited, created_at
        """

        result = await db.fetch_one(update_query, request.is_favorited, reading_id, user_id)

        if not result:
            return FortuneErrorResponse(error="Fortune reading not found", reading_id=reading_id)

        reading = FortuneReading(
            id=result["id"],
            content=result["content"],
            reading_type=ReadingType(result["reading_type"]),
            question=result["question"],
            target_person_id=result["target_person_id"],
            target_person_name=result["target_person_name"],
            created_at=result["created_at"],
            is_favorited=result["is_favorited"],
        )

        print(f"✅ FORTUNE_FAVORITE: Updated favorite status for reading {reading_id}", flush=True)

        return FortuneFavoriteResponse(reading=reading)

    except Exception as e:
        print(f"❌ FORTUNE_FAVORITE: Error updating favorite: {str(e)}", flush=True)
        return FortuneErrorResponse(error="Failed to update favorite status")


@router.delete(
    "/users/{user_id}/fortune-readings/{reading_id}",
)
async def delete_fortune_reading(
    user_id: UUID,
    reading_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """
    Remove a saved fortune reading from user's collection (hard delete).
    """
    print(f"🗑️ FORTUNE_DELETE: Deleting reading {reading_id}", flush=True)

    # Verify user can only delete their own readings
    if current_user.user_id != str(user_id):
        print(
            f"🚨 FORTUNE_DELETE: User {current_user.user_id} attempted to delete reading for different user {user_id}",
            flush=True,
        )
        return FortuneErrorResponse(error="Can only delete your own fortune readings")

    try:
        # Hard delete the reading
        delete_query = """
            DELETE FROM fortune_readings
            WHERE id = $1 AND user_id = $2
        """

        result = await db.execute(delete_query, reading_id, user_id)

        # Check if any rows were affected
        if "DELETE 0" in result:
            return FortuneErrorResponse(error="Fortune reading not found", reading_id=reading_id)

        print(f"✅ FORTUNE_DELETE: Deleted reading {reading_id}", flush=True)

        return FortuneDeleteResponse()

    except Exception as e:
        print(f"❌ FORTUNE_DELETE: Error deleting reading: {str(e)}", flush=True)
        return FortuneErrorResponse(error="Failed to delete fortune reading")
