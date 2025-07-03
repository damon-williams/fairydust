# services/content/fortune_routes.py
import json
import os
import uuid
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from models import (
    CosmicInfluences,
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
    LuckyElements,
    ReadingType,
    TokenUsage,
)

from shared.auth_middleware import TokenData, get_current_user
from shared.database import Database, get_db
from shared.llm_pricing import calculate_llm_cost
from shared.llm_usage_logger import calculate_prompt_hash, create_request_metadata, log_llm_usage

router = APIRouter()

# Constants
FORTUNE_RATE_LIMIT = 15  # Max 15 readings per hour per user
FREE_ASTROLOGY_API_KEY = os.getenv(
    "FREE_ASTROLOGY_API_KEY", "UEhzlTAEY72bFez65JR7w51hOiAWwb7l94M6yHyr"
)
FREE_ASTROLOGY_API_URL = "https://freeastrologyapi.com"  # Remove 'api.' prefix

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


@router.post("/apps/fortune-teller/generate", response_model=FortuneGenerationResponse)
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

        # Get cosmic influences with real astrological data
        cosmic_influences = await _get_cosmic_influences(
            zodiac_sign,
            life_path_number,
            request.birth_date,
            request.birth_time,
            request.birth_location,
        )

        # Generate lucky elements
        lucky_elements = _generate_lucky_elements(zodiac_sign, zodiac_element, life_path_number)

        # Generate fortune reading using LLM
        print("🤖 FORTUNE: Starting LLM generation", flush=True)
        (
            reading_content,
            provider_used,
            model_used,
            tokens_used,
            cost,
            latency_ms,
        ) = await _generate_fortune_llm(
            request=request,
            zodiac_sign=zodiac_sign,
            zodiac_element=zodiac_element,
            ruling_planet=ruling_planet,
            life_path_number=life_path_number,
            cosmic_influences=cosmic_influences,
            lucky_elements=lucky_elements,
        )

        if not reading_content:
            print("❌ FORTUNE: LLM generation failed", flush=True)
            return FortuneErrorResponse(
                error="Failed to generate fortune reading. Please try again."
            )

        print("🤖 FORTUNE: Generated reading successfully", flush=True)

        # Log LLM usage for analytics
        try:
            # Calculate prompt hash for the fortune generation
            full_prompt = _build_fortune_prompt(
                request,
                zodiac_sign,
                zodiac_element,
                ruling_planet,
                life_path_number,
                cosmic_influences,
                lucky_elements,
            )
            prompt_hash = calculate_prompt_hash(full_prompt)

            # Create request metadata
            request_metadata = create_request_metadata(
                action="fortune_generation",
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

            # Log usage asynchronously
            await log_llm_usage(
                user_id=request.user_id,
                app_id="fairydust-fortune-teller",
                provider=provider_used,
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
            print(f"⚠️ FORTUNE: Failed to log LLM usage: {str(e)}", flush=True)

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
            cosmic_influences=cosmic_influences,
            lucky_elements=lucky_elements,
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
            target_person_name=request.name,
            cosmic_influences=cosmic_influences,
            lucky_elements=lucky_elements,
            created_at=datetime.utcnow(),
            is_favorited=False,
        )

        return FortuneGenerationResponse(
            reading=reading,
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
        print(f"❌ FORTUNE: Unexpected error: {str(e)}", flush=True)
        return FortuneErrorResponse(error="Internal server error during fortune generation")


# Helper functions


async def _get_planetary_positions(
    birth_date: str, birth_time: str = None, birth_location: str = None
) -> dict:
    """Get planetary positions from Free Astrology API"""
    try:
        # TODO: For dynamic moon phases, we should use current date instead of birth date
        # For now, using birth date for planetary positions at birth
        # Consider adding a separate call for current planetary positions

        # Convert birth_date to required format
        birth_date_obj = datetime.strptime(birth_date, "%Y-%m-%d")

        # Prepare API request data
        api_data = {
            "year": birth_date_obj.year,
            "month": birth_date_obj.month,
            "date": birth_date_obj.day,
            "hour": 12,  # Default to noon if no time provided
            "min": 0,
            "lat": 40.7128,  # Default to NYC coordinates
            "lon": -74.0060,
            "tzone": -5.0,  # EST timezone
        }

        # Use birth_time if provided
        if birth_time:
            try:
                time_parts = birth_time.split(":")
                api_data["hour"] = int(time_parts[0])
                api_data["min"] = int(time_parts[1])
            except:
                pass  # Use default time if parsing fails

        # Note: birth_location would require geocoding to get lat/lon
        # For now, using default coordinates

        async with httpx.AsyncClient() as client:
            print(
                f"🌟 ASTROLOGY_API: Making request to {FREE_ASTROLOGY_API_URL}/api/v1/western-horoscope/planets",
                flush=True,
            )
            print(f"🌟 ASTROLOGY_API: Request data: {api_data}", flush=True)
            print(
                f"🌟 ASTROLOGY_API: Using API key: {FREE_ASTROLOGY_API_KEY[:10]}...{FREE_ASTROLOGY_API_KEY[-4:]}",
                flush=True,
            )

            response = await client.post(
                f"{FREE_ASTROLOGY_API_URL}/api/v1/western-horoscope/planets",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {FREE_ASTROLOGY_API_KEY}",  # Added auth header
                },
                json=api_data,
                timeout=10.0,
            )

            if response.status_code == 200:
                data = response.json()
                print("✅ ASTROLOGY_API: Got planetary data successfully", flush=True)
                print(f"🌟 ASTROLOGY_API: Response preview: {str(data)[:200]}...", flush=True)
                return _parse_planetary_data(data)
            else:
                print(f"❌ ASTROLOGY_API: Error {response.status_code}: {response.text}", flush=True)
                print(f"❌ ASTROLOGY_API: Full response headers: {response.headers}", flush=True)
                return {"planets": {}, "moon_phase": "Full Moon"}

    except Exception as e:
        print(f"❌ ASTROLOGY_API: Exception getting planetary data: {str(e)}", flush=True)
        return {"planets": {}, "moon_phase": "Full Moon"}


def _parse_planetary_data(api_response: dict) -> dict:
    """Parse Free Astrology API response to extract useful data"""
    try:
        print(
            f"🔍 ASTROLOGY_PARSE: Parsing response with keys: {list(api_response.keys())}",
            flush=True,
        )
        planets = {}
        moon_phase = "Full Moon"

        # Extract planetary positions from API response
        if "planets" in api_response:
            print(
                f"🔍 ASTROLOGY_PARSE: Found {len(api_response['planets'])} planets in response",
                flush=True,
            )
            for i, planet_data in enumerate(api_response["planets"]):
                planet_name = planet_data.get("name", "")
                planet_sign = planet_data.get("current_sign", "")
                is_retrograde = planet_data.get("isRetro", False)

                print(
                    f"🪐 ASTROLOGY_PARSE: Planet {i+1}: {planet_name} in {planet_sign} (retrograde: {is_retrograde})",
                    flush=True,
                )

                planets[planet_name] = {
                    "sign": planet_sign,
                    "retrograde": is_retrograde,
                    "position": planet_data.get("fullDegree", 0),
                }

                # Special handling for Moon to determine phase
                if planet_name.lower() == "moon":
                    moon_degree = planet_data.get("fullDegree", 0)
                    moon_phase = _calculate_moon_phase(moon_degree)
                    print(f"🌙 ASTROLOGY_PARSE: Moon at {moon_degree}° = {moon_phase}", flush=True)
        else:
            print("⚠️ ASTROLOGY_PARSE: No 'planets' key in API response", flush=True)

        print(
            f"✅ ASTROLOGY_PARSE: Parsed {len(planets)} planets, moon phase: {moon_phase}",
            flush=True,
        )
        return {"planets": planets, "moon_phase": moon_phase}

    except Exception as e:
        print(f"❌ ASTROLOGY_API: Error parsing planetary data: {str(e)}", flush=True)
        return {"planets": {}, "moon_phase": "Full Moon"}


def _determine_strongest_planetary_influence(planets: dict) -> str:
    """Determine which planet has the strongest current influence"""
    try:
        # Priority order for planetary influences in fortune telling
        priority_planets = ["Sun", "Moon", "Mars", "Venus", "Jupiter", "Saturn", "Mercury"]

        for planet in priority_planets:
            if planet in planets:
                planet_data = planets[planet]
                # Consider retrograde planets as having stronger influence
                if planet_data.get("retrograde", False):
                    return f"{planet} (retrograde)"
                return planet

        # Default fallback
        return "Jupiter"

    except Exception as e:
        print(f"❌ ASTROLOGY_API: Error determining strongest influence: {str(e)}", flush=True)
        return "Jupiter"


def _calculate_moon_phase(moon_degree: float) -> str:
    """Calculate moon phase based on lunar degree position"""
    try:
        # Simple moon phase calculation based on degree
        # This is a simplified approach - real moon phase needs Sun-Moon angle
        phases = [
            "New Moon",
            "Waxing Crescent",
            "First Quarter",
            "Waxing Gibbous",
            "Full Moon",
            "Waning Gibbous",
            "Last Quarter",
            "Waning Crescent",
        ]

        # Divide 360 degrees by 8 phases
        phase_index = int(moon_degree / 45) % 8
        return phases[phase_index]

    except Exception as e:
        print(f"❌ ASTROLOGY_API: Error calculating moon phase: {str(e)}", flush=True)
        return "Full Moon"


async def _check_rate_limit(db: Database, user_id: uuid.UUID) -> bool:
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


async def _get_cosmic_influences(
    zodiac_sign: str,
    life_path_number: int,
    birth_date: str,
    birth_time: str = None,
    birth_location: str = None,
) -> CosmicInfluences:
    """Get current cosmic influences using real astrological data"""
    try:
        print(
            f"🌌 COSMIC: Getting cosmic influences for {zodiac_sign}, birth: {birth_date}",
            flush=True,
        )

        # Get real planetary positions from Free Astrology API
        planetary_data = await _get_planetary_positions(birth_date, birth_time, birth_location)

        # Extract moon phase and planetary focus from real data
        moon_phase = planetary_data.get("moon_phase", "Full Moon")
        print(f"🌙 COSMIC: Moon phase from API: {moon_phase}", flush=True)

        # Determine strongest planetary influence based on current positions
        planets = planetary_data.get("planets", {})
        print(f"🪐 COSMIC: Got {len(planets)} planets from API", flush=True)
        strongest_planet = _determine_strongest_planetary_influence(planets)
        print(f"💫 COSMIC: Strongest planetary influence: {strongest_planet}", flush=True)

        planetary_focus = f"{strongest_planet} influences your cosmic energy"

        result = CosmicInfluences(
            zodiac_sign=zodiac_sign,
            moon_phase=moon_phase,
            planetary_focus=planetary_focus,
            life_path_number=life_path_number,
        )
        print(
            f"✅ COSMIC: Returning cosmic influences with moon: {moon_phase}, planet: {strongest_planet}",
            flush=True,
        )
        return result
    except Exception as e:
        print(f"❌ FORTUNE_COSMIC: Error getting cosmic influences: {str(e)}", flush=True)
        # Fallback to basic data if API fails
        return CosmicInfluences(
            zodiac_sign=zodiac_sign,
            moon_phase="Full Moon",
            planetary_focus="Jupiter brings good fortune",
            life_path_number=life_path_number,
        )


def _generate_lucky_elements(
    zodiac_sign: str, zodiac_element: str, life_path_number: int
) -> LuckyElements:
    """Generate lucky elements based on astrological data"""
    # Element-based lucky colors
    element_colors = {
        "Fire": ["Red", "Orange", "Gold", "Crimson"],
        "Earth": ["Brown", "Green", "Beige", "Forest Green"],
        "Air": ["Yellow", "Silver", "Light Blue", "White"],
        "Water": ["Blue", "Purple", "Teal", "Deep Blue"],
    }

    # Element-based gemstones
    element_gemstones = {
        "Fire": ["Ruby", "Carnelian", "Garnet", "Amber"],
        "Earth": ["Emerald", "Jade", "Peridot", "Moss Agate"],
        "Air": ["Sapphire", "Aquamarine", "Citrine", "Clear Quartz"],
        "Water": ["Amethyst", "Moonstone", "Pearl", "Lapis Lazuli"],
    }

    # Get colors and gemstones for this element
    colors = element_colors.get(zodiac_element, ["Purple"])
    gemstones = element_gemstones.get(zodiac_element, ["Amethyst"])

    # Select based on life path number
    color = colors[life_path_number % len(colors)]
    gemstone = gemstones[life_path_number % len(gemstones)]

    return LuckyElements(
        color=color, number=life_path_number, element=zodiac_element, gemstone=gemstone
    )


def _build_fortune_prompt(
    request: FortuneGenerationRequest,
    zodiac_sign: str,
    zodiac_element: str,
    ruling_planet: str,
    life_path_number: int,
    cosmic_influences: CosmicInfluences,
    lucky_elements: LuckyElements,
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
            cosmic_influences,
            lucky_elements,
        )
    else:
        return _build_question_fortune_prompt(
            request,
            zodiac_sign,
            zodiac_element,
            ruling_planet,
            life_path_number,
            cosmic_influences,
            lucky_elements,
        )


def _build_daily_fortune_prompt(
    request: FortuneGenerationRequest,
    zodiac_sign: str,
    zodiac_element: str,
    ruling_planet: str,
    life_path_number: int,
    cosmic_influences: CosmicInfluences,
    lucky_elements: LuckyElements,
) -> str:
    """Build bite-sized daily fortune prompt (30-60 words)"""

    prompt = f"""Create a bite-sized daily fortune for {request.name}.

PERSON'S PROFILE:
- Zodiac: {zodiac_sign} ({zodiac_element} element)
- Life Path: {life_path_number}
- Today's Moon: {cosmic_influences.moon_phase}
- Cosmic Focus: {cosmic_influences.planetary_focus}
- Lucky Color: {lucky_elements.color}
- Lucky Number: {lucky_elements.number}

DAILY FORTUNE REQUIREMENTS:
- Length: 30-60 words maximum (bite-sized like a fortune cookie, but slightly longer)
- Focus on today's energy and opportunities
- Include one lucky element naturally
- Be positive, actionable, and specific
- Sound authentic and personal
- Skip flowery language - be direct and impactful

Write a concise daily fortune that captures today's cosmic energy for this {zodiac_sign}."""

    return prompt


def _build_question_fortune_prompt(
    request: FortuneGenerationRequest,
    zodiac_sign: str,
    zodiac_element: str,
    ruling_planet: str,
    life_path_number: int,
    cosmic_influences: CosmicInfluences,
    lucky_elements: LuckyElements,
) -> str:
    """Build detailed question response prompt (100-200 words)"""

    prompt = f"""Answer this question with mystical wisdom for {request.name}: "{request.question}"

PERSON'S MYSTICAL PROFILE:
- Name: {request.name}
- Birth Date: {request.birth_date}
- Zodiac Sign: {zodiac_sign} ({zodiac_element} element, ruled by {ruling_planet})
- Life Path Number: {life_path_number}
- Current Moon Phase: {cosmic_influences.moon_phase}
- Planetary Influence: {cosmic_influences.planetary_focus}

LUCKY ELEMENTS:
- Color: {lucky_elements.color}
- Number: {lucky_elements.number}
- Element: {lucky_elements.element}
- Gemstone: {lucky_elements.gemstone}"""

    if request.birth_time:
        prompt += f"\n- Birth Time: {request.birth_time}"

    if request.birth_location:
        prompt += f"\n- Birth Location: {request.birth_location}"

    prompt += f"""

QUESTION RESPONSE REQUIREMENTS:
- Length: 100-200 words for detailed guidance
- Address their specific question directly
- Weave in their {zodiac_sign} traits and {zodiac_element} element energy
- Reference their life path {life_path_number} characteristics
- Include current cosmic influences ({cosmic_influences.moon_phase}, {cosmic_influences.planetary_focus})
- Mention lucky elements naturally in your guidance
- Provide actionable wisdom and specific insights
- Be mystical yet practical

Give a thoughtful response that uses their astrological and numerological profile to answer their question."""

    return prompt


async def _get_llm_model_config() -> dict:
    """Get LLM model configuration for fortune-teller app"""
    from shared.app_config_cache import get_app_config_cache

    cache = await get_app_config_cache()
    config = await cache.get_model_config("fairydust-fortune-teller")

    if config:
        return config

    # Default configuration for fortune-teller
    default_config = {
        "primary_provider": "anthropic",
        "primary_model_id": "claude-3-5-sonnet-20241022",
        "primary_parameters": {"temperature": 0.8, "max_tokens": 400, "top_p": 0.9},
    }

    await cache.set_model_config("fairydust-fortune-teller", default_config)
    return default_config


async def _generate_fortune_llm(
    request: FortuneGenerationRequest,
    zodiac_sign: str,
    zodiac_element: str,
    ruling_planet: str,
    life_path_number: int,
    cosmic_influences: CosmicInfluences,
    lucky_elements: LuckyElements,
) -> tuple[Optional[str], str, str, dict, float, int]:
    """Generate fortune reading using LLM"""
    try:
        # Build prompt
        full_prompt = _build_fortune_prompt(
            request,
            zodiac_sign,
            zodiac_element,
            ruling_planet,
            life_path_number,
            cosmic_influences,
            lucky_elements,
        )

        # Get model configuration
        model_config = await _get_llm_model_config()
        provider = model_config.get("primary_provider", "anthropic")
        model_id = model_config.get("primary_model_id", "claude-3-5-sonnet-20241022")
        parameters = model_config.get("primary_parameters", {})

        max_tokens = parameters.get("max_tokens", 400)
        temperature = parameters.get("temperature", 0.8)
        top_p = parameters.get("top_p", 0.9)

        print(f"🤖 FORTUNE_LLM: Generating with {provider} {model_id}", flush=True)

        # Make API call based on provider
        start_time = datetime.now()
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
                        "messages": [{"role": "user", "content": full_prompt}],
                    },
                )
            elif provider == "openai":
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY', '')}",
                    },
                    json={
                        "model": model_id,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                        "top_p": top_p,
                        "messages": [{"role": "user", "content": full_prompt}],
                    },
                )
            else:
                print(
                    f"⚠️ FORTUNE_LLM: Unsupported provider {provider}, falling back to Anthropic",
                    flush=True,
                )
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "Content-Type": "application/json",
                        "x-api-key": os.getenv("ANTHROPIC_API_KEY", ""),
                        "anthropic-version": "2023-06-01",
                    },
                    json={
                        "model": "claude-3-5-sonnet-20241022",
                        "max_tokens": 400,
                        "temperature": 0.8,
                        "top_p": 0.9,
                        "messages": [{"role": "user", "content": full_prompt}],
                    },
                )

        latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        if response.status_code == 200:
            result = response.json()

            # Handle different response formats based on provider
            if provider == "anthropic":
                content = result["content"][0]["text"].strip()
                usage = result.get("usage", {})
                prompt_tokens = usage.get("input_tokens", 0)
                completion_tokens = usage.get("output_tokens", 0)
            elif provider == "openai":
                content = result["choices"][0]["message"]["content"].strip()
                usage = result.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
            else:
                # Fallback case
                content = result["content"][0]["text"].strip()
                usage = result.get("usage", {})
                prompt_tokens = usage.get("input_tokens", 0)
                completion_tokens = usage.get("output_tokens", 0)

            total_tokens = prompt_tokens + completion_tokens

            tokens_used = {
                "prompt": prompt_tokens,
                "completion": completion_tokens,
                "total": total_tokens,
            }

            cost = calculate_llm_cost(provider, model_id, prompt_tokens, completion_tokens)

            print("✅ FORTUNE_LLM: Generated fortune successfully", flush=True)
            return content, provider, model_id, tokens_used, cost, latency_ms

        else:
            print(
                f"❌ FORTUNE_LLM: {provider} API error {response.status_code}: {response.text}",
                flush=True,
            )
            return None, provider, model_id, {}, 0.0, latency_ms

    except Exception as e:
        print(f"❌ FORTUNE_LLM: Error generating fortune: {str(e)}", flush=True)
        return None, "anthropic", "claude-3-5-sonnet-20241022", {}, 0.0, 0


