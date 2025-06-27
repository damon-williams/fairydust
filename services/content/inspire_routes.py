# services/content/inspire_routes.py
import json
import os
import time
import uuid
from datetime import datetime
from typing import Optional

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
from shared.llm_pricing import calculate_llm_cost
from shared.llm_usage_logger import log_llm_usage, calculate_prompt_hash, create_request_metadata

router = APIRouter()

# Constants
INSPIRE_DUST_COST = 2
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
    print(f"🌟 INSPIRE: Starting generation for user {request.user_id}", flush=True)
    print(f"📂 INSPIRE: Category: {request.category}", flush=True)

    # Verify user can only generate inspirations for themselves
    if current_user.user_id != str(request.user_id):
        print(
            f"🚨 INSPIRE: User {current_user.user_id} attempted to generate inspiration for different user {request.user_id}",
            flush=True,
        )
        return InspirationErrorResponse(
            error="Can only generate inspirations for yourself"
        )

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

        # Verify user has enough DUST
        user_balance = await _get_user_balance(request.user_id, auth_token)
        if user_balance < INSPIRE_DUST_COST:
            print(
                f"💰 INSPIRE: Insufficient DUST balance: {user_balance} < {INSPIRE_DUST_COST}",
                flush=True,
            )
            return InspirationErrorResponse(
                error="Insufficient DUST balance",
                current_balance=user_balance,
                required_amount=INSPIRE_DUST_COST,
            )

        # Get user context for personalization
        user_context = await _get_user_context(db, request.user_id)
        print(f"👤 INSPIRE: Retrieved user context", flush=True)

        # Generate inspiration using LLM
        inspiration_content, model_used, tokens_used, cost = await _generate_inspiration_llm(
            category=request.category,
            used_suggestions=request.used_suggestions,
            user_context=user_context,
        )

        if not inspiration_content:
            return InspirationErrorResponse(
                error="Failed to generate inspiration. Please try again."
            )

        print(f"🤖 INSPIRE: Generated inspiration: {inspiration_content[:50]}...", flush=True)

        # Log LLM usage for analytics (background task)
        try:
            # Calculate prompt hash for the inspiration generation
            full_prompt = _build_inspiration_prompt(
                category=request.category,
                used_suggestions=request.used_suggestions,
                user_context=user_context,
            )
            prompt_hash = calculate_prompt_hash(full_prompt)
            
            # Create request metadata
            request_metadata = create_request_metadata(
                action="inspiration_generation",
                parameters={
                    "category": request.category.value,
                    "used_suggestions_count": len(request.used_suggestions) if request.used_suggestions else 0,
                },
                user_context=user_context if user_context != "general user" else None,
                session_id=str(request.session_id) if request.session_id else None,
            )
            
            # Log usage asynchronously (don't block inspiration generation on logging failures)
            await log_llm_usage(
                user_id=request.user_id,
                app_id="fairydust-inspire",
                provider="anthropic",
                model_id=model_used,
                prompt_tokens=tokens_used.get("prompt", 0),
                completion_tokens=tokens_used.get("completion", 0),
                total_tokens=tokens_used.get("total", 0),
                cost_usd=cost,
                latency_ms=0,  # Inspire routes don't track latency yet
                prompt_hash=prompt_hash,
                finish_reason="stop",
                was_fallback=False,
                fallback_reason=None,
                request_metadata=request_metadata,
                auth_token=auth_token,
            )
        except Exception as e:
            print(f"⚠️ INSPIRE: Failed to log LLM usage: {str(e)}", flush=True)
            # Continue with inspiration generation even if logging fails

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

        # Consume DUST after successful generation and saving
        dust_consumed = await _consume_dust(request.user_id, INSPIRE_DUST_COST, auth_token, db)
        if not dust_consumed:
            print(f"❌ INSPIRE: Failed to consume DUST for user {request.user_id}", flush=True)
            return InspirationErrorResponse(error="Payment processing failed")

        new_balance = user_balance - INSPIRE_DUST_COST
        print(
            f"💰 INSPIRE: Consumed {INSPIRE_DUST_COST} DUST from user {request.user_id}",
            flush=True,
        )

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
        return InspirationErrorResponse(
            error="Internal server error during inspiration generation"
        )


