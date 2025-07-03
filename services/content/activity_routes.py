# services/content/activity_routes.py
import json
import os
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from models import (
    Activity,
    ActivitySearchMetadata,
    ActivitySearchRequest,
    ActivitySearchResponse,
    ActivityType,
)
from tripadvisor_service import TripAdvisorService

from shared.auth_middleware import TokenData, get_current_user
from shared.database import Database, get_db
from shared.llm_pricing import calculate_llm_cost
from shared.llm_usage_logger import calculate_prompt_hash, create_request_metadata, log_llm_usage

router = APIRouter()

# Initialize TripAdvisor service
TRIPADVISOR_API_KEY = os.getenv("TRIPADVISOR_API_KEY")
if not TRIPADVISOR_API_KEY:
    print("❌ ACTIVITY_SERVICE: TRIPADVISOR_API_KEY environment variable not set", flush=True)
    raise ValueError("TRIPADVISOR_API_KEY environment variable is required")

tripadvisor_service = TripAdvisorService(TRIPADVISOR_API_KEY)


@router.post("/activity/search", response_model=ActivitySearchResponse)
async def search_activities(
    request: ActivitySearchRequest,
    http_request: Request,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """
    Search for activities near user's location with personalized AI context
    """
    print(f"🎯 ACTIVITY_SEARCH: Starting search for user {request.user_id}", flush=True)
    print(
        f"🗺️ ACTIVITY_SEARCH: Location {request.location.latitude},{request.location.longitude} radius={request.location.radius_miles}mi",
        flush=True,
    )
    print(f"👥 ACTIVITY_SEARCH: Selected people: {request.selected_people}", flush=True)

    # Verify user can only search activities for themselves
    if current_user.user_id != str(request.user_id):
        print(
            f"🚨 ACTIVITY_SEARCH: User {current_user.user_id} attempted to search activities for different user {request.user_id}",
            flush=True,
        )
        raise HTTPException(status_code=403, detail="Can only search activities for yourself")

    try:
        # Extract Authorization header for service-to-service calls
        auth_token = http_request.headers.get("authorization", "")
        if not auth_token:
            raise HTTPException(status_code=401, detail="Authorization header required")

        # Content service no longer manages DUST - handled externally

        # Get people information for AI context
        people_info = await _get_people_info(db, request.user_id, request.selected_people)
        print(f"👥 ACTIVITY_SEARCH: Retrieved info for {len(people_info)} people", flush=True)

        # Search TripAdvisor for activities
        activities_data, total_found = await tripadvisor_service.search_nearby_activities(
            latitude=request.location.latitude,
            longitude=request.location.longitude,
            radius_miles=request.location.radius_miles,
            location_type=request.location_type.value,
        )

        print(
            f"📊 ACTIVITY_SEARCH: TripAdvisor returned {len(activities_data)} activities", flush=True
        )

        if not activities_data:
            print("⚠️ ACTIVITY_SEARCH: No activities found", flush=True)
            return ActivitySearchResponse(
                activities=[],
                search_metadata=ActivitySearchMetadata(
                    total_found=0,
                    radius_used=request.location.radius_miles,
                    location_address=tripadvisor_service.get_location_address(
                        request.location.latitude, request.location.longitude
                    ),
                ),
            )

        # Generate AI context for each activity
        activities_with_context = await _generate_ai_contexts(
            activities_data, people_info, request.user_id, auth_token
        )

        # Sort and limit results
        sorted_activities = await _prioritize_activities(activities_with_context, request.location)
        final_activities = sorted_activities[:12]  # Limit to 12 activities

        print(
            f"✅ ACTIVITY_SEARCH: Returning {len(final_activities)} activities with AI context",
            flush=True,
        )

        print(
            f"✅ ACTIVITY_SEARCH: Generated activities for user {request.user_id} (DUST handled by client)",
            flush=True,
        )

        # Build response
        activities = []
        for activity_data in final_activities:
            activity = Activity(
                id=f"act_{uuid.uuid4()}",
                tripadvisor_id=activity_data["tripadvisor_id"],
                name=activity_data["name"],
                type=ActivityType(activity_data["type"]),
                address=activity_data["address"],
                distance_miles=activity_data["distance_miles"],
                latitude=activity_data["latitude"],
                longitude=activity_data["longitude"],
                rating=activity_data["rating"],
                num_reviews=activity_data["num_reviews"],
                price_level=activity_data["price_level"],
                photos=activity_data["photos"],
                hours=activity_data["hours"],
                current_status=activity_data["current_status"],
                phone=activity_data["phone"],
                website=activity_data["website"],
                ai_context=activity_data["ai_context"],
                suitability_tags=activity_data["suitability_tags"],
            )
            activities.append(activity)

        return ActivitySearchResponse(
            activities=activities,
            search_metadata=ActivitySearchMetadata(
                total_found=total_found,
                radius_used=request.location.radius_miles,
                location_address=tripadvisor_service.get_location_address(
                    request.location.latitude, request.location.longitude
                ),
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ ACTIVITY_SEARCH: Unexpected error: {str(e)}", flush=True)
        print(f"❌ ACTIVITY_SEARCH: Error type: {type(e).__name__}", flush=True)
        raise HTTPException(status_code=500, detail="Internal server error during activity search")


async def _get_user_balance(user_id: uuid.UUID, auth_token: str) -> int:
    """Get user's current DUST balance via Ledger Service"""
    print(f"🔍 ACTIVITY_BALANCE: Checking DUST balance for user {user_id}", flush=True)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{ledger_url}/balance/{user_id}",
                headers={"Authorization": auth_token},
                timeout=10.0,
            )
            print(
                f"🔍 ACTIVITY_BALANCE: Ledger service response: {response.status_code}", flush=True
            )

            if response.status_code == 200:
                balance_data = response.json()
                balance = balance_data.get("balance", 0)
                print(f"✅ ACTIVITY_BALANCE: User {user_id} has {balance} DUST", flush=True)
                print(f"🔍 ACTIVITY_BALANCE: Full response: {balance_data}", flush=True)
                return balance
            else:
                print(f"❌ ACTIVITY_BALANCE: Ledger service error: {response.text}", flush=True)
                return 0
    except Exception as e:
        print(f"❌ ACTIVITY_BALANCE: Exception getting balance: {str(e)}", flush=True)
        return 0


async def _get_app_id(db: Database) -> str:
    """Get the UUID for the fairydust-activity app"""
    result = await db.fetch_one("SELECT id FROM apps WHERE slug = $1", "fairydust-activity")
    if not result:
        raise HTTPException(
            status_code=500,
            detail="fairydust-activity app not found in database. Please create the app first.",
        )
    return str(result["id"])


async def _get_people_info(
    db: Database, user_id: uuid.UUID, selected_people: list[str]
) -> list[dict]:
    """Get information about selected people for AI context"""
    if not selected_people:
        return []

    try:
        # Convert string IDs to UUIDs
        person_uuids = []
        for person_id in selected_people:
            try:
                person_uuids.append(uuid.UUID(person_id))
            except ValueError:
                print(f"⚠️ ACTIVITY_PEOPLE: Invalid person ID format: {person_id}", flush=True)
                continue

        if not person_uuids:
            return []

        query = """
            SELECT person_id, name, relationship, age, traits, notes
            FROM user_people
            WHERE user_id = $1 AND person_id = ANY($2)
        """

        rows = await db.fetch_all(query, user_id, person_uuids)

        people_info = []
        for row in rows:
            people_info.append(
                {
                    "person_id": str(row["person_id"]),
                    "name": row["name"],
                    "relationship": row["relationship"],
                    "age": row["age"],
                    "traits": row["traits"] or [],
                    "notes": row["notes"],
                }
            )

        return people_info

    except Exception as e:
        print(f"❌ ACTIVITY_PEOPLE: Error getting people info: {str(e)}", flush=True)
        return []


async def _generate_ai_contexts(
    activities_data: list[dict], people_info: list[dict], user_id: uuid.UUID, auth_token: str
) -> list[dict]:
    """Generate personalized AI context for each activity"""
    print(f"🤖 ACTIVITY_AI: Generating contexts for {len(activities_data)} activities", flush=True)

    # Build context about the group
    group_context = _build_group_context(people_info)

    # Generate context for each activity (in batches to avoid overwhelming the API)
    batch_size = 5
    activities_with_context = []

    for i in range(0, len(activities_data), batch_size):
        batch = activities_data[i : i + batch_size]
        batch_contexts = await _generate_batch_contexts(batch, group_context, user_id, auth_token)

        for j, activity in enumerate(batch):
            activity_copy = activity.copy()
            if j < len(batch_contexts):
                activity_copy["ai_context"] = batch_contexts[j]["context"]
                activity_copy["suitability_tags"] = batch_contexts[j]["tags"]
            else:
                activity_copy["ai_context"] = f"Great {activity['type']} to explore!"
                activity_copy["suitability_tags"] = ["interesting"]

            activities_with_context.append(activity_copy)

    print(f"✅ ACTIVITY_AI: Generated {len(activities_with_context)} activity contexts", flush=True)
    return activities_with_context


def _build_group_context(people_info: list[dict]) -> str:
    """Build context string about the group composition"""
    if not people_info:
        return "solo traveler"

    group_parts = []
    for person in people_info:
        age_str = f" ({person['age']})" if person["age"] else ""
        group_parts.append(f"{person['name']}{age_str}")

    return f"group with {', '.join(group_parts)}"


async def _get_llm_model_config() -> dict:
    """Get LLM configuration for activity AI context generation (with caching)"""
    from shared.app_config_cache import get_app_config_cache

    app_id = "fairydust-activity"

    # Try to get from cache first
    cache = await get_app_config_cache()
    cached_config = await cache.get_model_config(app_id)

    if cached_config:
        return {
            "primary_provider": cached_config.get("primary_provider", "anthropic"),
            "primary_model_id": cached_config.get("primary_model_id", "claude-3-haiku-20240307"),
            "primary_parameters": cached_config.get(
                "primary_parameters", {"temperature": 0.7, "max_tokens": 1000, "top_p": 0.9}
            ),
        }

    # Cache miss - use default config and cache it
    default_config = {
        "primary_provider": "anthropic",
        "primary_model_id": "claude-3-haiku-20240307",
        "primary_parameters": {"temperature": 0.7, "max_tokens": 1000, "top_p": 0.9},
    }

    # Cache the default config for future requests
    await cache.set_model_config(app_id, default_config)

    return default_config


async def _generate_batch_contexts(
    activities: list[dict], group_context: str, user_id: uuid.UUID, auth_token: str
) -> list[dict]:
    """Generate AI contexts for a batch of activities"""
    try:
        # Get LLM configuration
        model_config = await _get_llm_model_config()

        # Build prompt for the batch
        activities_text = ""
        for i, activity in enumerate(activities):
            activities_text += (
                f"{i+1}. {activity['name']} - {activity['type']} at {activity['address']}\n"
            )
            if activity.get("rating"):
                activities_text += f"   Rating: {activity['rating']}/5"
            if activity.get("num_reviews"):
                activities_text += f" ({activity['num_reviews']} reviews)"
            activities_text += "\n"

        prompt = f"""For each activity below, generate a personalized 2-3 sentence recommendation for a {group_context}. Focus on why this activity suits the specific group, practical tips, and what to expect. Also provide 2-4 suitability tags.

Activities:
{activities_text}

Respond with exactly {len(activities)} entries in this JSON format:
[
  {{
    "context": "Perfect for you and Sarah (8) - this interactive science museum...",
    "tags": ["family-friendly", "educational", "indoor", "interactive"]
  }}
]"""

        # Build request based on provider
        provider = model_config.get("primary_provider", "anthropic")
        model_id = model_config.get("primary_model_id", "claude-3-haiku-20240307")
        parameters = model_config.get("primary_parameters", {})

        # Make API call to generate contexts
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
                        "max_tokens": parameters.get("max_tokens", 1000),
                        "temperature": parameters.get("temperature", 0.7),
                        "top_p": parameters.get("top_p", 0.9),
                        "messages": [{"role": "user", "content": prompt}],
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
                        "max_tokens": parameters.get("max_tokens", 1000),
                        "temperature": parameters.get("temperature", 0.7),
                        "top_p": parameters.get("top_p", 0.9),
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
            else:
                print(
                    f"⚠️ ACTIVITY_AI: Unsupported provider {provider}, falling back to Anthropic",
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
                        "model": "claude-3-haiku-20240307",
                        "max_tokens": 1000,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )

            if response.status_code == 200:
                result = response.json()

                # Handle different response formats based on provider
                if provider == "anthropic":
                    content = result["content"][0]["text"]
                    usage = result.get("usage", {})
                    prompt_tokens = usage.get("input_tokens", 0)
                    completion_tokens = usage.get("output_tokens", 0)
                elif provider == "openai":
                    content = result["choices"][0]["message"]["content"]
                    usage = result.get("usage", {})
                    prompt_tokens = usage.get("prompt_tokens", 0)
                    completion_tokens = usage.get("completion_tokens", 0)
                else:
                    # Fallback case
                    content = result["content"][0]["text"]
                    usage = result.get("usage", {})
                    prompt_tokens = usage.get("input_tokens", 0)
                    completion_tokens = usage.get("output_tokens", 0)

                total_tokens = prompt_tokens + completion_tokens

                cost = calculate_llm_cost(provider, model_id, prompt_tokens, completion_tokens)

                # Log LLM usage (don't block on logging failures)
                try:
                    prompt_hash = calculate_prompt_hash(prompt)
                    request_metadata = create_request_metadata(
                        action="activity_context_generation",
                        parameters={
                            "batch_size": len(activities),
                            "group_context": group_context,
                        },
                    )

                    await log_llm_usage(
                        user_id=user_id,
                        app_id="fairydust-activity",
                        provider=provider,
                        model_id=model_id,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                        cost_usd=cost,
                        latency_ms=0,  # Activity routes don't track latency yet
                        prompt_hash=prompt_hash,
                        finish_reason="stop",
                        was_fallback=False,
                        fallback_reason=None,
                        request_metadata=request_metadata,
                        auth_token=auth_token,
                    )
                except Exception as e:
                    print(f"⚠️ ACTIVITY_AI: Failed to log LLM usage: {str(e)}", flush=True)

                # Try to parse JSON response
                try:
                    contexts = json.loads(content)
                    if isinstance(contexts, list) and len(contexts) == len(activities):
                        return contexts
                except json.JSONDecodeError:
                    print("⚠️ ACTIVITY_AI: Failed to parse AI response as JSON", flush=True)
            else:
                print(
                    f"⚠️ ACTIVITY_AI: AI API error {response.status_code}: {response.text}",
                    flush=True,
                )

    except Exception as e:
        print(f"⚠️ ACTIVITY_AI: Error generating AI contexts: {str(e)}", flush=True)

    # Fallback contexts
    fallback_contexts = []
    for activity in activities:
        fallback_contexts.append(
            {
                "context": f"Great {activity['type']} to explore with your group!",
                "tags": ["interesting", "worth-visiting"],
            }
        )

    return fallback_contexts


async def _prioritize_activities(activities: list[dict], location: dict) -> list[dict]:
    """Sort activities by relevance, distance, and rating"""

    def priority_score(activity):
        score = 0

        # Rating boost (0-5 scale)
        if activity.get("rating"):
            score += activity["rating"] * 2

        # Review count boost (logarithmic)
        if activity.get("num_reviews"):
            import math

            score += math.log10(max(1, activity["num_reviews"]))

        # Distance penalty (closer is better)
        distance_penalty = activity.get("distance_miles", 0) * 0.5
        score -= distance_penalty

        # Type variety bonus (slight preference for attractions)
        if activity.get("type") == "attraction":
            score += 0.5

        return score

    return sorted(activities, key=priority_score, reverse=True)
