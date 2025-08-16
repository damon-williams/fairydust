# services/content/inspire_routes.py
# Service URL configuration based on environment
import os
from datetime import datetime
from typing import Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from models import (
    InspirationCategory,
    InspirationDeleteResponse,
    InspirationErrorResponse,
    InspirationFavoriteRequest,
    InspirationFavoriteResponse,
    InspirationGenerateRequest,
    InspirationGenerateResponse,
    InspirationsListResponse,
    TokenUsage,
    UserInspiration,
)

from shared.auth_middleware import TokenData, get_current_user
from shared.database import Database, get_db
from shared.llm_client import LLMError, llm_client
from shared.uuid_utils import generate_uuid7

# Service URL configuration
environment = os.getenv("ENVIRONMENT", "staging")
base_url_suffix = "production" if environment == "production" else "staging"
ledger_url = f"https://fairydust-ledger-{base_url_suffix}.up.railway.app"

router = APIRouter()

# Constants
INSPIRE_RATE_LIMIT = 10  # Max 10 generations per hour per user

# Category-specific prompts
CATEGORY_PROMPTS = {
    InspirationCategory.CHALLENGE: "Generate a fun, achievable challenge or adventure that someone could try today or this weekend. Make it specific, actionable, and exciting. Keep it under 20 words.",
    InspirationCategory.CREATIVE: "Suggest a creative project or artistic activity that someone could start today. Make it inspiring and accessible. Keep it under 20 words.",
    InspirationCategory.SELF_CARE: "Recommend a self-care activity or healthy habit that would be good for someone today. Make it practical and beneficial. Keep it under 20 words.",
    InspirationCategory.KIND_GESTURE: "Suggest a kind gesture or thoughtful action someone could do for a friend, family member, or stranger. Keep it under 20 words.",
}


