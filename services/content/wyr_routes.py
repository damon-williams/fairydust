# services/content/wyr_routes.py
import json
import os
import random
import uuid
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from models import (
    AnswerObject,
    GameCategory,
    GameLength,
    GameStatus,
    QuestionObject,
    TokenUsage,
    WyrGameCompleteResponse,
    WyrGameDeleteResponse,
    WyrGameErrorResponse,
    WyrGameSession,
    WyrGameSessionComplete,
    WyrGameSessionCreate,
    WyrGameSessionProgress,
    WyrGameSessionResponse,
    WyrGameSessionsResponse,
)

from shared.auth_middleware import TokenData, get_current_user
from shared.database import Database, get_db
from shared.json_utils import parse_jsonb_field, safe_json_parse
from shared.llm_pricing import calculate_llm_cost
from shared.llm_usage_logger import calculate_prompt_hash, create_request_metadata, log_llm_usage

router = APIRouter()

# Constants
WYR_RATE_LIMIT = 20  # Max 20 game sessions per hour per user

# Category display names
CATEGORY_NAMES = {
    GameCategory.THOUGHT_PROVOKING: "🧠 Thought-Provoking",
    GameCategory.FUNNY_SILLY: "😂 Funny & Silly",
    GameCategory.FAMILY_FRIENDLY: "👨‍👩‍👧 Family-Friendly",
    GameCategory.WORK_CAREER: "💼 Work & Career",
    GameCategory.RELATIONSHIPS_LOVE: "💕 Relationships & Love",
    GameCategory.FANTASY_SUPERPOWERS: "🧙 Fantasy & Superpowers",
    GameCategory.POP_CULTURE: "🎬 Pop Culture",
    GameCategory.TRAVEL_ADVENTURE: "🌍 Travel & Adventure",
    GameCategory.MIX_IT_UP: "🎲 Mix It Up",
}


