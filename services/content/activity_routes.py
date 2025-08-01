# services/content/activity_routes.py
import json
import os
import uuid

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
from shared.llm_client import LLMError, llm_client
from shared.llm_usage_logger import create_request_metadata

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
    """Get information about selected people and pets from Identity Service for AI context"""
    if not selected_people:
        print("🔍 ACTIVITY_PEOPLE: No selected people, returning empty list")
        return []

    try:
        # Convert string IDs to UUIDs for Identity Service call
        person_uuids = []
        for person_id in selected_people:
            try:
                person_uuids.append(uuid.UUID(person_id))
            except ValueError:
                print(f"⚠️ ACTIVITY_PEOPLE: Invalid person ID format: {person_id}", flush=True)
                continue

        if not person_uuids:
            return []

        # Call Identity Service to get people and pets data
        import httpx

        # Service URL configuration based on environment
        environment = os.getenv("ENVIRONMENT", "staging")
        base_url_suffix = "production" if environment == "production" else "staging"
        identity_url = f"https://fairydust-identity-{base_url_suffix}.up.railway.app"

        print(f"🔍 ACTIVITY_PEOPLE: Fetching people data from Identity Service for user {user_id}")

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{identity_url}/users/{user_id}/people",
                timeout=10.0,
            )

            if response.status_code == 200:
                all_people = response.json().get("people", [])
                print(f"🔍 ACTIVITY_PEOPLE: Got {len(all_people)} people from Identity Service")

                # Filter to selected people and extract activity-relevant data
                selected_people_data = []
                for person in all_people:
                    if person and person.get("id") in [str(pid) for pid in person_uuids]:
                        # Calculate age from birth_date if available
                        age = None
                        if person.get("birth_date"):
                            from datetime import date

                            try:
                                birth = date.fromisoformat(person["birth_date"])
                                age = (date.today() - birth).days // 365
                            except:
                                pass

                        # Extract activity preferences or personality description for traits
                        traits = []
                        if person.get("personality_description"):
                            traits = [
                                t.strip() for t in person.get("personality_description").split(",")
                            ][:5]

                        # Build person/pet data
                        entry_type = person.get("entry_type", "person")
                        person_data = {
                            "person_id": person.get("id", ""),
                            "name": person.get("name", ""),
                            "relationship": person.get("relationship", ""),
                            "entry_type": entry_type,
                            "species": person.get("species"),  # For pets
                            "age": age,
                            "traits": traits,
                            "notes": "",  # Activity preferences could be added here
                        }

                        selected_people_data.append(person_data)

                print(
                    f"🔍 ACTIVITY_PEOPLE: Filtered to {len(selected_people_data)} selected people/pets"
                )
                return selected_people_data
            else:
                print(
                    f"🔍 ACTIVITY_PEOPLE: Identity Service returned {response.status_code}, returning empty list"
                )
                return []

    except Exception as e:
        print(
            f"❌ ACTIVITY_PEOPLE: Error getting people info from Identity Service: {str(e)}",
            flush=True,
        )
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
    """Build context string about the group composition including pets"""
    if not people_info:
        return "solo traveler"

    people_parts = []
    pet_parts = []

    for person in people_info:
        if person.get("entry_type") == "pet":
            # Handle pets differently
            species_str = f" ({person['species']})" if person.get("species") else ""
            age_str = f", {person['age']} years old" if person.get("age") else ""
            pet_parts.append(f"{person['name']}{species_str}{age_str}")
        else:
            # Handle people
            age_str = f" ({person['age']})" if person.get("age") else ""
            people_parts.append(f"{person['name']}{age_str}")

    # Build context string
    context_parts = []
    if people_parts:
        context_parts.append(f"group with {', '.join(people_parts)}")
    if pet_parts:
        pet_context = (
            f"traveling with pet{'s' if len(pet_parts) > 1 else ''}: {', '.join(pet_parts)}"
        )
        if people_parts:
            context_parts.append(pet_context)
        else:
            context_parts.append(f"solo traveler {pet_context}")

    return "; ".join(context_parts) if context_parts else "group"


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
    """Generate AI contexts for a batch of activities using centralized LLM client"""
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

        # Check if group includes pets for enhanced guidance
        has_pets = any(person.get("entry_type") == "pet" for person in people_info)
        pet_guidance = ""
        if has_pets:
            pet_guidance = " When the group includes pets, prioritize outdoor activities, pet-friendly venues, and practical considerations like leash requirements, pet waste facilities, and shade/water availability. Consider the pet's energy level and species-specific needs."

        prompt = f"""For each activity below, generate a personalized 2-3 sentence recommendation for a {group_context}. Focus on why this activity suits the specific group, practical tips, and what to expect. Also provide 2-4 suitability tags.{pet_guidance}

Activities:
{activities_text}

Respond with exactly {len(activities)} entries in this JSON format:
[
  {{
    "context": "Perfect for you and Sarah (8) - this interactive science museum...",
    "tags": ["family-friendly", "educational", "indoor", "interactive"]
  }}
]"""

        # Create request metadata
        request_metadata = create_request_metadata(
            action="find-activity",
            parameters={
                "batch_size": len(activities),
                "group_context": group_context,
            },
        )

        # Use centralized LLM client
        content, generation_metadata = await llm_client.generate_completion(
            prompt=prompt,
            app_config=model_config,
            user_id=user_id,
            app_id="fairydust-activity",
            action="find-activity",
            request_metadata=request_metadata,
        )

        print(
            f"✅ ACTIVITY_AI: Generated contexts using {generation_metadata['provider']}/{generation_metadata['model_id']}",
            flush=True,
        )

        if generation_metadata.get("was_fallback"):
            print("⚠️ ACTIVITY_AI: Used fallback provider after primary failed", flush=True)

        # Try to parse JSON response
        try:
            contexts = json.loads(content)
            if isinstance(contexts, list) and len(contexts) == len(activities):
                return contexts
        except json.JSONDecodeError:
            print("⚠️ ACTIVITY_AI: Failed to parse AI response as JSON", flush=True)

    except LLMError as e:
        print(f"❌ ACTIVITY_AI: LLM error generating contexts: {str(e)}", flush=True)
    except Exception as e:
        print(f"❌ ACTIVITY_AI: Unexpected error generating AI contexts: {str(e)}", flush=True)

    # Fallback contexts
    print(f"⚠️ ACTIVITY_AI: Using fallback contexts for {len(activities)} activities", flush=True)
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