async def _save_fortune_reading(
    db: Database,
    user_id: uuid.UUID,
    target_person_id: Optional[uuid.UUID],
    target_person_name: str,
    reading_type: ReadingType,
    question: Optional[str],
    content: str,
    cosmic_influences: CosmicInfluences,
    lucky_elements: LuckyElements,
    model_used: str,
    tokens_used: dict,
    cost: float,
) -> uuid.UUID:
    """Save fortune reading to database"""
    try:
        reading_id = uuid.uuid4()

        metadata = {
            "model_used": model_used,
            "tokens_used": tokens_used.get("total", 0),
            "cost_usd": cost,
            "cosmic_influences": cosmic_influences.dict(),
            "lucky_elements": lucky_elements.dict(),
        }

        insert_query = """
            INSERT INTO fortune_readings (
                id, user_id, target_person_id, target_person_name, reading_type,
                question, content, cosmic_influences, lucky_elements, metadata,
                created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10::jsonb,
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
            json.dumps(cosmic_influences.dict()),
            json.dumps(lucky_elements.dict()),
            json.dumps(metadata),
        )

        print(f"✅ FORTUNE_SAVE: Saved reading {reading_id}", flush=True)
        return reading_id

    except Exception as e:
        print(f"❌ FORTUNE_SAVE: Error saving reading: {str(e)}", flush=True)
        raise HTTPException(status_code=500, detail="Failed to save fortune reading")


@router.get("/users/{user_id}/fortune-readings", response_model=FortuneHistoryResponse)
async def get_user_fortune_readings(
    user_id: uuid.UUID,
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
            SELECT id, content, reading_type, question, target_person_name,
                   cosmic_influences, lucky_elements, is_favorited, created_at
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
            # Parse JSONB fields
            cosmic_influences = CosmicInfluences(**json.loads(row["cosmic_influences"]))
            lucky_elements = LuckyElements(**json.loads(row["lucky_elements"]))

            reading = FortuneReading(
                id=row["id"],
                content=row["content"],
                reading_type=ReadingType(row["reading_type"]),
                question=row["question"],
                target_person_name=row["target_person_name"],
                cosmic_influences=cosmic_influences,
                lucky_elements=lucky_elements,
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


@router.patch(
    "/users/{user_id}/people/{person_id}/fortune-profile", response_model=FortuneProfileResponse
)
async def update_person_fortune_profile(
    user_id: uuid.UUID,
    person_id: uuid.UUID,
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
    response_model=FortuneFavoriteResponse,
)
async def toggle_fortune_reading_favorite(
    user_id: uuid.UUID,
    reading_id: uuid.UUID,
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
            RETURNING id, content, reading_type, question, target_person_name,
                      cosmic_influences, lucky_elements, is_favorited, created_at
        """

        result = await db.fetch_one(update_query, request.is_favorited, reading_id, user_id)

        if not result:
            return FortuneErrorResponse(error="Fortune reading not found", reading_id=reading_id)

        # Parse JSONB fields
        cosmic_influences = CosmicInfluences(**json.loads(result["cosmic_influences"]))
        lucky_elements = LuckyElements(**json.loads(result["lucky_elements"]))

        reading = FortuneReading(
            id=result["id"],
            content=result["content"],
            reading_type=ReadingType(result["reading_type"]),
            question=result["question"],
            target_person_name=result["target_person_name"],
            cosmic_influences=cosmic_influences,
            lucky_elements=lucky_elements,
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
    response_model=FortuneDeleteResponse,
)
async def delete_fortune_reading(
    user_id: uuid.UUID,
    reading_id: uuid.UUID,
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