@router.post("/apps/would-you-rather/start-game", response_model=WyrGameSessionResponse)
async def start_new_game_session(
    request: WyrGameSessionCreate,
    http_request: Request,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Start a new Would You Rather game session"""
    print(f"🎮 WYR: Starting new game for user {request.user_id}", flush=True)
    print(f"📊 WYR: Length: {request.game_length}, Category: {request.category}", flush=True)

    # Verify user can only create games for themselves
    if current_user.user_id != str(request.user_id):
        print(
            f"🚨 WYR: User {current_user.user_id} attempted to create game for different user {request.user_id}",
            flush=True,
        )
        raise HTTPException(status_code=403, detail="Can only create games for yourself")

    try:
        # Extract Authorization header for service-to-service calls
        auth_token = http_request.headers.get("authorization", "")
        if not auth_token:
            raise HTTPException(status_code=401, detail="Authorization header required")

        # Check rate limiting
        rate_limit_exceeded = await _check_rate_limit(db, request.user_id)
        if rate_limit_exceeded:
            raise HTTPException(
                status_code=429, 
                detail=f"Rate limit exceeded. Maximum {WYR_RATE_LIMIT} games per hour."
            )

        # Generate questions using LLM
        print("🤖 WYR: Generating questions", flush=True)
        (
            questions,
            provider_used,
            model_used,
            tokens_used,
            cost,
            latency_ms,
        ) = await _generate_questions_llm(
            game_length=request.game_length,
            category=request.category,
            custom_request=request.custom_request,
            user_id=request.user_id,
            db=db,
        )

        if not questions:
            print("❌ WYR: Question generation failed", flush=True)
            raise HTTPException(
                status_code=500, 
                detail="Failed to generate questions. Please try again."
            )

        print(f"✅ WYR: Generated {len(questions)} questions", flush=True)

        # Log LLM usage for analytics
        try:
            prompt_hash = calculate_prompt_hash(f"WYR_{request.category}_{request.game_length}")
            request_metadata = create_request_metadata(
                action="wyr_question_generation",
                parameters={
                    "game_length": request.game_length,
                    "category": request.category.value,
                    "has_custom_request": bool(request.custom_request),
                },
                user_context=None,
                session_id=None,
            )

            await log_llm_usage(
                user_id=request.user_id,
                app_id="fairydust-would-you-rather",
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
            print(f"⚠️ WYR: Failed to log LLM usage: {str(e)}", flush=True)

        # Save session to database
        session_id = await _save_game_session(
            db=db,
            user_id=request.user_id,
            game_length=request.game_length,
            category=request.category,
            custom_request=request.custom_request,
            questions=questions,
        )

        print(f"✅ WYR: Created session {session_id}", flush=True)

        # Build response
        session = WyrGameSession(
            session_id=session_id,
            user_id=request.user_id,
            game_length=request.game_length,
            category=request.category.value,
            custom_request=request.custom_request,
            status=GameStatus.IN_PROGRESS,
            current_question=1,
            started_at=datetime.utcnow(),
            completed_at=None,
            questions=questions,
            answers=[],
            summary=None,
        )

        return WyrGameSessionResponse(session=session)

    except Exception as e:
        print(f"❌ WYR: Unexpected error: {str(e)}", flush=True)
        raise HTTPException(
            status_code=500,
            detail="Internal server error during game creation"
        )


@router.put("/apps/would-you-rather/sessions/{session_id}/progress", response_model=WyrGameSessionResponse)
async def save_answer_progress(
    session_id: uuid.UUID = Path(..., description="Session ID"),
    request: WyrGameSessionProgress = ...,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Save answer progress for a game session"""
    print(f"💾 WYR: Saving progress for session {session_id}", flush=True)

    try:
        # Get existing session
        session_data = await _get_session(db, session_id, current_user.user_id)
        if not session_data:
            raise HTTPException(
                status_code=404,
                detail="Session not found or access denied"
            )

        # Check if session is already completed
        if session_data["status"] == "completed":
            raise HTTPException(
                status_code=400,
                detail="Cannot modify completed session"
            )

        # Parse existing data
        existing_questions = safe_json_parse(session_data["questions"], default=[], expected_type=list)
        existing_answers = safe_json_parse(session_data["answers"], default=[], expected_type=list)

        # Validate question exists
        question_exists = any(q.get("id") == str(request.question_id) for q in existing_questions)
        if not question_exists:
            raise HTTPException(
                status_code=400,
                detail="Invalid question ID"
            )

        # Update or add answer
        answer_updated = False
        for i, answer in enumerate(existing_answers):
            if answer.get("question_id") == str(request.question_id):
                existing_answers[i] = {
                    "question_id": str(request.question_id),
                    "chosen_option": request.chosen_option,
                    "answered_at": datetime.utcnow().isoformat(),
                }
                answer_updated = True
                break

        if not answer_updated:
            existing_answers.append({
                "question_id": str(request.question_id),
                "chosen_option": request.chosen_option,
                "answered_at": datetime.utcnow().isoformat(),
            })

        # Update session
        update_query = """
            UPDATE wyr_game_sessions
            SET current_question = $1, answers = $2::jsonb, updated_at = CURRENT_TIMESTAMP
            WHERE id = $3 AND user_id = $4
            RETURNING *
        """

        updated_session = await db.fetch_one(
            update_query,
            request.current_question,
            json.dumps(existing_answers),
            session_id,
            uuid.UUID(current_user.user_id),
        )

        if not updated_session:
            raise HTTPException(
                status_code=500,
                detail="Failed to update session"
            )

        # Build response
        session = await _build_session_response(updated_session)
        print(f"✅ WYR: Updated progress for session {session_id}", flush=True)

        return WyrGameSessionResponse(session=session)

    except Exception as e:
        print(f"❌ WYR: Error updating progress: {str(e)}", flush=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to save progress"
        )


@router.post("/apps/would-you-rather/sessions/{session_id}/complete", response_model=WyrGameCompleteResponse)
async def complete_game_session(
    session_id: uuid.UUID = Path(..., description="Session ID"),
    request: WyrGameSessionComplete = ...,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Complete a game session and generate personality analysis"""
    print(f"🏁 WYR: Completing session {session_id}", flush=True)

    try:
        # Get existing session
        session_data = await _get_session(db, session_id, current_user.user_id)
        if not session_data:
            raise HTTPException(
                status_code=404,
                detail="Session not found or access denied"
            )

        # Check if already completed
        if session_data["status"] == "completed":
            session = await _build_session_response(session_data)
            # Scrub completed session to only show chosen options
            scrubbed_session = _scrub_completed_session(session)
            return WyrGameCompleteResponse(
                session=scrubbed_session,
                summary=session_data["summary"] or "Analysis not available"
            )

        # Generate personality analysis
        print("🧠 WYR: Generating personality analysis", flush=True)
        summary = await _generate_personality_analysis(
            questions=safe_json_parse(session_data["questions"], default=[], expected_type=list),
            answers=request.final_answers,
            category=session_data["category"],
            user_id=uuid.UUID(current_user.user_id),
            db=db,
        )

        # Update session as completed
        complete_query = """
            UPDATE wyr_game_sessions
            SET status = 'completed', completed_at = CURRENT_TIMESTAMP, 
                summary = $1, answers = $2::jsonb, updated_at = CURRENT_TIMESTAMP
            WHERE id = $3 AND user_id = $4
            RETURNING *
        """

        completed_session = await db.fetch_one(
            complete_query,
            summary,
            json.dumps([answer.model_dump(mode='json') for answer in request.final_answers]),
            session_id,
            uuid.UUID(current_user.user_id),
        )

        if not completed_session:
            raise HTTPException(
                status_code=500,
                detail="Failed to complete session"
            )

        session = await _build_session_response(completed_session)
        
        # Scrub questions to only show chosen options
        scrubbed_session = _scrub_completed_session(session)
        print(f"✅ WYR: Completed session {session_id}", flush=True)

        return WyrGameCompleteResponse(session=scrubbed_session, summary=summary)

    except Exception as e:
        print(f"❌ WYR: Error completing session: {str(e)}", flush=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to complete session"
        )


@router.get("/users/{user_id}/would-you-rather/sessions", response_model=WyrGameSessionsResponse)
async def get_user_sessions(
    user_id: uuid.UUID = Path(..., description="User ID"),
    limit: int = Query(50, ge=1, le=100, description="Number of results to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    status: str = Query("all", description="Filter by status: all|in_progress|completed"),
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get all game sessions for a user"""
    print(f"📋 WYR: Getting sessions for user {user_id}", flush=True)

    # Verify user can only access their own sessions
    if current_user.user_id != str(user_id):
        raise HTTPException(
            status_code=403,
            detail="Can only access your own sessions"
        )

    try:
        # Build query with filters
        base_query = """
            SELECT id, user_id, game_length, category, custom_request, status,
                   current_question, started_at, completed_at, summary, questions, answers
            FROM wyr_game_sessions
            WHERE user_id = $1
        """
        params = [user_id]
        param_count = 1

        if status in ["in_progress", "completed"]:
            param_count += 1
            base_query += f" AND status = ${param_count}"
            params.append(status)

        # Order by creation date descending
        base_query += " ORDER BY created_at DESC"

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
                COUNT(*) FILTER (WHERE status = 'in_progress') as in_progress_count,
                COUNT(*) FILTER (WHERE status = 'completed') as completed_count
            FROM wyr_game_sessions
            WHERE user_id = $1
        """
        count_params = [user_id]

        if status in ["in_progress", "completed"]:
            count_query += " AND status = $2"
            count_params.append(status)

        count_result = await db.fetch_one(count_query, *count_params)
        total_count = count_result["total_count"] if count_result else 0
        in_progress_count = count_result["in_progress_count"] if count_result else 0
        completed_count = count_result["completed_count"] if count_result else 0

        # Build response
        sessions = []
        for row in rows:
            session = await _build_session_response(row)
            
            # Scrub completed sessions to only show chosen options
            if session.status == GameStatus.COMPLETED:
                session = _scrub_completed_session(session)
                
            sessions.append(session)

        print(f"✅ WYR: Returning {len(sessions)} sessions", flush=True)

        return WyrGameSessionsResponse(
            sessions=sessions,
            total_count=total_count,
            in_progress_count=in_progress_count,
            completed_count=completed_count,
        )

    except Exception as e:
        print(f"❌ WYR: Error getting sessions: {str(e)}", flush=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve sessions"
        )


@router.get("/apps/would-you-rather/sessions/{session_id}", response_model=WyrGameSessionResponse)
async def get_single_session(
    session_id: uuid.UUID = Path(..., description="Session ID"),
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get a single game session"""
    print(f"📄 WYR: Getting session {session_id}", flush=True)

    try:
        session_data = await _get_session(db, session_id, current_user.user_id)
        if not session_data:
            raise HTTPException(
                status_code=404,
                detail="Session not found or access denied"
            )

        session = await _build_session_response(session_data)
        
        # Scrub completed sessions to only show chosen options
        if session.status == GameStatus.COMPLETED:
            session = _scrub_completed_session(session)
            
        return WyrGameSessionResponse(session=session)

    except Exception as e:
        print(f"❌ WYR: Error getting session: {str(e)}", flush=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve session"
        )


@router.delete("/apps/would-you-rather/sessions/{session_id}", response_model=WyrGameDeleteResponse)
async def delete_session(
    session_id: uuid.UUID = Path(..., description="Session ID"),
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Delete a game session"""
    print(f"🗑️ WYR: Deleting session {session_id}", flush=True)

    try:
        # Verify session exists and belongs to user
        session_data = await _get_session(db, session_id, current_user.user_id)
        if not session_data:
            raise HTTPException(
                status_code=404,
                detail="Session not found or access denied"
            )

        # Delete session
        delete_query = """
            DELETE FROM wyr_game_sessions
            WHERE id = $1 AND user_id = $2
        """

        result = await db.execute(delete_query, session_id, uuid.UUID(current_user.user_id))

        if "DELETE 0" in result:
            raise HTTPException(
                status_code=500,
                detail="Failed to delete session"
            )

        print(f"✅ WYR: Deleted session {session_id}", flush=True)
        return WyrGameDeleteResponse()

    except Exception as e:
        print(f"❌ WYR: Error deleting session: {str(e)}", flush=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to delete session"
        )


# Helper functions

async def _check_rate_limit(db: Database, user_id: uuid.UUID) -> bool:
    """Check if user has exceeded rate limit for game creation"""
    try:
        query = """
            SELECT COUNT(*) as session_count
            FROM wyr_game_sessions
            WHERE user_id = $1
            AND created_at > NOW() - INTERVAL '1 hour'
        """

        result = await db.fetch_one(query, user_id)
        session_count = result["session_count"] if result else 0

        if session_count >= WYR_RATE_LIMIT:
            print(
                f"⚠️ WYR_RATE_LIMIT: User {user_id} exceeded rate limit: {session_count}/{WYR_RATE_LIMIT}",
                flush=True,
            )
            return True

        print(
            f"✅ WYR_RATE_LIMIT: User {user_id} within limit: {session_count}/{WYR_RATE_LIMIT}",
            flush=True,
        )
        return False

    except Exception as e:
        print(f"❌ WYR_RATE_LIMIT: Error checking rate limit: {str(e)}", flush=True)
        return False


async def _get_user_age_context(db: Database, user_id: uuid.UUID) -> str:
    """Get user age context for content filtering"""
    try:
        # Get user birth date
        user_query = """
            SELECT birth_date FROM users WHERE id = $1
        """
        
        user_result = await db.fetch_one(user_query, user_id)
        if not user_result or not user_result["birth_date"]:
            return "general audience"

        # Calculate age
        from datetime import date
        birth_date = user_result["birth_date"]
        if isinstance(birth_date, str):
            birth_date = date.fromisoformat(birth_date)
        
        age = (date.today() - birth_date).days // 365

        if age < 13:
            return "children (under 13)"
        elif age < 18:
            return "teenagers (13-17)"
        elif age < 25:
            return "young adults (18-24)"
        else:
            return "adults (25+)"

    except Exception as e:
        print(f"⚠️ WYR_AGE: Error getting user age: {str(e)}", flush=True)
        return "general audience"


async def _get_wyr_llm_model_config() -> dict:
    """Get LLM configuration for Would You Rather app (with caching)"""
    from shared.app_config_cache import get_app_config_cache
    from shared.database import get_db

    app_slug = "fairydust-would-you-rather"

    # First, get the app UUID from the slug
    db = await get_db()
    app_result = await db.fetch_one("SELECT id FROM apps WHERE slug = $1", app_slug)

    if not app_result:
        print(f"❌ WYR_CONFIG: App not found for slug: {app_slug}", flush=True)
        return {
            "primary_provider": "anthropic",
            "primary_model_id": "claude-3-5-sonnet-20241022",
            "primary_parameters": {"temperature": 0.7, "max_tokens": 1000, "top_p": 0.9},
        }

    app_id = str(app_result["id"])
    print(f"📊 WYR_CONFIG: Found app ID: {app_id}", flush=True)

    # Try to get cached config first
    try:
        cache = await get_app_config_cache()
    except Exception as e:
        print(f"❌ WYR_CONFIG: Cache unavailable: {e}", flush=True)
        cache = None

    if cache:
        cached_config = await cache.get_model_config(app_id)

        if cached_config:
            print("✅ WYR_CONFIG: Found cached config", flush=True)
            print(f"✅ WYR_CONFIG: Provider: {cached_config.get('primary_provider')}", flush=True)
            print(f"✅ WYR_CONFIG: Model: {cached_config.get('primary_model_id')}", flush=True)

            config = {
                "primary_provider": cached_config.get("primary_provider", "anthropic"),
                "primary_model_id": cached_config.get("primary_model_id", "claude-3-5-sonnet-20241022"),
                "primary_parameters": cached_config.get(
                    "primary_parameters", {"temperature": 0.7, "max_tokens": 1000, "top_p": 0.9}
                ),
            }

            print(f"✅ WYR_CONFIG: Returning cached config: {config}", flush=True)
            return config

    # Cache miss - check database directly
    print("⚠️ WYR_CONFIG: Cache miss, checking database directly", flush=True)

    try:
        db_config = await db.fetch_one("SELECT * FROM app_model_configs WHERE app_id = $1", app_id)

        if db_config:
            print("📊 WYR_CONFIG: Found database config", flush=True)
            print(f"📊 WYR_CONFIG: DB Provider: {db_config['primary_provider']}", flush=True)
            print(f"📊 WYR_CONFIG: DB Model: {db_config['primary_model_id']}", flush=True)

            # Parse and cache the database config
            from shared.json_utils import parse_model_config_field

            parsed_config = {
                "primary_provider": db_config["primary_provider"],
                "primary_model_id": db_config["primary_model_id"],
                "primary_parameters": parse_model_config_field(
                    dict(db_config), "primary_parameters"
                )
                or {"temperature": 0.7, "max_tokens": 1000, "top_p": 0.9},
            }

            # Cache the database config
            if cache:
                await cache.set_model_config(app_id, parsed_config)
                print(f"✅ WYR_CONFIG: Cached database config: {parsed_config}", flush=True)

            return parsed_config

    except Exception as e:
        print(f"❌ WYR_CONFIG: Database error: {e}", flush=True)

    # Fallback to default config
    print("🔄 WYR_CONFIG: Using default config (no cache, no database)", flush=True)
    default_config = {
        "primary_provider": "anthropic",
        "primary_model_id": "claude-3-5-sonnet-20241022",
        "primary_parameters": {"temperature": 0.7, "max_tokens": 1000, "top_p": 0.9},
    }

    # Cache the default config
    if cache:
        await cache.set_model_config(app_id, default_config)
        print(f"✅ WYR_CONFIG: Cached default config: {default_config}", flush=True)

    return default_config


async def _generate_questions_llm(
    game_length: GameLength,
    category: GameCategory,
    custom_request: Optional[str],
    user_id: uuid.UUID,
    db: Database,
) -> tuple[list[QuestionObject], str, str, dict, float, int]:
    """Generate questions using LLM"""
    try:
        # Get user age context
        age_context = await _get_user_age_context(db, user_id)
        
        # Build prompt
        prompt = _build_questions_prompt(game_length, category, custom_request, age_context)

        # Get LLM model configuration from database/cache
        model_config = await _get_wyr_llm_model_config()

        provider = model_config.get("primary_provider", "anthropic")
        model_id = model_config.get("primary_model_id", "claude-3-5-sonnet-20241022")
        parameters = model_config.get("primary_parameters", {})
        
        temperature = parameters.get("temperature", 0.7)
        max_tokens = parameters.get("max_tokens", 1000)
        top_p = parameters.get("top_p", 0.9)

        print(f"🔧 WYR_LLM: Using provider: {provider}, model: {model_id}", flush=True)
        print(f"🔧 WYR_LLM: Parameters - temp: {temperature}, max_tokens: {max_tokens}, top_p: {top_p}", flush=True)

        start_time = datetime.now()
        
        if provider.lower() == "openai":
            # OpenAI API call
            api_key = os.getenv("OPENAI_API_KEY", "")
            if not api_key:
                print("❌ WYR_LLM: Missing OPENAI_API_KEY", flush=True)
                return [], provider, model_id, {}, 0.0, 0

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}",
                    },
                    json={
                        "model": model_id,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                        "top_p": top_p,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
        else:
            # Anthropic API call (default)
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            if not api_key:
                print("❌ WYR_LLM: Missing ANTHROPIC_API_KEY", flush=True)
                return [], provider, model_id, {}, 0.0, 0

            async with httpx.AsyncClient(timeout=30.0) as client:
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
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )

        latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        if response.status_code == 200:
            result = response.json()
            
            # Parse content based on provider
            if provider.lower() == "openai":
                content = result["choices"][0]["message"]["content"].strip()
                usage = result.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                total_tokens = usage.get("total_tokens", 0)
            else:
                # Anthropic format
                content = result["content"][0]["text"].strip()
                usage = result.get("usage", {})
                prompt_tokens = usage.get("input_tokens", 0)
                completion_tokens = usage.get("output_tokens", 0)
                total_tokens = prompt_tokens + completion_tokens

            # Parse questions from response
            questions = _parse_questions_response(content, category)
            
            tokens_used = {
                "prompt": prompt_tokens,
                "completion": completion_tokens,
                "total": total_tokens,
            }

            cost = calculate_llm_cost(provider, model_id, prompt_tokens, completion_tokens)

            print(f"✅ WYR_LLM: Generated {len(questions)} questions", flush=True)
            return questions, provider, model_id, tokens_used, cost, latency_ms

        else:
            print(f"❌ WYR_LLM: API error {response.status_code}: {response.text}", flush=True)
            return [], provider, model_id, {}, 0.0, latency_ms

    except Exception as e:
        print(f"❌ WYR_LLM: Error generating questions: {str(e)}", flush=True)
        return [], "anthropic", "claude-3-5-sonnet-20241022", {}, 0.0, 0


def _build_questions_prompt(
    game_length: GameLength,
    category: GameCategory,
    custom_request: Optional[str],
    age_context: str,
) -> str:
    """Build the LLM prompt for question generation"""
    
    category_descriptions = {
        GameCategory.THOUGHT_PROVOKING: "Deep philosophical questions that make you think about values, morality, and life choices",
        GameCategory.FUNNY_SILLY: "Lighthearted, humorous questions that are entertaining and playful",
        GameCategory.FAMILY_FRIENDLY: "Simple, wholesome questions using easy words that children can understand and families can enjoy together",
        GameCategory.WORK_CAREER: "Professional scenarios and career-related dilemmas",
        GameCategory.RELATIONSHIPS_LOVE: "Questions about friendship, romance, and human connections",
        GameCategory.FANTASY_SUPERPOWERS: "Magical abilities, fictional scenarios, and superhero choices",
        GameCategory.POP_CULTURE: "Movies, music, celebrities, and entertainment",
        GameCategory.TRAVEL_ADVENTURE: "Exploration, travel destinations, and adventurous experiences",
        GameCategory.MIX_IT_UP: "A random mix from all categories for variety",
    }

    base_prompt = f"""Create exactly {game_length.value} "Would You Rather" questions for a {age_context} audience.

CATEGORY: {category_descriptions.get(category, category.value)}"""

    if custom_request:
        base_prompt += f"""
CUSTOM THEME: {custom_request}"""

    if category == GameCategory.MIX_IT_UP:
        base_prompt += f"""

VARIETY REQUIREMENT: Since this is "Mix It Up", include questions from different categories:
- {game_length.value // 3} thought-provoking questions
- {game_length.value // 3} funny/silly questions  
- Remaining questions from other categories (relationships, fantasy, pop culture, etc.)"""

    base_prompt += f"""

AGE APPROPRIATENESS: Content must be suitable for {age_context}"""

    # Add specific child-friendly guidance for family-friendly category or young audiences
    if category == GameCategory.FAMILY_FRIENDLY or "children" in age_context.lower():
        base_prompt += """

CHILD-FRIENDLY REQUIREMENTS:
- Use simple, everyday words a 6-year-old can understand
- Focus on fun, innocent choices (animals, food, toys, games, colors)
- Avoid complex concepts, adult themes, or anything scary
- Make questions about things kids enjoy and relate to
- Examples: "pizza or ice cream", "cats or dogs", "playground or pool"
- NO adult concepts like money, work, relationships, or complex scenarios"""

    base_prompt += """

QUALITY REQUIREMENTS:
- Each question should present two genuinely difficult choices
- Options should be balanced (neither obviously better)
- Questions should spark interesting discussions
- Avoid offensive, inappropriate, or insensitive content
- Make dilemmas meaningful and engaging

FORMAT: Return ONLY a valid JSON array of objects with this exact structure (no other text):
[
  {{
    "question_number": 1,
    "option_a": "First choice description",
    "option_b": "Second choice description",
    "category": "{category.value if category != GameCategory.MIX_IT_UP else 'varies'}"
  }}
]

EXAMPLES of good "Would You Rather" questions:"""

    # Add age-appropriate examples
    if category == GameCategory.FAMILY_FRIENDLY or "children" in age_context.lower():
        base_prompt += """
- "Would you rather have a pet dragon or a pet unicorn?"
- "Would you rather eat ice cream for breakfast or cookies for dinner?"
- "Would you rather be able to talk to animals or make toys come to life?"
- "Would you rather live in a treehouse or a castle made of candy?"
- "Would you rather have super speed or super strength?"
"""
    else:
        base_prompt += """
- "Would you rather have the ability to fly but only 3 feet off the ground, or be invisible but only when no one is looking?"
- "Would you rather always know when someone is lying but never be able to prove it, or never know when someone is lying but always trust people?"
"""

    base_prompt += f"""Generate exactly {game_length.value} creative, engaging questions now.

IMPORTANT: Return ONLY the JSON array, no explanations, no additional text."""

    return base_prompt


def _parse_questions_response(content: str, category: GameCategory) -> list[QuestionObject]:
    """Parse LLM response into QuestionObject list"""
    try:
        # Try to extract JSON from response
        import re
        
        # Debug: Print the actual response content
        print(f"🔍 WYR_PARSE: OpenAI response content: {content[:500]}...", flush=True)
        
        # Look for JSON array in the response - try multiple patterns
        json_match = None
        
        # Pattern 1: Direct JSON array
        json_match = re.search(r'\[.*\]', content, re.DOTALL)
        
        # Pattern 2: JSON in markdown code blocks
        if not json_match:
            json_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', content, re.DOTALL)
            if json_match:
                json_match = type('Match', (), {'group': lambda: json_match.group(1)})()
        
        # Pattern 3: JSON after some introductory text
        if not json_match:
            json_match = re.search(r'(?:here|questions|array).*?(\[.*\])', content, re.DOTALL | re.IGNORECASE)
            if json_match:
                json_match = type('Match', (), {'group': lambda: json_match.group(1)})()
        
        if not json_match:
            print("❌ WYR_PARSE: No JSON array found in response", flush=True)
            print(f"🔍 WYR_PARSE: Full response was: {content}", flush=True)
            return []

        questions_data = json.loads(json_match.group())
        questions = []

        for i, q_data in enumerate(questions_data):
            question = QuestionObject(
                id=uuid.uuid4(),
                question_number=q_data.get("question_number", i + 1),
                option_a=q_data.get("option_a", ""),
                option_b=q_data.get("option_b", ""),
                category=q_data.get("category", category.value),
            )
            questions.append(question)

        return questions

    except Exception as e:
        print(f"❌ WYR_PARSE: Error parsing questions: {str(e)}", flush=True)
        return []


async def _save_game_session(
    db: Database,
    user_id: uuid.UUID,
    game_length: GameLength,
    category: GameCategory,
    custom_request: Optional[str],
    questions: list[QuestionObject],
) -> uuid.UUID:
    """Save new game session to database"""
    try:
        session_id = uuid.uuid4()

        insert_query = """
            INSERT INTO wyr_game_sessions (
                id, user_id, game_length, category, custom_request, status,
                current_question, questions, answers, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, 'in_progress', 1, $6::jsonb, '[]'::jsonb,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """

        # Convert questions to JSON, ensuring UUIDs are properly serialized
        questions_json = json.dumps([q.model_dump(mode='json') for q in questions])

        await db.execute(
            insert_query,
            session_id,
            user_id,
            game_length,
            category.value,
            custom_request,
            questions_json,
        )

        print(f"✅ WYR_SAVE: Saved session {session_id}", flush=True)
        return session_id

    except Exception as e:
        print(f"❌ WYR_SAVE: Error saving session: {str(e)}", flush=True)
        raise


async def _get_session(db: Database, session_id: uuid.UUID, user_id: str) -> Optional[dict]:
    """Get session by ID and verify ownership"""
    try:
        query = """
            SELECT id, user_id, game_length, category, custom_request, status,
                   current_question, started_at, completed_at, summary, questions, answers
            FROM wyr_game_sessions
            WHERE id = $1 AND user_id = $2
        """

        result = await db.fetch_one(query, session_id, uuid.UUID(user_id))
        return dict(result) if result else None

    except Exception as e:
        print(f"❌ WYR_GET: Error getting session: {str(e)}", flush=True)
        return None


async def _build_session_response(session_data: dict) -> WyrGameSession:
    """Build WyrGameSession response from database data"""
    try:
        questions_data = safe_json_parse(session_data["questions"], default=[], expected_type=list)
        answers_data = safe_json_parse(session_data["answers"], default=[], expected_type=list)

        questions = [
            QuestionObject(
                id=uuid.UUID(q["id"]),
                question_number=q["question_number"],
                option_a=q["option_a"],
                option_b=q["option_b"],
                category=q["category"],
            )
            for q in questions_data
        ]

        answers = [
            AnswerObject(
                question_id=uuid.UUID(a["question_id"]),
                chosen_option=a.get("chosen_option"),
                answered_at=datetime.fromisoformat(a["answered_at"]) if a.get("answered_at") else None,
            )
            for a in answers_data
        ]

        return WyrGameSession(
            session_id=session_data["id"],
            user_id=session_data["user_id"],
            game_length=session_data["game_length"],
            category=session_data["category"],
            custom_request=session_data["custom_request"],
            status=GameStatus(session_data["status"]),
            current_question=session_data["current_question"],
            started_at=session_data["started_at"],
            completed_at=session_data["completed_at"],
            questions=questions,
            answers=answers,
            summary=session_data["summary"],
        )

    except Exception as e:
        print(f"❌ WYR_BUILD: Error building session response: {str(e)}", flush=True)
        raise


async def _generate_personality_analysis(
    questions: list[dict],
    answers: list[AnswerObject],
    category: str,
    user_id: uuid.UUID,
    db: Database,
) -> str:
    """Generate personality analysis based on user's answers"""
    try:
        # Get user age context for appropriate language
        age_context = await _get_user_age_context(db, user_id)
        
        # Build analysis prompt
        prompt = _build_analysis_prompt(questions, answers, category, age_context)

        # Make LLM API call
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            return "Analysis temporarily unavailable"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 250,
                    "temperature": 0.7,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )

        if response.status_code == 200:
            result = response.json()
            analysis = result["content"][0]["text"].strip()
            return analysis
        else:
            print(f"❌ WYR_ANALYSIS: API error {response.status_code}", flush=True)
            return "Analysis temporarily unavailable"

    except Exception as e:
        print(f"❌ WYR_ANALYSIS: Error generating analysis: {str(e)}", flush=True)
        return "Analysis temporarily unavailable"


def _build_analysis_prompt(questions: list[dict], answers: list[AnswerObject], category: str, age_context: str) -> str:
    """Build prompt for personality analysis"""
    
    # Create answer mapping
    answer_map = {str(a.question_id): a.chosen_option for a in answers}
    
    # Build questions and answers text
    qa_text = []
    for q in questions:
        question_id = q.get("id")
        chosen = answer_map.get(question_id, "not answered")
        
        if chosen == "a":
            chosen_text = f"CHOSE A: {q.get('option_a', '')}"
        elif chosen == "b":
            chosen_text = f"CHOSE B: {q.get('option_b', '')}"
        else:
            chosen_text = "NOT ANSWERED"
            
        qa_text.append(f"Q{q.get('question_number', '')}: {q.get('option_a', '')} vs {q.get('option_b', '')}\n{chosen_text}")

    qa_string = "\n\n".join(qa_text)

    # Check if this is for a child or family-friendly content
    is_child_friendly = category == "family-friendly" or "children" in age_context.lower()
    
    if is_child_friendly:
        prompt = f"""Look at these fun "Would You Rather" choices and write something nice about this person!

THEIR CHOICES:
{qa_string}

Write a short, happy message (about 100 words, 2-3 sentences) that:
- Says nice things about their choices
- Uses simple words kids can understand  
- Makes them feel good about themselves
- Talks about what kind of person they are

Write like you're talking to a friend. Use words like "awesome", "cool", "amazing". Make it fun and positive!

IMPORTANT: Keep it short and sweet. Use easy words. Make them smile!"""
    else:
        prompt = f"""Analyze this person's personality based on their "Would You Rather" choices in the {category} category.

THEIR CHOICES:
{qa_string}

Create a concise personality analysis (120-150 words, maximum 3 paragraphs) that:
- Identifies key patterns in their choices
- Highlights 2-3 main personality traits
- Feels personal and encouraging

Write like a wise friend. Be specific, not generic. Keep it punchy and fun.

IMPORTANT: Maximum 3 paragraphs. Return ONLY the analysis text, no explanations."""

    return prompt


def _scrub_completed_session(session: WyrGameSession) -> WyrGameSession:
    """
    Scrub completed session to only show chosen option text, not both options.
    This prevents clients from seeing both A and B options in the final response.
    """
    try:
        # Create answer mapping for quick lookup
        answer_map = {str(answer.question_id): answer.chosen_option for answer in session.answers}
        
        # Create new questions list with only chosen option text
        scrubbed_questions = []
        for question in session.questions:
            chosen_option = answer_map.get(str(question.id))
            
            if chosen_option == "a":
                # User chose option A, only show option A text
                scrubbed_question = QuestionObject(
                    id=question.id,
                    question_number=question.question_number,
                    option_a=question.option_a,  # Show chosen text
                    option_b="",  # Hide unchosen option
                    category=question.category,
                )
            elif chosen_option == "b":
                # User chose option B, only show option B text  
                scrubbed_question = QuestionObject(
                    id=question.id,
                    question_number=question.question_number,
                    option_a="",  # Hide unchosen option
                    option_b=question.option_b,  # Show chosen text
                    category=question.category,
                )
            else:
                # No answer recorded, hide both options
                scrubbed_question = QuestionObject(
                    id=question.id,
                    question_number=question.question_number,
                    option_a="",
                    option_b="",
                    category=question.category,
                )
            
            scrubbed_questions.append(scrubbed_question)
        
        # Return new session with scrubbed questions
        return WyrGameSession(
            session_id=session.session_id,
            user_id=session.user_id,
            game_length=session.game_length,
            category=session.category,
            custom_request=session.custom_request,
            status=session.status,
            current_question=session.current_question,
            started_at=session.started_at,
            completed_at=session.completed_at,
            questions=scrubbed_questions,  # Use scrubbed questions
            answers=session.answers,  # Keep original answers
            summary=session.summary,
        )
        
    except Exception as e:
        print(f"⚠️ WYR_SCRUB: Error scrubbing session, returning original: {str(e)}", flush=True)
        return session  # Return original session if scrubbing fails