@router.post("/apps/inspire/generate", response_model=InspirationGenerateResponse)
async def generate_inspiration(
    request: InspirationGenerateRequest,
    http_request: Request,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """
    Generate a new inspiration using LLM and automatically save it to user's collection.
    """
    from shared.uuid_utils import generate_uuid7

    request_id = str(generate_uuid7())[:8]
    print(
        f"🚀 INSPIRE DEBUG: === NEW REQUEST START [{request_id}] === User: {request.user_id}, Category: {request.category}",
        flush=True,
    )
    print(f"🌟 INSPIRE: Starting generation for user {request.user_id}", flush=True)
    print(f"📂 INSPIRE: Category: {request.category}", flush=True)

    # Verify user can only generate inspirations for themselves
    if current_user.user_id != str(request.user_id):
        print(
            f"🚨 INSPIRE: User {current_user.user_id} attempted to generate inspiration for different user {request.user_id}",
            flush=True,
        )
        return InspirationErrorResponse(error="Can only generate inspirations for yourself")

    try:
        # Extract Authorization header for service-to-service calls
        auth_token = http_request.headers.get("authorization", "")
        if not auth_token:
            return InspirationErrorResponse(error="Authorization header required")

        # Check rate limiting
        rate_limit_exceeded = await _check_rate_limit(db, request.user_id)
        if rate_limit_exceeded:
            return InspirationErrorResponse(
                error=f"Rate limit exceeded. Maximum {INSPIRE_RATE_LIMIT} inspirations per hour."
            )

        # Get user balance for logging purposes only (payment handled by app)
        user_balance = await _get_user_balance(request.user_id, auth_token)
        print(
            f"💰 INSPIRE DEBUG: User balance: {user_balance} DUST",
            flush=True,
        )

        # Get user context for personalization
        user_context = await _get_user_context(db, request.user_id)
        print("👤 INSPIRE: Retrieved user context", flush=True)

        # Get user's recent inspirations to avoid duplicates
        recent_inspirations = await _get_recent_inspirations(db, request.user_id, request.category)
        print(
            f"🔍 INSPIRE: Found {len(recent_inspirations)} recent inspirations to avoid", flush=True
        )

        # Generate inspiration using LLM with enhanced duplicate prevention and retry logic
        print(
            f"🤖 INSPIRE DEBUG: Starting LLM generation for category: {request.category}", flush=True
        )

        max_retries = 3
        inspiration_content = None
        model_used = None
        tokens_used = {}
        total_cost = 0.0

        for attempt in range(max_retries):
            print(f"🔄 INSPIRE DEBUG: Generation attempt {attempt + 1}/{max_retries}", flush=True)

            content, model, tokens, cost = await _generate_inspiration_llm_with_user(
                category=request.category,
                used_suggestions=request.used_suggestions,
                user_context=user_context,
                recent_inspirations=recent_inspirations,
                user_id=request.user_id,
            )

            total_cost += cost
            if content:  # Success - no duplicate detected
                inspiration_content = content
                model_used = model
                tokens_used = tokens
                break
            else:
                print(
                    f"⚠️ INSPIRE DEBUG: Attempt {attempt + 1} failed (duplicate or error)",
                    flush=True,
                )
                if attempt < max_retries - 1:
                    print(
                        "🔄 INSPIRE DEBUG: Retrying with more specific anti-duplicate instructions...",
                        flush=True,
                    )

        if not inspiration_content:
            print("❌ INSPIRE DEBUG: All generation attempts failed", flush=True)
            return InspirationErrorResponse(
                error="Failed to generate unique inspiration. Please try again."
            )

        # Use total cost from all attempts
        cost = total_cost

        print(f"🤖 INSPIRE DEBUG: Generated inspiration: {inspiration_content[:50]}...", flush=True)
        print(
            f"🤖 INSPIRE DEBUG: Model used: {model_used}, LLM cost: ${cost}, Tokens: {tokens_used}",
            flush=True,
        )

        # Save inspiration to database
        inspiration_id = await _save_inspiration(
            db=db,
            user_id=request.user_id,
            content=inspiration_content,
            category=request.category,
            session_id=request.session_id,
            model_used=model_used,
            tokens_used=tokens_used,
            cost=cost,
        )

        # Mark onboarding as completed for first-time users
        await _mark_onboarding_completed(db, request.user_id)

        # DUST payment is handled by the app before calling this endpoint
        new_balance = user_balance  # Balance unchanged by content service

        # Build response
        inspiration = UserInspiration(
            id=inspiration_id,
            content=inspiration_content,
            category=request.category,
            created_at=datetime.utcnow(),
            is_favorited=False,
        )

        return InspirationGenerateResponse(
            inspiration=inspiration,
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
        print(f"❌ INSPIRE: Unexpected error: {str(e)}", flush=True)
        print(f"❌ INSPIRE: Error type: {type(e).__name__}", flush=True)
        return InspirationErrorResponse(error="Internal server error during inspiration generation")


@router.get("/users/{user_id}/inspirations", response_model=InspirationsListResponse)
async def get_user_inspirations(
    user_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
    limit: int = Query(50, ge=1, le=100, description="Number of results to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    category: Optional[InspirationCategory] = Query(None, description="Filter by category"),
    favorites_only: bool = Query(False, description="Return only favorited items"),
):
    """
    Retrieve all saved inspirations for a user, sorted by favorites first, then creation date descending.
    """
    print(f"📋 INSPIRE: Getting inspirations for user {user_id}", flush=True)

    # Verify user can only access their own inspirations
    if current_user.user_id != str(user_id):
        print(
            f"🚨 INSPIRE: User {current_user.user_id} attempted to access inspirations for different user {user_id}",
            flush=True,
        )
        return InspirationErrorResponse(error="Can only access your own inspirations")

    try:
        # Build query with filters
        base_query = """
            SELECT id, content, category, is_favorited, created_at
            FROM user_inspirations
            WHERE user_id = $1 AND deleted_at IS NULL
        """
        params = [user_id]
        param_count = 1

        if category:
            param_count += 1
            base_query += f" AND category = ${param_count}"
            params.append(category.value)

        if favorites_only:
            base_query += " AND is_favorited = TRUE"

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
            FROM user_inspirations
            WHERE user_id = $1 AND deleted_at IS NULL
        """
        count_params = [user_id]

        if category:
            count_query += " AND category = $2"
            count_params.append(category.value)

        count_result = await db.fetch_one(count_query, *count_params)
        total_count = count_result["total_count"] if count_result else 0
        favorites_count = count_result["favorites_count"] if count_result else 0

        # Build response
        inspirations = []
        for row in rows:
            inspiration = UserInspiration(
                id=row["id"],
                content=row["content"],
                category=InspirationCategory(row["category"]),
                created_at=row["created_at"],
                is_favorited=row["is_favorited"],
            )
            inspirations.append(inspiration)

        print(f"✅ INSPIRE: Returning {len(inspirations)} inspirations", flush=True)

        return InspirationsListResponse(
            inspirations=inspirations,
            total_count=total_count,
            favorites_count=favorites_count,
        )

    except Exception as e:
        print(f"❌ INSPIRE: Error getting inspirations: {str(e)}", flush=True)
        return InspirationErrorResponse(error="Failed to retrieve inspirations")


@router.post(
    "/users/{user_id}/inspirations/{inspiration_id}/favorite",
    response_model=InspirationFavoriteResponse,
)
async def toggle_inspiration_favorite(
    user_id: UUID,
    inspiration_id: UUID,
    request: InspirationFavoriteRequest,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """
    Toggle the favorite status of a saved inspiration.
    """
    print(
        f"⭐ INSPIRE: Toggling favorite for inspiration {inspiration_id} to {request.is_favorited}",
        flush=True,
    )

    # Verify user can only modify their own inspirations
    if current_user.user_id != str(user_id):
        print(
            f"🚨 INSPIRE: User {current_user.user_id} attempted to modify inspiration for different user {user_id}",
            flush=True,
        )
        return InspirationErrorResponse(error="Can only modify your own inspirations")

    try:
        # Update favorite status
        update_query = """
            UPDATE user_inspirations
            SET is_favorited = $1, updated_at = CURRENT_TIMESTAMP
            WHERE id = $2 AND user_id = $3 AND deleted_at IS NULL
            RETURNING id, content, category, is_favorited, created_at
        """

        result = await db.fetch_one(update_query, request.is_favorited, inspiration_id, user_id)

        if not result:
            return InspirationErrorResponse(
                error="Inspiration not found", inspiration_id=inspiration_id
            )

        inspiration = UserInspiration(
            id=result["id"],
            content=result["content"],
            category=InspirationCategory(result["category"]),
            created_at=result["created_at"],
            is_favorited=result["is_favorited"],
        )

        print(f"✅ INSPIRE: Updated favorite status for inspiration {inspiration_id}", flush=True)

        return InspirationFavoriteResponse(inspiration=inspiration)

    except Exception as e:
        print(f"❌ INSPIRE: Error updating favorite: {str(e)}", flush=True)
        return InspirationErrorResponse(error="Failed to update favorite status")


@router.delete(
    "/users/{user_id}/inspirations/{inspiration_id}",
    response_model=InspirationDeleteResponse,
)
async def delete_inspiration(
    user_id: UUID,
    inspiration_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """
    Remove a saved inspiration from user's collection (soft delete).
    """
    print(f"🗑️ INSPIRE: Deleting inspiration {inspiration_id}", flush=True)

    # Verify user can only delete their own inspirations
    if current_user.user_id != str(user_id):
        print(
            f"🚨 INSPIRE: User {current_user.user_id} attempted to delete inspiration for different user {user_id}",
            flush=True,
        )
        return InspirationErrorResponse(error="Can only delete your own inspirations")

    try:
        # Soft delete (set deleted_at timestamp)
        delete_query = """
            UPDATE user_inspirations
            SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = $1 AND user_id = $2 AND deleted_at IS NULL
        """

        result = await db.execute(delete_query, inspiration_id, user_id)

        # Check if any rows were affected
        if "UPDATE 0" in result:
            return InspirationErrorResponse(
                error="Inspiration not found", inspiration_id=inspiration_id
            )

        print(f"✅ INSPIRE: Deleted inspiration {inspiration_id}", flush=True)

        return InspirationDeleteResponse()

    except Exception as e:
        print(f"❌ INSPIRE: Error deleting inspiration: {str(e)}", flush=True)
        return InspirationErrorResponse(error="Failed to delete inspiration")


# Helper functions
async def _get_user_balance(user_id: UUID, auth_token: str) -> int:
    """Get user's current DUST balance via Ledger Service"""
    print(f"🔍 INSPIRE_BALANCE: Checking DUST balance for user {user_id}", flush=True)
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
                print(f"✅ INSPIRE_BALANCE: User {user_id} has {balance} DUST", flush=True)
                return balance
            else:
                print(f"❌ INSPIRE_BALANCE: Ledger service error: {response.text}", flush=True)
                return 0
    except Exception as e:
        print(f"❌ INSPIRE_BALANCE: Exception getting balance: {str(e)}", flush=True)
        return 0


async def _check_rate_limit(db: Database, user_id: UUID) -> bool:
    """Check if user has exceeded rate limit for inspiration generation"""
    try:
        # Count generations in the last hour
        query = """
            SELECT COUNT(*) as generation_count
            FROM user_inspirations
            WHERE user_id = $1
            AND created_at > NOW() - INTERVAL '1 hour'
            AND deleted_at IS NULL
        """

        result = await db.fetch_one(query, user_id)
        generation_count = result["generation_count"] if result else 0

        if generation_count >= INSPIRE_RATE_LIMIT:
            print(
                f"⚠️ INSPIRE_RATE_LIMIT: User {user_id} exceeded rate limit: {generation_count}/{INSPIRE_RATE_LIMIT}",
                flush=True,
            )
            return True

        print(
            f"✅ INSPIRE_RATE_LIMIT: User {user_id} within limit: {generation_count}/{INSPIRE_RATE_LIMIT}",
            flush=True,
        )
        return False

    except Exception as e:
        print(f"❌ INSPIRE_RATE_LIMIT: Error checking rate limit: {str(e)}", flush=True)
        # Default to allowing if we can't check (fail open)
        return False


async def _get_recent_inspirations(
    db: Database, user_id: UUID, category: InspirationCategory
) -> list[str]:
    """Get user's recent inspirations to avoid duplicates"""
    try:
        # Get recent inspirations from the same category (last 30 days)
        query = """
            SELECT content
            FROM user_inspirations
            WHERE user_id = $1
            AND category = $2
            AND deleted_at IS NULL
            AND created_at > NOW() - INTERVAL '30 days'
            ORDER BY created_at DESC
            LIMIT 20
        """

        rows = await db.fetch_all(query, user_id, category.value)
        recent_content = [row["content"] for row in rows]

        print(
            f"🔍 INSPIRE_RECENT: Found {len(recent_content)} recent inspirations for {category.value}",
            flush=True,
        )
        return recent_content

    except Exception as e:
        print(f"⚠️ INSPIRE_RECENT: Error getting recent inspirations: {str(e)}", flush=True)
        return []


def _is_duplicate_content(new_content: str, previous_content: list[str]) -> bool:
    """Check if new content is too similar to previous content"""
    if not previous_content or not new_content:
        return False

    new_content_lower = new_content.lower().strip()

    for prev_content in previous_content:
        prev_content_lower = prev_content.lower().strip()

        # Check for exact matches
        if new_content_lower == prev_content_lower:
            return True

        # Check for very high similarity (90%+ word overlap)
        new_words = set(new_content_lower.split())
        prev_words = set(prev_content_lower.split())

        if len(new_words) > 0 and len(prev_words) > 0:
            overlap = len(new_words.intersection(prev_words))
            similarity = overlap / max(len(new_words), len(prev_words))

            if similarity > 0.9:  # 90% similarity threshold
                return True

        # Check for substring matches (one is contained in the other)
        if len(new_content_lower) > 10 and len(prev_content_lower) > 10:
            if new_content_lower in prev_content_lower or prev_content_lower in new_content_lower:
                return True

    return False


async def _get_user_context(db: Database, user_id: UUID) -> str:
    """Get user context for personalization"""
    try:
        # Get people and pets in my life
        people_query = """
            SELECT name, relationship, birth_date, personality_description, entry_type, species
            FROM people_in_my_life
            WHERE user_id = $1
        """

        people_rows = await db.fetch_all(people_query, user_id)

        # Build context string
        context_parts = []

        if people_rows:
            people_list = []
            pets_list = []

            for row in people_rows:
                if row["entry_type"] == "pet":
                    # Handle pets
                    pet_desc = f"{row['name']}"
                    if row["species"]:
                        pet_desc += f" ({row['species']}"
                    else:
                        pet_desc += " (pet"

                    if row["relationship"]:
                        pet_desc += f", {row['relationship']}"

                    if row["birth_date"]:
                        # Calculate age from birth date
                        from datetime import date

                        birth = date.fromisoformat(str(row["birth_date"]))
                        age = (date.today() - birth).days // 365
                        pet_desc += f", {age} years old"

                    # Add personality description if available
                    if row["personality_description"]:
                        pet_desc += f", {row['personality_description']}"

                    pet_desc += ")"
                    pets_list.append(pet_desc)
                else:
                    # Handle people
                    person_desc = f"{row['name']} ({row['relationship']}"
                    if row["birth_date"]:
                        # Calculate age from birth date
                        from datetime import date

                        birth = date.fromisoformat(str(row["birth_date"]))
                        age = (date.today() - birth).days // 365
                        person_desc += f", {age} years old"

                    # Add personality description if available
                    if row["personality_description"]:
                        person_desc += f", {row['personality_description']}"

                    person_desc += ")"
                    people_list.append(person_desc)

            if people_list:
                context_parts.append(f"People: {', '.join(people_list[:3])}")

            if pets_list:
                context_parts.append(f"Pets: {', '.join(pets_list[:3])}")

        return "; ".join(context_parts) if context_parts else "general user"

    except Exception as e:
        print(f"⚠️ INSPIRE_CONTEXT: Error getting user context: {str(e)}", flush=True)
        return "general user"


async def _get_llm_model_config() -> dict:
    """Get LLM configuration for inspire app using normalized structure (with caching)"""
    from shared.app_config_cache import get_app_config_cache
    from shared.database import get_db
    from shared.json_utils import parse_jsonb_field

    app_slug = "fairydust-inspire"

    # First, get the app UUID from the slug
    db = await get_db()
    app_result = await db.fetch_one("SELECT id FROM apps WHERE slug = $1", app_slug)

    if not app_result:
        print(f"❌ INSPIRE_CONFIG: App with slug '{app_slug}' not found in database", flush=True)
        # Get global fallback configuration instead of hardcoded defaults
        try:
            from shared.llm_client import llm_client

            global_fallbacks = await llm_client._get_global_fallbacks()
            if global_fallbacks:
                primary_provider, primary_model = global_fallbacks[0]
                return {
                    "primary_provider": primary_provider,
                    "primary_model_id": primary_model,
                    "primary_parameters": {"temperature": 0.8, "max_tokens": 150, "top_p": 0.9},
                }
        except Exception as e:
            print(f"⚠️ INSPIRE_CONFIG: Failed to get global fallbacks: {e}", flush=True)

        # Emergency hardcoded fallback only if global config fails
        return {
            "primary_provider": "anthropic",
            "primary_model_id": "claude-3-5-haiku-20241022",
            "primary_parameters": {"temperature": 0.8, "max_tokens": 150, "top_p": 0.9},
        }

    app_id = str(app_result["id"])
    print(f"🔍 INSPIRE_CONFIG: Resolved {app_slug} to UUID {app_id}", flush=True)

    # Try to get from cache first (cache still uses legacy format)
    cache = await get_app_config_cache()
    cached_config = await cache.get_model_config(app_id)

    if cached_config:
        # Get global fallbacks for defaults
        default_provider = "anthropic"
        default_model = "claude-3-5-haiku-20241022"
        try:
            from shared.llm_client import llm_client

            global_fallbacks = await llm_client._get_global_fallbacks()
            if global_fallbacks:
                default_provider, default_model = global_fallbacks[0]
        except:
            pass

        return {
            "primary_provider": cached_config.get("primary_provider", default_provider),
            "primary_model_id": cached_config.get("primary_model_id", default_model),
            "primary_parameters": cached_config.get(
                "primary_parameters", {"temperature": 0.8, "max_tokens": 150, "top_p": 0.9}
            ),
        }

    # Cache miss - fetch from new normalized database structure
    print("⚠️ INSPIRE_CONFIG: Cache miss, checking database directly", flush=True)

    try:
        db_config = await db.fetch_one(
            """
            SELECT provider, model_id, parameters FROM app_model_configs
            WHERE app_id = $1 AND model_type = 'text' AND is_enabled = true
            """,
            app_result["id"],
        )

        if db_config:
            print("📊 INSPIRE_CONFIG: Found normalized database config", flush=True)
            print(f"📊 INSPIRE_CONFIG: DB Provider: {db_config['provider']}", flush=True)
            print(f"📊 INSPIRE_CONFIG: DB Model: {db_config['model_id']}", flush=True)

            # Parse parameters from JSONB field
            parameters = parse_jsonb_field(
                db_config["parameters"],
                default={"temperature": 0.8, "max_tokens": 150, "top_p": 0.9},
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
            print(f"✅ INSPIRE_CONFIG: Cached normalized config: {parsed_config}", flush=True)

            return parsed_config

    except Exception as e:
        print(f"❌ INSPIRE_CONFIG: Database error: {e}", flush=True)

    # Fallback to global default config
    print("🔄 INSPIRE_CONFIG: Using global default config (no cache, no database)", flush=True)

    # Get global fallbacks
    default_provider = "anthropic"
    default_model = "claude-3-5-haiku-20241022"
    try:
        from shared.llm_client import llm_client

        global_fallbacks = await llm_client._get_global_fallbacks()
        if global_fallbacks:
            default_provider, default_model = global_fallbacks[0]
    except Exception as e:
        print(f"⚠️ INSPIRE_CONFIG: Failed to get global fallbacks for default: {e}", flush=True)

    default_config = {
        "primary_provider": default_provider,
        "primary_model_id": default_model,
        "primary_parameters": {"temperature": 0.8, "max_tokens": 150, "top_p": 0.9},
    }

    # Cache the default config for future requests
    await cache.set_model_config(app_id, default_config)
    print(f"✅ INSPIRE_CONFIG: Cached default config: {default_config}", flush=True)

    return default_config


# _build_inspiration_prompt function removed - prompt building now handled in _generate_inspiration_llm_with_user


async def _generate_inspiration_llm_with_user(
    category: InspirationCategory,
    used_suggestions: list[str],
    user_context: str,
    recent_inspirations: list[str] = None,
    user_id: UUID = None,
) -> tuple[Optional[str], str, dict, float]:
    """Generate inspiration using centralized LLM client with user ID for logging"""
    try:
        # Get LLM model configuration from database/cache
        model_config = await _get_llm_model_config()

        # Build prompt
        base_prompt = CATEGORY_PROMPTS[category]

        # Add context and enhanced anti-duplication
        context_prompt = f"Context: User is a {user_context}. "

        anti_dup_prompt = ""

        # Combine recent database content with used_suggestions for comprehensive duplicate prevention
        all_previous_content = []
        if recent_inspirations:
            all_previous_content.extend(recent_inspirations)
        if used_suggestions:
            all_previous_content.extend(used_suggestions)

        if all_previous_content:
            # Use the most recent 15 items to avoid overly long prompts
            recent_items = list(set(all_previous_content))[-15:]  # Remove duplicates and limit
            suggestions_text = "\n".join([f"- {s}" for s in recent_items])
            anti_dup_prompt = f"\n\nIMPORTANT: Avoid generating anything identical or very similar to these previous inspirations:\n{suggestions_text}\n\nGenerate something completely fresh and unique.\n\n"

        full_prompt = f"{context_prompt}{base_prompt}{anti_dup_prompt}Respond with just the inspiration text, nothing else."

        print("🤖 INSPIRE_LLM: Generating with centralized LLM client", flush=True)

        # Create request metadata for logging
        request_metadata = {
            "parameters": {
                "category": category.value,
                "used_suggestions_count": len(used_suggestions) if used_suggestions else 0,
            },
            "user_context": user_context if user_context != "general user" else None,
        }

        # Use centralized LLM client
        completion, metadata = await llm_client.generate_completion(
            prompt=full_prompt,
            app_config=model_config,
            user_id=user_id or generate_uuid7(),
            app_id="fairydust-inspire",
            action="inspiration_generation",
            request_metadata=request_metadata,
        )

        # Extract data from metadata
        model_id = metadata["model_id"]
        tokens_used = metadata["tokens_used"]
        cost = metadata["cost_usd"]

        # Convert tokens format to match existing code
        tokens_dict = {
            "prompt": tokens_used["prompt_tokens"],
            "completion": tokens_used["completion_tokens"],
            "total": tokens_used["total_tokens"],
        }

        # Check for duplicates before returning
        if _is_duplicate_content(completion, all_previous_content):
            print(
                "⚠️ INSPIRE_LLM: Generated content is too similar to previous inspiration",
                flush=True,
            )
            print(f"🔄 INSPIRE_LLM: Generated: {completion[:50]}...", flush=True)
            # Return None to trigger retry at higher level
            return None, model_id, tokens_dict, cost

        print("✅ INSPIRE_LLM: Generated inspiration successfully", flush=True)
        return completion, model_id, tokens_dict, cost

    except LLMError as e:
        print(f"❌ INSPIRE_LLM: LLM error: {str(e)}", flush=True)
        return None, "claude-3-haiku-20240307", {}, 0.0
    except Exception as e:
        print(f"❌ INSPIRE_LLM: Error generating inspiration: {str(e)}", flush=True)
        return None, "claude-3-haiku-20240307", {}, 0.0


async def _save_inspiration(
    db: Database,
    user_id: UUID,
    content: str,
    category: InspirationCategory,
    session_id: Optional[UUID],
    model_used: str,
    tokens_used: dict,
    cost: float,
) -> UUID:
    """Save inspiration to database"""
    try:
        insert_query = """
            INSERT INTO user_inspirations (
                user_id, content, category, session_id, model_used,
                tokens_used, cost_usd, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
        """

        result = await db.fetch_one(
            insert_query,
            user_id,
            content,
            category.value,
            session_id,
            model_used,
            tokens_used.get("total", 0),
            cost,
        )

        inspiration_id = result["id"]
        print(f"✅ INSPIRE_SAVE: Saved inspiration {inspiration_id}", flush=True)
        return inspiration_id

    except Exception as e:
        print(f"❌ INSPIRE_SAVE: Error saving inspiration: {str(e)}", flush=True)
        raise HTTPException(status_code=500, detail="Failed to save inspiration")


async def _mark_onboarding_completed(db: Database, user_id: UUID) -> None:
    """Mark user's onboarding as completed if not already completed"""
    try:
        # Update only if onboarding is not already completed
        await db.execute(
            """
            UPDATE users
            SET is_onboarding_completed = TRUE, updated_at = CURRENT_TIMESTAMP
            WHERE id = $1 AND is_onboarding_completed = FALSE
            """,
            user_id,
        )
        print(f"✅ ONBOARDING: Marked onboarding completed for user {user_id}", flush=True)
    except Exception as e:
        print(f"⚠️ ONBOARDING: Error marking onboarding complete: {str(e)}", flush=True)
        # Don't raise exception - onboarding completion is not critical for inspiration generation