@router.get("/users/{user_id}/inspirations", response_model=InspirationsListResponse)
async def get_user_inspirations(
    user_id: uuid.UUID,
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
    user_id: uuid.UUID,
    inspiration_id: uuid.UUID,
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

        result = await db.fetch_one(
            update_query, request.is_favorited, inspiration_id, user_id
        )

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
    user_id: uuid.UUID,
    inspiration_id: uuid.UUID,
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
async def _get_user_balance(user_id: uuid.UUID, auth_token: str) -> int:
    """Get user's current DUST balance via Ledger Service"""
    print(f"🔍 INSPIRE_BALANCE: Checking DUST balance for user {user_id}", flush=True)
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
                print(f"✅ INSPIRE_BALANCE: User {user_id} has {balance} DUST", flush=True)
                return balance
            else:
                print(f"❌ INSPIRE_BALANCE: Ledger service error: {response.text}", flush=True)
                return 0
    except Exception as e:
        print(f"❌ INSPIRE_BALANCE: Exception getting balance: {str(e)}", flush=True)
        return 0


async def _get_app_id(db: Database) -> str:
    """Get the UUID for the fairydust-inspire app"""
    result = await db.fetch_one("SELECT id FROM apps WHERE slug = $1", "fairydust-inspire")
    if not result:
        raise HTTPException(
            status_code=500,
            detail="fairydust-inspire app not found in database. Please create the app first.",
        )
    return str(result["id"])


async def _consume_dust(user_id: uuid.UUID, amount: int, auth_token: str, db: Database) -> bool:
    """Consume DUST for inspiration generation via Ledger Service"""
    print(f"🔍 INSPIRE_DUST: Attempting to consume {amount} DUST for user {user_id}", flush=True)
    try:
        # Get the proper app UUID
        app_id = await _get_app_id(db)

        # Generate idempotency key to prevent double-charging
        idempotency_key = f"inspire_gen_{str(user_id).replace('-', '')[:16]}_{int(time.time())}"

        async with httpx.AsyncClient() as client:
            payload = {
                "user_id": str(user_id),
                "amount": amount,
                "app_id": app_id,
                "action": "inspiration_generation",
                "idempotency_key": idempotency_key,
                "metadata": {"service": "content", "feature": "inspire_generation"},
            }

            response = await client.post(
                "https://fairydust-ledger-production.up.railway.app/transactions/consume",
                json=payload,
                headers={"Authorization": auth_token},
                timeout=10.0,
            )

            if response.status_code != 200:
                response_text = response.text
                print(f"❌ INSPIRE_DUST: Error response: {response_text}", flush=True)
                return False

            print("✅ INSPIRE_DUST: DUST consumption successful", flush=True)
            return True
    except Exception as e:
        print(f"❌ INSPIRE_DUST: Exception consuming DUST: {str(e)}", flush=True)
        return False


async def _check_rate_limit(db: Database, user_id: uuid.UUID) -> bool:
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
        print(f"⚠️ INSPIRE_CONTEXT: Error getting user context: {str(e)}", flush=True)
        return "general user"


async def _get_llm_model_config() -> dict:
    """Get LLM configuration for inspire app (with caching)"""
    from shared.app_config_cache import get_app_config_cache

    app_id = "fairydust-inspire"

    # Try to get from cache first
    cache = await get_app_config_cache()
    cached_config = await cache.get_model_config(app_id)

    if cached_config:
        return {
            "primary_provider": cached_config.get("primary_provider", "anthropic"),
            "primary_model_id": cached_config.get("primary_model_id", "claude-3-haiku-20240307"),
            "primary_parameters": cached_config.get(
                "primary_parameters", {"temperature": 0.8, "max_tokens": 150, "top_p": 0.9}
            ),
        }

    # Cache miss - use default config and cache it
    default_config = {
        "primary_provider": "anthropic",
        "primary_model_id": "claude-3-haiku-20240307",
        "primary_parameters": {"temperature": 0.8, "max_tokens": 150, "top_p": 0.9},
    }

    # Cache the default config for future requests
    await cache.set_model_config(app_id, default_config)

    return default_config


async def _generate_inspiration_llm(
    category: InspirationCategory,
    used_suggestions: list[str],
    user_context: str,
) -> tuple[Optional[str], str, dict, float]:
    """Generate inspiration using LLM"""
    try:
        # Get LLM model configuration from database/cache
        model_config = await _get_llm_model_config()
        
        provider = model_config.get("primary_provider", "anthropic")
        model_id = model_config.get("primary_model_id", "claude-3-haiku-20240307")
        parameters = model_config.get("primary_parameters", {})
        
        temperature = parameters.get("temperature", 0.8)
        max_tokens = parameters.get("max_tokens", 150)
        top_p = parameters.get("top_p", 0.9)

        # Build prompt
        base_prompt = CATEGORY_PROMPTS[category]

        # Add context and anti-duplication
        context_prompt = f"Context: User is a {user_context}. "

        anti_dup_prompt = ""
        if used_suggestions:
            suggestions_text = "\n".join([f"- {s}" for s in used_suggestions[-10:]])
            anti_dup_prompt = f"\n\nAvoid suggesting anything similar to these recent suggestions:\n{suggestions_text}\n\n"

        full_prompt = f"{context_prompt}{base_prompt}{anti_dup_prompt}Respond with just the inspiration text, nothing else."

        print(f"🤖 INSPIRE_LLM: Generating with {provider} model {model_id}", flush=True)

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
                        "messages": [{"role": "user", "content": full_prompt}],
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

                    cost = calculate_llm_cost("anthropic", model_id, prompt_tokens, completion_tokens)

                    print(f"✅ INSPIRE_LLM: Generated inspiration successfully", flush=True)
                    return content, model_id, tokens_used, cost

                else:
                    print(
                        f"❌ INSPIRE_LLM: Anthropic API error {response.status_code}: {response.text}",
                        flush=True,
                    )
                    return None, model_id, {}, 0.0

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

                    # Calculate cost using shared pricing module
                    cost = calculate_llm_cost("openai", model_id, prompt_tokens, completion_tokens)

                    print(f"✅ INSPIRE_LLM: Generated inspiration successfully", flush=True)
                    return content, model_id, tokens_used, cost

                else:
                    print(
                        f"❌ INSPIRE_LLM: OpenAI API error {response.status_code}: {response.text}",
                        flush=True,
                    )
                    return None, model_id, {}, 0.0

            else:
                print(
                    f"⚠️ INSPIRE_LLM: Unsupported provider {provider}, falling back to Anthropic",
                    flush=True,
                )
                # Fallback to Anthropic with default model
                return await _generate_inspiration_llm(category, used_suggestions, user_context)

    except Exception as e:
        print(f"❌ INSPIRE_LLM: Error generating inspiration: {str(e)}", flush=True)
        return None, "claude-3-haiku-20240307", {}, 0.0


async def _save_inspiration(
    db: Database,
    user_id: uuid.UUID,
    content: str,
    category: InspirationCategory,
    session_id: Optional[uuid.UUID],
    model_used: str,
    tokens_used: dict,
    cost: float,
) -> uuid.UUID:
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