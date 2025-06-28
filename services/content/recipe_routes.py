# services/content/recipe_routes.py
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
    DietaryRestriction,
    PersonPreference,
    RecipeComplexity,
    RecipeDeleteResponse,
    RecipeErrorResponse,
    RecipeFavoriteRequest,
    RecipeFavoriteResponse,
    RecipeGenerateRequest,
    RecipeGenerateResponse,
    RecipePreferences,
    RecipePreferencesResponse,
    RecipePreferencesUpdateRequest,
    RecipesListResponse,
    TokenUsage,
    UserRecipeNew,
)

from shared.auth_middleware import TokenData, get_current_user
from shared.database import Database, get_db
from shared.llm_pricing import calculate_llm_cost
from shared.llm_usage_logger import calculate_prompt_hash, create_request_metadata, log_llm_usage

router = APIRouter()

# Constants
RECIPE_DUST_COST = 3
RECIPE_RATE_LIMIT = 15  # Max 15 generations per hour per user


@router.post("/apps/recipe/generate")
async def generate_recipe(
    request: RecipeGenerateRequest,
    http_request: Request,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """
    Generate a new recipe using LLM and automatically save it to user's collection.
    """
    print(f"🍳 RECIPE: Starting generation for user {request.user_id}", flush=True)
    print(f"📂 RECIPE: Dish: {request.dish}, Complexity: {request.complexity}", flush=True)

    # Verify user can only generate recipes for themselves
    if current_user.user_id != str(request.user_id):
        print(
            f"🚨 RECIPE: User {current_user.user_id} attempted to generate recipe for different user {request.user_id}",
            flush=True,
        )
        return RecipeErrorResponse(error="Can only generate recipes for yourself")

    try:
        # Extract Authorization header for service-to-service calls
        auth_token = http_request.headers.get("authorization", "")
        if not auth_token:
            return RecipeErrorResponse(error="Authorization header required")

        # Check rate limiting
        rate_limit_exceeded = await _check_rate_limit(db, request.user_id)
        if rate_limit_exceeded:
            return RecipeErrorResponse(
                error=f"Rate limit exceeded. Maximum {RECIPE_RATE_LIMIT} recipes per hour."
            )

        # Verify user has enough DUST
        user_balance = await _get_user_balance(request.user_id, auth_token)
        if user_balance < RECIPE_DUST_COST:
            print(
                f"💰 RECIPE: Insufficient DUST balance: {user_balance} < {RECIPE_DUST_COST}",
                flush=True,
            )
            return RecipeErrorResponse(
                error="Insufficient DUST balance",
                current_balance=user_balance,
                required_amount=RECIPE_DUST_COST,
            )

        # Validate selected people exist in user's "People in My Life"
        if request.selected_people:
            valid_people = await _validate_selected_people(
                db, request.user_id, request.selected_people
            )
            if not valid_people:
                return RecipeErrorResponse(
                    error="One or more selected people not found in your contacts"
                )

        # Get user context for personalization
        user_context = await _get_user_context(db, request.user_id, request.selected_people)
        print("👤 RECIPE: Retrieved user context", flush=True)

        # Get dietary preferences
        dietary_preferences = await _get_dietary_preferences(
            db, request.user_id, request.selected_people
        )
        print("🥗 RECIPE: Retrieved dietary preferences", flush=True)

        # Generate recipe using LLM
        (
            recipe_content,
            title,
            servings,
            prep_time,
            cook_time,
            model_used,
            tokens_used,
            cost,
        ) = await _generate_recipe_llm(
            dish=request.dish,
            complexity=request.complexity,
            include_ingredients=request.include_ingredients,
            exclude_ingredients=request.exclude_ingredients,
            total_people=request.total_people,
            user_context=user_context,
            dietary_preferences=dietary_preferences,
        )

        if not recipe_content:
            return RecipeErrorResponse(error="Failed to generate recipe. Please try again.")

        print(f"🤖 RECIPE: Generated recipe: {title}", flush=True)

        # Log LLM usage for analytics (background task)
        try:
            # Calculate prompt hash for the recipe generation
            full_prompt = _build_recipe_prompt(
                dish=request.dish,
                complexity=request.complexity,
                include_ingredients=request.include_ingredients,
                exclude_ingredients=request.exclude_ingredients,
                total_people=request.total_people,
                user_context=user_context,
                dietary_preferences=dietary_preferences,
            )
            prompt_hash = calculate_prompt_hash(full_prompt)

            # Create request metadata
            request_metadata = create_request_metadata(
                action="recipe_generation",
                parameters={
                    "dish": request.dish,
                    "complexity": request.complexity.value,
                    "include_ingredients": request.include_ingredients,
                    "exclude_ingredients": request.exclude_ingredients,
                    "total_people": request.total_people,
                    "has_selected_people": bool(request.selected_people),
                    "selected_people_count": len(request.selected_people)
                    if request.selected_people
                    else 0,
                },
                user_context=user_context if user_context != "general user" else None,
                session_id=str(request.session_id) if request.session_id else None,
            )

            # Log usage asynchronously (don't block recipe generation on logging failures)
            await log_llm_usage(
                user_id=request.user_id,
                app_id="fairydust-recipe",
                provider="anthropic",
                model_id=model_used,
                prompt_tokens=tokens_used.get("prompt", 0),
                completion_tokens=tokens_used.get("completion", 0),
                total_tokens=tokens_used.get("total", 0),
                cost_usd=cost,
                latency_ms=0,  # Recipe routes don't track latency yet
                prompt_hash=prompt_hash,
                finish_reason="stop",
                was_fallback=False,
                fallback_reason=None,
                request_metadata=request_metadata,
                auth_token=auth_token,
            )
        except Exception as e:
            print(f"⚠️ RECIPE: Failed to log LLM usage: {str(e)}", flush=True)
            # Continue with recipe generation even if logging fails

        # Save recipe to database
        recipe_metadata = {
            "dish": request.dish,
            "include_ingredients": request.include_ingredients,
            "exclude_ingredients": request.exclude_ingredients,
            "selected_people": [str(pid) for pid in request.selected_people],
            "total_people": request.total_people,
            "generation_params": {
                "complexity": request.complexity.value,
                "user_context": user_context,
                "dietary_preferences": dietary_preferences,
            },
        }

        recipe_id = await _save_recipe(
            db=db,
            user_id=request.user_id,
            title=title,
            content=recipe_content,
            complexity=request.complexity,
            servings=servings,
            prep_time_minutes=prep_time,
            cook_time_minutes=cook_time,
            session_id=request.session_id,
            model_used=model_used,
            tokens_used=tokens_used,
            cost=cost,
            metadata=recipe_metadata,
        )

        # Consume DUST after successful generation and saving
        dust_consumed = await _consume_dust(request.user_id, RECIPE_DUST_COST, auth_token, db)
        if not dust_consumed:
            print(f"❌ RECIPE: Failed to consume DUST for user {request.user_id}", flush=True)
            return RecipeErrorResponse(error="Payment processing failed")

        new_balance = user_balance - RECIPE_DUST_COST
        print(
            f"💰 RECIPE: Consumed {RECIPE_DUST_COST} DUST from user {request.user_id}",
            flush=True,
        )

        # Build response
        recipe = UserRecipeNew(
            id=recipe_id,
            title=title,
            content=recipe_content,
            complexity=request.complexity,
            servings=servings,
            prep_time_minutes=prep_time,
            cook_time_minutes=cook_time,
            created_at=datetime.utcnow(),
            is_favorited=False,
            metadata=recipe_metadata,
        )

        return RecipeGenerateResponse(
            recipe=recipe,
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
        print(f"❌ RECIPE: Unexpected error: {str(e)}", flush=True)
        print(f"❌ RECIPE: Error type: {type(e).__name__}", flush=True)
        return RecipeErrorResponse(error="Internal server error during recipe generation")


@router.get("/users/{user_id}/recipes")
async def get_user_recipes(
    user_id: uuid.UUID,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
    limit: int = Query(50, ge=1, le=100, description="Number of results to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    complexity: Optional[RecipeComplexity] = Query(None, description="Filter by complexity"),
    favorites_only: bool = Query(False, description="Return only favorited recipes"),
    search: Optional[str] = Query(None, description="Search in recipe title and content"),
):
    """
    Retrieve all saved recipes for a user, sorted by favorites first, then creation date descending.
    """
    print(f"📋 RECIPE: Getting recipes for user {user_id}", flush=True)

    # Verify user can only access their own recipes
    if current_user.user_id != str(user_id):
        print(
            f"🚨 RECIPE: User {current_user.user_id} attempted to access recipes for different user {user_id}",
            flush=True,
        )
        return RecipeErrorResponse(error="Can only access your own recipes")

    try:
        # Build query with filters
        base_query = """
            SELECT id, title, content, complexity, servings, prep_time_minutes,
                   cook_time_minutes, is_favorited, created_at, metadata
            FROM user_recipes
            WHERE user_id = $1 AND deleted_at IS NULL AND app_id = 'fairydust-recipe'
        """
        params = [user_id]
        param_count = 1

        if complexity:
            param_count += 1
            base_query += f" AND complexity = ${param_count}"
            params.append(complexity.value)

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
            FROM user_recipes
            WHERE user_id = $1 AND deleted_at IS NULL AND app_id = 'fairydust-recipe'
        """
        count_params = [user_id]

        if complexity:
            count_query += " AND complexity = $2"
            count_params.append(complexity.value)

        if search:
            param_idx = len(count_params) + 1
            count_query += f" AND (title ILIKE ${param_idx} OR content ILIKE ${param_idx})"
            count_params.append(search_pattern)

        count_result = await db.fetch_one(count_query, *count_params)
        total_count = count_result["total_count"] if count_result else 0
        favorites_count = count_result["favorites_count"] if count_result else 0

        # Build response
        recipes = []
        for row in rows:
            recipe = UserRecipeNew(
                id=row["id"],
                title=row["title"],
                content=row["content"],
                complexity=RecipeComplexity(row["complexity"])
                if row["complexity"]
                else RecipeComplexity.MEDIUM,
                servings=row["servings"] or 1,
                prep_time_minutes=row["prep_time_minutes"],
                cook_time_minutes=row["cook_time_minutes"],
                created_at=row["created_at"],
                is_favorited=row["is_favorited"],
                metadata=row["metadata"] or {},
            )
            recipes.append(recipe)

        print(f"✅ RECIPE: Returning {len(recipes)} recipes", flush=True)

        return RecipesListResponse(
            recipes=recipes,
            total_count=total_count,
            favorites_count=favorites_count,
        )

    except Exception as e:
        print(f"❌ RECIPE: Error getting recipes: {str(e)}", flush=True)
        return RecipeErrorResponse(error="Failed to retrieve recipes")


@router.post(
    "/users/{user_id}/recipes/{recipe_id}/favorite",
)
async def toggle_recipe_favorite(
    user_id: uuid.UUID,
    recipe_id: uuid.UUID,
    request: RecipeFavoriteRequest,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """
    Toggle the favorite status of a saved recipe.
    """
    print(
        f"⭐ RECIPE: Toggling favorite for recipe {recipe_id} to {request.is_favorited}",
        flush=True,
    )

    # Verify user can only modify their own recipes
    if current_user.user_id != str(user_id):
        print(
            f"🚨 RECIPE: User {current_user.user_id} attempted to modify recipe for different user {user_id}",
            flush=True,
        )
        return RecipeErrorResponse(error="Can only modify your own recipes")

    try:
        # Update favorite status
        update_query = """
            UPDATE user_recipes
            SET is_favorited = $1, updated_at = CURRENT_TIMESTAMP
            WHERE id = $2 AND user_id = $3 AND deleted_at IS NULL AND app_id = 'fairydust-recipe'
            RETURNING id, title, content, complexity, servings, prep_time_minutes,
                      cook_time_minutes, is_favorited, created_at, metadata
        """

        result = await db.fetch_one(update_query, request.is_favorited, recipe_id, user_id)

        if not result:
            return RecipeErrorResponse(error="Recipe not found", recipe_id=recipe_id)

        recipe = UserRecipeNew(
            id=result["id"],
            title=result["title"],
            content=result["content"],
            complexity=RecipeComplexity(result["complexity"])
            if result["complexity"]
            else RecipeComplexity.MEDIUM,
            servings=result["servings"] or 1,
            prep_time_minutes=result["prep_time_minutes"],
            cook_time_minutes=result["cook_time_minutes"],
            created_at=result["created_at"],
            is_favorited=result["is_favorited"],
            metadata=result["metadata"] or {},
        )

        print(f"✅ RECIPE: Updated favorite status for recipe {recipe_id}", flush=True)

        return RecipeFavoriteResponse(recipe=recipe)

    except Exception as e:
        print(f"❌ RECIPE: Error updating favorite: {str(e)}", flush=True)
        return RecipeErrorResponse(error="Failed to update favorite status")


@router.delete(
    "/users/{user_id}/recipes/{recipe_id}",
)
async def delete_recipe(
    user_id: uuid.UUID,
    recipe_id: uuid.UUID,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """
    Remove a saved recipe from user's collection (soft delete).
    """
    print(f"🗑️ RECIPE: Deleting recipe {recipe_id}", flush=True)

    # Verify user can only delete their own recipes
    if current_user.user_id != str(user_id):
        print(
            f"🚨 RECIPE: User {current_user.user_id} attempted to delete recipe for different user {user_id}",
            flush=True,
        )
        return RecipeErrorResponse(error="Can only delete your own recipes")

    try:
        # Soft delete (set deleted_at timestamp)
        delete_query = """
            UPDATE user_recipes
            SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = $1 AND user_id = $2 AND deleted_at IS NULL AND app_id = 'fairydust-recipe'
        """

        result = await db.execute(delete_query, recipe_id, user_id)

        # Check if any rows were affected
        if "UPDATE 0" in result:
            return RecipeErrorResponse(error="Recipe not found", recipe_id=recipe_id)

        print(f"✅ RECIPE: Deleted recipe {recipe_id}", flush=True)

        return RecipeDeleteResponse()

    except Exception as e:
        print(f"❌ RECIPE: Error deleting recipe: {str(e)}", flush=True)
        return RecipeErrorResponse(error="Failed to delete recipe")


@router.get("/users/{user_id}/recipe-preferences")
async def get_user_recipe_preferences(
    user_id: uuid.UUID,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """
    Retrieve user's dietary restrictions and preferences.
    """
    print(f"🥗 RECIPE_PREFS: Getting preferences for user {user_id}", flush=True)

    # Verify user can only access their own preferences
    if current_user.user_id != str(user_id):
        print(
            f"🚨 RECIPE_PREFS: User {current_user.user_id} attempted to access preferences for different user {user_id}",
            flush=True,
        )
        return RecipeErrorResponse(error="Can only access your own preferences")

    try:
        # Get user preferences
        prefs_query = """
            SELECT personal_restrictions, custom_restrictions, people_preferences
            FROM user_recipe_preferences
            WHERE user_id = $1
        """

        result = await db.fetch_one(prefs_query, user_id)

        if result:
            # Parse stored preferences
            personal_restrictions = [
                DietaryRestriction(r) for r in (result["personal_restrictions"] or [])
            ]
            custom_restrictions = result["custom_restrictions"]

            people_prefs = []
            for pref in result["people_preferences"] or []:
                # Get person name from people_in_my_life
                person_query = "SELECT name FROM people_in_my_life WHERE id = $1 AND user_id = $2"
                person_result = await db.fetch_one(person_query, pref.get("person_id"), user_id)
                person_name = person_result["name"] if person_result else None

                people_prefs.append(
                    PersonPreference(
                        person_id=pref.get("person_id"),
                        person_name=person_name,
                        selected_restrictions=[
                            DietaryRestriction(r) for r in pref.get("selected_restrictions", [])
                        ],
                        foods_to_avoid=pref.get("foods_to_avoid"),
                    )
                )

            preferences = RecipePreferences(
                personal_restrictions=personal_restrictions,
                custom_restrictions=custom_restrictions,
                people_preferences=people_prefs,
            )
        else:
            # Return empty preferences if none exist
            preferences = RecipePreferences()

        print(f"✅ RECIPE_PREFS: Retrieved preferences for user {user_id}", flush=True)

        return RecipePreferencesResponse(preferences=preferences)

    except Exception as e:
        print(f"❌ RECIPE_PREFS: Error getting preferences: {str(e)}", flush=True)
        return RecipeErrorResponse(error="Failed to retrieve preferences")


@router.put("/users/{user_id}/recipe-preferences")
async def update_user_recipe_preferences(
    user_id: uuid.UUID,
    request: RecipePreferencesUpdateRequest,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """
    Update user's dietary restrictions and preferences.
    """
    print(f"🥗 RECIPE_PREFS: Updating preferences for user {user_id}", flush=True)

    # Verify user can only update their own preferences
    if current_user.user_id != str(user_id):
        print(
            f"🚨 RECIPE_PREFS: User {current_user.user_id} attempted to update preferences for different user {user_id}",
            flush=True,
        )
        return RecipeErrorResponse(error="Can only update your own preferences")

    try:
        # Validate that all person_ids exist in user's "People in My Life"
        if request.people_preferences:
            person_ids = [pref.person_id for pref in request.people_preferences]
            valid_people = await _validate_selected_people(db, user_id, person_ids)
            if not valid_people:
                return RecipeErrorResponse(
                    error="One or more selected people not found in your contacts"
                )

        # Prepare data for storage
        personal_restrictions = [r.value for r in request.personal_restrictions]
        people_prefs_data = []

        for pref in request.people_preferences:
            people_prefs_data.append(
                {
                    "person_id": str(pref.person_id),
                    "selected_restrictions": [r.value for r in pref.selected_restrictions],
                    "foods_to_avoid": pref.foods_to_avoid,
                }
            )

        # Upsert preferences
        upsert_query = """
            INSERT INTO user_recipe_preferences (
                user_id, personal_restrictions, custom_restrictions, people_preferences,
                created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id) DO UPDATE SET
                personal_restrictions = EXCLUDED.personal_restrictions,
                custom_restrictions = EXCLUDED.custom_restrictions,
                people_preferences = EXCLUDED.people_preferences,
                updated_at = CURRENT_TIMESTAMP
            RETURNING personal_restrictions, custom_restrictions, people_preferences
        """

        result = await db.fetch_one(
            upsert_query,
            user_id,
            json.dumps(personal_restrictions),
            request.custom_restrictions,
            json.dumps(people_prefs_data),
        )

        # Build response with person names
        people_prefs_response = []
        for pref in request.people_preferences:
            # Get person name
            person_query = "SELECT name FROM people_in_my_life WHERE id = $1 AND user_id = $2"
            person_result = await db.fetch_one(person_query, pref.person_id, user_id)
            person_name = person_result["name"] if person_result else None

            people_prefs_response.append(
                PersonPreference(
                    person_id=pref.person_id,
                    person_name=person_name,
                    selected_restrictions=pref.selected_restrictions,
                    foods_to_avoid=pref.foods_to_avoid,
                )
            )

        preferences = RecipePreferences(
            personal_restrictions=request.personal_restrictions,
            custom_restrictions=request.custom_restrictions,
            people_preferences=people_prefs_response,
        )

        print(f"✅ RECIPE_PREFS: Updated preferences for user {user_id}", flush=True)

        return RecipePreferencesResponse(preferences=preferences)

    except Exception as e:
        print(f"❌ RECIPE_PREFS: Error updating preferences: {str(e)}", flush=True)
        return RecipeErrorResponse(error="Failed to update preferences")


# Helper functions
async def _get_user_balance(user_id: uuid.UUID, auth_token: str) -> int:
    """Get user's current DUST balance via Ledger Service"""
    print(f"🔍 RECIPE_BALANCE: Checking DUST balance for user {user_id}", flush=True)
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
                print(f"✅ RECIPE_BALANCE: User {user_id} has {balance} DUST", flush=True)
                return balance
            else:
                print(f"❌ RECIPE_BALANCE: Ledger service error: {response.text}", flush=True)
                return 0
    except Exception as e:
        print(f"❌ RECIPE_BALANCE: Exception getting balance: {str(e)}", flush=True)
        return 0


async def _get_app_id(db: Database) -> str:
    """Get the UUID for the fairydust-recipe app"""
    result = await db.fetch_one("SELECT id FROM apps WHERE slug = $1", "fairydust-recipe")
    if not result:
        raise HTTPException(
            status_code=500,
            detail="fairydust-recipe app not found in database. Please create the app first.",
        )
    return str(result["id"])


async def _consume_dust(user_id: uuid.UUID, amount: int, auth_token: str, db: Database) -> bool:
    """Consume DUST for recipe generation via Ledger Service"""
    print(f"🔍 RECIPE_DUST: Attempting to consume {amount} DUST for user {user_id}", flush=True)
    try:
        # Get the proper app UUID
        app_id = await _get_app_id(db)

        # Generate idempotency key to prevent double-charging
        idempotency_key = f"recipe_gen_{str(user_id).replace('-', '')[:16]}_{int(time.time())}"

        async with httpx.AsyncClient() as client:
            payload = {
                "user_id": str(user_id),
                "amount": amount,
                "app_id": app_id,
                "action": "recipe_generation",
                "idempotency_key": idempotency_key,
                "metadata": {"service": "content", "feature": "recipe_generation"},
            }

            response = await client.post(
                "https://fairydust-ledger-production.up.railway.app/transactions/consume",
                json=payload,
                headers={"Authorization": auth_token},
                timeout=10.0,
            )

            if response.status_code != 200:
                response_text = response.text
                print(f"❌ RECIPE_DUST: Error response: {response_text}", flush=True)
                return False

            print("✅ RECIPE_DUST: DUST consumption successful", flush=True)
            return True
    except Exception as e:
        print(f"❌ RECIPE_DUST: Exception consuming DUST: {str(e)}", flush=True)
        return False


async def _check_rate_limit(db: Database, user_id: uuid.UUID) -> bool:
    """Check if user has exceeded rate limit for recipe generation"""
    try:
        # Count generations in the last hour
        query = """
            SELECT COUNT(*) as generation_count
            FROM user_recipes
            WHERE user_id = $1
            AND created_at > NOW() - INTERVAL '1 hour'
            AND deleted_at IS NULL
            AND app_id = 'fairydust-recipe'
        """

        result = await db.fetch_one(query, user_id)
        generation_count = result["generation_count"] if result else 0

        if generation_count >= RECIPE_RATE_LIMIT:
            print(
                f"⚠️ RECIPE_RATE_LIMIT: User {user_id} exceeded rate limit: {generation_count}/{RECIPE_RATE_LIMIT}",
                flush=True,
            )
            return True

        print(
            f"✅ RECIPE_RATE_LIMIT: User {user_id} within limit: {generation_count}/{RECIPE_RATE_LIMIT}",
            flush=True,
        )
        return False

    except Exception as e:
        print(f"❌ RECIPE_RATE_LIMIT: Error checking rate limit: {str(e)}", flush=True)
        # Default to allowing if we can't check (fail open)
        return False


async def _validate_selected_people(
    db: Database, user_id: uuid.UUID, person_ids: list[uuid.UUID]
) -> bool:
    """Validate that all person_ids exist in user's 'People in My Life'"""
    if not person_ids:
        return True

    try:
        query = """
            SELECT COUNT(*) as count
            FROM people_in_my_life
            WHERE user_id = $1 AND id = ANY($2)
        """

        result = await db.fetch_one(query, user_id, person_ids)
        found_count = result["count"] if result else 0

        return found_count == len(person_ids)

    except Exception as e:
        print(f"❌ RECIPE_PEOPLE: Error validating people: {str(e)}", flush=True)
        return False


async def _get_user_context(
    db: Database, user_id: uuid.UUID, selected_people: list[uuid.UUID]
) -> str:
    """Get user context for personalization"""
    try:
        context_parts = []

        # Get user profile data
        profile_query = """
            SELECT field_name, field_value
            FROM user_profile_data
            WHERE user_id = $1
        """

        profile_rows = await db.fetch_all(profile_query, user_id)

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

        # Get selected people information
        if selected_people:
            people_query = """
                SELECT name, relationship, age_range
                FROM people_in_my_life
                WHERE user_id = $1 AND id = ANY($2)
            """

            people_rows = await db.fetch_all(people_query, user_id, selected_people)

            if people_rows:
                people_list = []
                for row in people_rows:
                    person_desc = f"{row['name']} ({row['relationship']}"
                    if row["age_range"]:
                        person_desc += f", {row['age_range']}"
                    person_desc += ")"
                    people_list.append(person_desc)

                context_parts.append(f"Cooking for: {', '.join(people_list)}")

        return "; ".join(context_parts) if context_parts else "general user"

    except Exception as e:
        print(f"⚠️ RECIPE_CONTEXT: Error getting user context: {str(e)}", flush=True)
        return "general user"


async def _get_dietary_preferences(
    db: Database, user_id: uuid.UUID, selected_people: list[uuid.UUID]
) -> list[str]:
    """Get merged dietary preferences for user and selected people"""
    try:
        all_restrictions = set()

        # Get user's personal restrictions
        prefs_query = """
            SELECT personal_restrictions, custom_restrictions, people_preferences
            FROM user_recipe_preferences
            WHERE user_id = $1
        """

        result = await db.fetch_one(prefs_query, user_id)

        if result:
            # Add personal restrictions
            personal_restrictions = result["personal_restrictions"] or []
            all_restrictions.update(personal_restrictions)

            # Add custom restrictions as text
            custom_restrictions = result["custom_restrictions"]
            if custom_restrictions:
                all_restrictions.add(custom_restrictions)

            # Add restrictions for selected people
            people_prefs = result["people_preferences"] or []
            for pref in people_prefs:
                if pref.get("person_id") in [str(pid) for pid in selected_people]:
                    selected_restrictions = pref.get("selected_restrictions", [])
                    all_restrictions.update(selected_restrictions)

                    foods_to_avoid = pref.get("foods_to_avoid")
                    if foods_to_avoid:
                        all_restrictions.add(f"avoid {foods_to_avoid}")

        return list(all_restrictions)

    except Exception as e:
        print(f"⚠️ RECIPE_DIETARY: Error getting dietary preferences: {str(e)}", flush=True)
        return []


async def _get_llm_model_config() -> dict:
    """Get LLM configuration for recipe app (with caching)"""
    from shared.app_config_cache import get_app_config_cache

    app_id = "fairydust-recipe"

    # Try to get from cache first
    cache = await get_app_config_cache()
    cached_config = await cache.get_model_config(app_id)

    if cached_config:
        return {
            "primary_provider": cached_config.get("primary_provider", "anthropic"),
            "primary_model_id": cached_config.get("primary_model_id", "claude-3-5-sonnet-20241022"),
            "primary_parameters": cached_config.get(
                "primary_parameters", {"temperature": 0.7, "max_tokens": 1000, "top_p": 0.9}
            ),
        }

    # Cache miss - use default config and cache it
    default_config = {
        "primary_provider": "anthropic",
        "primary_model_id": "claude-3-5-sonnet-20241022",
        "primary_parameters": {"temperature": 0.7, "max_tokens": 1000, "top_p": 0.9},
    }

    # Cache the default config for future requests
    await cache.set_model_config(app_id, default_config)

    return default_config


async def _generate_recipe_llm(
    dish: Optional[str],
    complexity: RecipeComplexity,
    include_ingredients: Optional[str],
    exclude_ingredients: Optional[str],
    total_people: int,
    user_context: str,
    dietary_preferences: list[str],
) -> tuple[Optional[str], str, int, Optional[int], Optional[int], str, dict, float]:
    """Generate recipe using LLM"""
    try:
        # Get LLM model configuration from database/cache
        model_config = await _get_llm_model_config()

        provider = model_config.get("primary_provider", "anthropic")
        model_id = model_config.get("primary_model_id", "claude-3-5-sonnet-20241022")
        parameters = model_config.get("primary_parameters", {})

        temperature = parameters.get("temperature", 0.7)
        max_tokens = parameters.get("max_tokens", 1000)
        top_p = parameters.get("top_p", 0.9)

        # Build prompt using template from specification
        servings_text = "person" if total_people == 1 else "people"
        dish_text = f" for {dish}" if dish else ""

        preferences = []
        if include_ingredients:
            preferences.append(f"include {include_ingredients}")
        if exclude_ingredients:
            preferences.append(f"avoid {exclude_ingredients}")

        preferences_text = (
            f" that incorporates these preferences: {', '.join(preferences)}" if preferences else ""
        )
        dietary_text = (
            f" and follows these dietary requirements: {', '.join(dietary_preferences)}"
            if dietary_preferences
            else ""
        )
        personalization_text = (
            f"\nPersonalization context: {user_context}" if user_context != "general user" else ""
        )

        # Build complexity-specific guidance
        complexity_guidance = {
            RecipeComplexity.SIMPLE: "Focus on easy-to-find ingredients and basic cooking techniques. Instructions should be beginner-friendly with simple steps. Avoid specialized equipment or advanced techniques.",
            RecipeComplexity.MEDIUM: "Use moderate cooking techniques and some specialty ingredients. Include techniques like sautéing, roasting, or braising. May require basic kitchen skills and equipment.",
            RecipeComplexity.GOURMET: "Create an elevated, restaurant-quality dish with sophisticated flavors and advanced techniques. Use high-quality ingredients, complex flavor profiles, specialized equipment, and professional cooking methods. Include techniques like reduction sauces, proper knife work, temperature control, plating presentation, and culinary terminology. This should be a dish worthy of a fine dining establishment.",
        }

        complexity_instruction = complexity_guidance[complexity]

        prompt = f"""Generate a {complexity.value} recipe{dish_text} that serves {total_people} {servings_text}{preferences_text}{dietary_text}{personalization_text}

{complexity_instruction}

Provide the recipe in this exact format:

🍽️ **Recipe Name**

**Prep Time:** X minutes
**Cook Time:** X minutes
**Servings:** {total_people}

**Ingredients:**
• List ingredients with amounts for {total_people} servings
• Use bullet points with exact amounts
• Scale ingredients appropriately for the serving size

**Instructions:**
1. Step-by-step instructions
2. Clear and easy to follow
3. Include cooking times and temperatures

**Nutritional Info:** Per serving - 450 calories | Protein: 25g | Carbs: 35g | Fat: 18g | Fiber: 3g

**Cooking Tip:**
One helpful tip for success with this recipe.

IMPORTANT: Always include the Nutritional Info section with estimated values."""

        print(f"🤖 RECIPE_LLM: Generating with {provider} model {model_id}", flush=True)

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
                    content = result["content"][0]["text"].strip()

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

                    # Extract recipe information
                    title = _extract_recipe_title(content, dish)
                    prep_time = _extract_time(content, "Prep Time:")
                    cook_time = _extract_time(content, "Cook Time:")

                    print("✅ RECIPE_LLM: Generated recipe successfully", flush=True)
                    return (
                        content,
                        title,
                        total_people,
                        prep_time,
                        cook_time,
                        model_id,
                        tokens_used,
                        cost,
                    )

                else:
                    print(
                        f"❌ RECIPE_LLM: Anthropic API error {response.status_code}: {response.text}",
                        flush=True,
                    )
                    return None, "", 0, None, None, model_id, {}, 0.0

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
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )

                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"].strip()

                    # Calculate tokens and cost
                    usage = result.get("usage", {})
                    prompt_tokens = usage.get("prompt_tokens", 0)
                    completion_tokens = usage.get("completion_tokens", 0)
                    total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

                    tokens_used = {
                        "prompt": prompt_tokens,
                        "completion": completion_tokens,
                        "total": total_tokens,
                    }

                    cost = calculate_llm_cost("openai", model_id, prompt_tokens, completion_tokens)

                    # Extract recipe information
                    title = _extract_recipe_title(content, dish)
                    prep_time = _extract_time(content, "Prep Time:")
                    cook_time = _extract_time(content, "Cook Time:")

                    print("✅ RECIPE_LLM: Generated recipe successfully", flush=True)
                    return (
                        content,
                        title,
                        total_people,
                        prep_time,
                        cook_time,
                        model_id,
                        tokens_used,
                        cost,
                    )

                else:
                    print(
                        f"❌ RECIPE_LLM: OpenAI API error {response.status_code}: {response.text}",
                        flush=True,
                    )
                    return None, "", 0, None, None, model_id, {}, 0.0

            else:
                print(
                    f"⚠️ RECIPE_LLM: Unsupported provider {provider}, falling back to Anthropic",
                    flush=True,
                )
                return None, "", 0, None, None, "claude-3-5-sonnet-20241022", {}, 0.0

    except Exception as e:
        print(f"❌ RECIPE_LLM: Error generating recipe: {str(e)}", flush=True)
        return None, "", 0, None, None, "claude-3-5-sonnet-20241022", {}, 0.0


def _extract_recipe_title(content: str, dish: Optional[str]) -> str:
    """Extract title from recipe content"""
    try:
        # Look for the pattern: 🍽️ **Title**
        title_match = re.search(r"🍽️\s*\*\*([^*]+)\*\*", content)
        if title_match:
            title = title_match.group(1).strip()
            return title

        # Fallback to dish name if title extraction fails
        if dish:
            return dish.title()

        # Final fallback
        return "Recipe"

    except Exception as e:
        print(f"⚠️ RECIPE_TITLE: Error extracting title: {str(e)}", flush=True)
        return dish.title() if dish else "Recipe"


def _extract_time(content: str, time_type: str) -> Optional[int]:
    """Extract prep/cook time from recipe content"""
    try:
        # Look for pattern like "Prep Time: 20 minutes"
        pattern = rf"{time_type}\s*(\d+)\s*minutes?"
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None
    except Exception:
        return None


async def _save_recipe(
    db: Database,
    user_id: uuid.UUID,
    title: str,
    content: str,
    complexity: RecipeComplexity,
    servings: int,
    prep_time_minutes: Optional[int],
    cook_time_minutes: Optional[int],
    session_id: Optional[uuid.UUID],
    model_used: str,
    tokens_used: dict,
    cost: float,
    metadata: dict,
) -> uuid.UUID:
    """Save recipe to database"""
    try:
        insert_query = """
            INSERT INTO user_recipes (
                user_id, app_id, title, content, category, complexity, servings,
                prep_time_minutes, cook_time_minutes, session_id, model_used,
                tokens_used, cost_usd, metadata, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
        """

        result = await db.fetch_one(
            insert_query,
            user_id,
            "fairydust-recipe",
            title,
            content,
            title,  # category is the title for recipes
            complexity.value,
            servings,
            prep_time_minutes,
            cook_time_minutes,
            session_id,
            model_used,
            tokens_used.get("total", 0),
            cost,
            json.dumps(metadata),
        )

        recipe_id = result["id"]
        print(f"✅ RECIPE_SAVE: Saved recipe {recipe_id}", flush=True)
        return recipe_id

    except Exception as e:
        print(f"❌ RECIPE_SAVE: Error saving recipe: {str(e)}", flush=True)
        raise HTTPException(status_code=500, detail="Failed to save recipe")
