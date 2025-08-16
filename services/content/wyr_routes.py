# services/content/wyr_routes.py
import hashlib
import json
from uuid import UUID
from shared.uuid_utils import generate_uuid7
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from models import (
    AnswerObject,
    GameCategory,
    GameLength,
    GameStatus,
    QuestionObject,
    WyrGameCompleteResponse,
    WyrGameDeleteResponse,
    WyrGameSession,
    WyrGameSessionComplete,
    WyrGameSessionCreate,
    WyrGameSessionProgress,
    WyrGameSessionResponse,
    WyrGameSessionsResponse,
)

from shared.auth_middleware import TokenData, get_current_user
from shared.database import Database, get_db
from shared.json_utils import safe_json_parse
from shared.llm_client import LLMError, llm_client

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
                detail=f"Rate limit exceeded. Maximum {WYR_RATE_LIMIT} games per hour.",
            )

        # Generate questions using LLM with duplicate prevention
        print("🤖 WYR: Generating questions with duplicate prevention", flush=True)
        questions, generation_metadata = await _generate_questions_llm(
            game_length=request.game_length,
            category=request.category,
            custom_request=request.custom_request,
            user_id=request.user_id,
            db=db,
        )

        if not questions:
            print("❌ WYR: Question generation failed", flush=True)
            raise HTTPException(
                status_code=500, detail="Failed to generate questions. Please try again."
            )

        print(f"✅ WYR: Generated {len(questions)} questions", flush=True)
        print(
            f"✅ WYR: Used {generation_metadata['provider']}/{generation_metadata['model_id']}",
            flush=True,
        )
        print(
            f"✅ WYR: Cost: ${generation_metadata['cost_usd']:.4f}, Time: {generation_metadata['generation_time_ms']}ms",
            flush=True,
        )

        # Note: LLM usage is already logged by the centralized client

        # Save session to database
        session_id = await _save_game_session(
            db=db,
            user_id=request.user_id,
            game_length=request.game_length,
            category=request.category,
            custom_request=request.custom_request,
            questions=questions,
        )

        # Save questions to user's history for duplicate prevention
        await _save_question_history(db, request.user_id, session_id, questions)

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
        raise HTTPException(status_code=500, detail="Internal server error during game creation")


@router.put(
    "/apps/would-you-rather/sessions/{session_id}/progress", response_model=WyrGameSessionResponse
)
async def save_answer_progress(
    session_id: UUID = Path(..., description="Session ID"),
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
            raise HTTPException(status_code=404, detail="Session not found or access denied")

        # Check if session is already completed
        if session_data["status"] == "completed":
            raise HTTPException(status_code=400, detail="Cannot modify completed session")

        # Parse existing data
        existing_questions = safe_json_parse(
            session_data["questions"], default=[], expected_type=list
        )
        existing_answers = safe_json_parse(session_data["answers"], default=[], expected_type=list)

        # Validate question exists
        question_exists = any(q.get("id") == str(request.question_id) for q in existing_questions)
        if not question_exists:
            raise HTTPException(status_code=400, detail="Invalid question ID")

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
            existing_answers.append(
                {
                    "question_id": str(request.question_id),
                    "chosen_option": request.chosen_option,
                    "answered_at": datetime.utcnow().isoformat(),
                }
            )

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
            UUID(current_user.user_id),
        )

        if not updated_session:
            raise HTTPException(status_code=500, detail="Failed to update session")

        # Build response
        session = await _build_session_response(updated_session)
        print(f"✅ WYR: Updated progress for session {session_id}", flush=True)

        return WyrGameSessionResponse(session=session)

    except Exception as e:
        print(f"❌ WYR: Error updating progress: {str(e)}", flush=True)
        raise HTTPException(status_code=500, detail="Failed to save progress")


@router.post(
    "/apps/would-you-rather/sessions/{session_id}/complete", response_model=WyrGameCompleteResponse
)
async def complete_game_session(
    session_id: UUID = Path(..., description="Session ID"),
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
            raise HTTPException(status_code=404, detail="Session not found or access denied")

        # Check if already completed
        if session_data["status"] == "completed":
            session = await _build_session_response(session_data)
            # Scrub completed session to only show chosen options
            scrubbed_session = _scrub_completed_session(session)
            return WyrGameCompleteResponse(
                session=scrubbed_session,
                summary=session_data["summary"] or "Analysis not available",
            )

        # Generate personality analysis
        print("🧠 WYR: Generating personality analysis", flush=True)
        summary, analysis_metadata = await _generate_personality_analysis(
            questions=safe_json_parse(session_data["questions"], default=[], expected_type=list),
            answers=request.final_answers,
            category=session_data["category"],
            user_id=UUID(current_user.user_id),
            db=db,
        )

        print(
            f"✅ WYR: Analysis generated with {analysis_metadata['provider']}/{analysis_metadata['model_id']}",
            flush=True,
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
            json.dumps([answer.model_dump(mode="json") for answer in request.final_answers]),
            session_id,
            UUID(current_user.user_id),
        )

        if not completed_session:
            raise HTTPException(status_code=500, detail="Failed to complete session")

        session = await _build_session_response(completed_session)

        # Scrub questions to only show chosen options
        scrubbed_session = _scrub_completed_session(session)
        print(f"✅ WYR: Completed session {session_id}", flush=True)

        return WyrGameCompleteResponse(session=scrubbed_session, summary=summary)

    except Exception as e:
        print(f"❌ WYR: Error completing session: {str(e)}", flush=True)
        raise HTTPException(status_code=500, detail="Failed to complete session")


@router.get("/users/{user_id}/would-you-rather/sessions", response_model=WyrGameSessionsResponse)
async def get_user_sessions(
    user_id: UUID = Path(..., description="User ID"),
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
        raise HTTPException(status_code=403, detail="Can only access your own sessions")

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
        raise HTTPException(status_code=500, detail="Failed to retrieve sessions")


@router.get("/apps/would-you-rather/sessions/{session_id}", response_model=WyrGameSessionResponse)
async def get_single_session(
    session_id: UUID = Path(..., description="Session ID"),
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get a single game session"""
    print(f"📄 WYR: Getting session {session_id}", flush=True)

    try:
        session_data = await _get_session(db, session_id, current_user.user_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="Session not found or access denied")

        session = await _build_session_response(session_data)

        # Scrub completed sessions to only show chosen options
        if session.status == GameStatus.COMPLETED:
            session = _scrub_completed_session(session)

        return WyrGameSessionResponse(session=session)

    except Exception as e:
        print(f"❌ WYR: Error getting session: {str(e)}", flush=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve session")


@router.delete("/apps/would-you-rather/sessions/{session_id}", response_model=WyrGameDeleteResponse)
async def delete_session(
    session_id: UUID = Path(..., description="Session ID"),
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Delete a game session"""
    print(f"🗑️ WYR: Deleting session {session_id}", flush=True)

    try:
        # Verify session exists and belongs to user
        session_data = await _get_session(db, session_id, current_user.user_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="Session not found or access denied")

        # Delete session
        delete_query = """
            DELETE FROM wyr_game_sessions
            WHERE id = $1 AND user_id = $2
        """

        result = await db.execute(delete_query, session_id, UUID(current_user.user_id))

        if "DELETE 0" in result:
            raise HTTPException(status_code=500, detail="Failed to delete session")

        print(f"✅ WYR: Deleted session {session_id}", flush=True)
        return WyrGameDeleteResponse()

    except Exception as e:
        print(f"❌ WYR: Error deleting session: {str(e)}", flush=True)
        raise HTTPException(status_code=500, detail="Failed to delete session")


# Helper functions


def _normalize_question_for_duplicate_check(option_a: str, option_b: str) -> str:
    """Normalize question content for duplicate detection"""
    # Remove extra whitespace and convert to lowercase
    a_clean = option_a.lower().strip()
    b_clean = option_b.lower().strip()

    # Sort options alphabetically to handle reversed questions
    # e.g., "cats vs dogs" and "dogs vs cats" should be the same
    options = sorted([a_clean, b_clean])
    return f"{options[0]} vs {options[1]}"


def _hash_question(option_a: str, option_b: str) -> str:
    """Create hash for duplicate detection"""
    normalized = _normalize_question_for_duplicate_check(option_a, option_b)
    return hashlib.md5(normalized.encode()).hexdigest()


async def _get_user_question_hashes(db: Database, user_id: UUID, limit: int = 200) -> set[str]:
    """Get user's recent question hashes to avoid duplicates"""
    try:
        query = """
            SELECT question_hash
            FROM user_question_history
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2
        """

        rows = await db.fetch_all(query, user_id, limit)
        return {row["question_hash"] for row in rows}

    except Exception as e:
        print(f"⚠️ WYR_HISTORY: Error getting question history: {str(e)}", flush=True)
        # Return empty set if table doesn't exist yet or other error
        return set()


async def _save_question_history(
    db: Database, user_id: UUID, session_id: UUID, questions: list[QuestionObject]
) -> None:
    """Save questions to user's history for duplicate prevention"""
    try:
        # Insert all questions into history
        for question in questions:
            question_hash = _hash_question(question.option_a, question.option_b)
            question_content = {
                "question_number": question.question_number,
                "option_a": question.option_a,
                "option_b": question.option_b,
                "category": question.category,
            }

            await db.execute(
                """
                INSERT INTO user_question_history
                (user_id, question_hash, question_content, game_session_id)
                VALUES ($1, $2, $3::jsonb, $4)
                ON CONFLICT DO NOTHING
                """,
                user_id,
                question_hash,
                json.dumps(question_content),
                session_id,
            )

        print(f"✅ WYR_HISTORY: Saved {len(questions)} questions to history", flush=True)

    except Exception as e:
        print(f"⚠️ WYR_HISTORY: Error saving question history: {str(e)}", flush=True)
        # Don't fail the game creation if history saving fails


def _filter_duplicate_questions(
    questions: list[QuestionObject], existing_hashes: set[str]
) -> list[QuestionObject]:
    """Filter out questions that user has seen before"""
    filtered_questions = []
    duplicates_found = 0

    for question in questions:
        question_hash = _hash_question(question.option_a, question.option_b)

        if question_hash not in existing_hashes:
            filtered_questions.append(question)
        else:
            duplicates_found += 1
            print(
                f"🔄 WYR_DUPLICATE: Filtered duplicate question: {question.option_a} vs {question.option_b}",
                flush=True,
            )

    if duplicates_found > 0:
        print(f"🔄 WYR_DUPLICATE: Filtered {duplicates_found} duplicate questions", flush=True)

    return filtered_questions


async def _check_rate_limit(db: Database, user_id: UUID) -> bool:
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


async def _get_user_age_context(db: Database, user_id: UUID) -> str:
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
            "primary_parameters": {"temperature": 1.0, "max_tokens": 1000, "top_p": 0.95},
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

            # Parse cached parameters if they're a string
            cached_parameters = cached_config.get("primary_parameters", {"temperature": 1.0, "max_tokens": 1000, "top_p": 0.95})
            if isinstance(cached_parameters, str):
                import json
                try:
                    cached_parameters = json.loads(cached_parameters)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse cached parameters JSON: {cached_parameters}")
                    cached_parameters = {"temperature": 1.0, "max_tokens": 1000, "top_p": 0.95}
            
            config = {
                "primary_provider": cached_config.get("primary_provider", "anthropic"),
                "primary_model_id": cached_config.get(
                    "primary_model_id", "claude-3-5-sonnet-20241022"
                ),
                "primary_parameters": cached_parameters,
            }

            print(f"✅ WYR_CONFIG: Returning cached config: {config}", flush=True)
            return config

    # Cache miss - check database directly
    print("⚠️ WYR_CONFIG: Cache miss, checking database directly", flush=True)

    try:
        db_config = await db.fetch_one(
            "SELECT provider, model_id, parameters FROM app_model_configs WHERE app_id = $1 AND model_type = 'text'", 
            app_id
        )

        if db_config:
            print("📊 WYR_CONFIG: Found database config", flush=True)
            print(f"📊 WYR_CONFIG: DB Provider: {db_config['provider']}", flush=True)
            print(f"📊 WYR_CONFIG: DB Model: {db_config['model_id']}", flush=True)

            # Parse and cache the database config
            # Parse parameters if it's a string (JSONB field might return as string)
            parameters = db_config.get("parameters", {})
            if isinstance(parameters, str):
                import json
                try:
                    parameters = json.loads(parameters)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse parameters JSON: {parameters}")
                    parameters = {"temperature": 1.0, "max_tokens": 1000, "top_p": 0.95}
            elif parameters is None:
                parameters = {"temperature": 1.0, "max_tokens": 1000, "top_p": 0.95}
            
            parsed_config = {
                "primary_provider": db_config["provider"],
                "primary_model_id": db_config["model_id"],
                "primary_parameters": parameters,
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
        "primary_parameters": {"temperature": 1.0, "max_tokens": 1000, "top_p": 0.95},
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
    user_id: UUID,
    db: Database,
) -> tuple[list[QuestionObject], dict]:
    """Generate questions using centralized LLM client with duplicate prevention"""
    try:
        # Get user's question history for duplicate detection
        print("🔍 WYR_DUPLICATE: Fetching user question history", flush=True)
        existing_hashes = await _get_user_question_hashes(db, user_id)
        print(f"🔍 WYR_DUPLICATE: User has {len(existing_hashes)} previous questions", flush=True)

        # Get user age context
        age_context = await _get_user_age_context(db, user_id)

        # Build prompt with anti-duplicate instructions if user has history
        prompt = _build_questions_prompt(
            game_length, category, custom_request, age_context, len(existing_hashes)
        )

        # Get LLM model configuration from database/cache
        model_config = await _get_wyr_llm_model_config()

        # Ensure sufficient tokens for question generation (max 10 questions)
        parameters = model_config.get("primary_parameters", {})
        parameters["max_tokens"] = max(parameters.get("max_tokens", 1000), 1500)

        # Update config with adjusted parameters
        app_config = {**model_config, "primary_parameters": parameters}

        print(
            f"🔧 WYR_LLM: Using {app_config['primary_provider']}/{app_config['primary_model_id']}",
            flush=True,
        )
        print(f"🔧 WYR_LLM: Parameters: {parameters}", flush=True)

        # Create request metadata for logging
        request_metadata = {
            "parameters": {
                "game_length": game_length.value,
                "category": category.value,
                "has_custom_request": bool(custom_request),
                "age_context": age_context,
            }
        }

        # Use centralized LLM client
        completion, generation_metadata = await llm_client.generate_completion(
            prompt=prompt,
            app_config=app_config,
            user_id=user_id,
            app_id="fairydust-would-you-rather",
            action=f"would-you-rather-{game_length.value}",
            request_metadata=request_metadata,
        )

        # Parse questions from response
        questions = _parse_questions_response(completion, category)

        print(
            f"📝 WYR_LLM: Initially generated {len(questions)} questions",
            flush=True,
        )

        # Filter out duplicates
        if existing_hashes:
            questions = _filter_duplicate_questions(questions, existing_hashes)
            print(
                f"🔄 WYR_DUPLICATE: After filtering: {len(questions)} unique questions",
                flush=True,
            )

        # If we lost too many questions to duplicates, try to generate more
        if len(questions) < game_length.value and len(existing_hashes) > 0:
            shortage = game_length.value - len(questions)
            print(f"⚠️ WYR_DUPLICATE: Need {shortage} more questions due to duplicates", flush=True)

            # Generate additional questions with stronger anti-duplicate prompt
            try:
                extra_prompt = _build_questions_prompt(
                    GameLength(shortage),
                    category,
                    custom_request,
                    age_context,
                    len(existing_hashes),
                    extra_creative=True,
                )

                extra_completion, _ = await llm_client.generate_completion(
                    prompt=extra_prompt,
                    app_config=app_config,
                    user_id=user_id,
                    app_id="fairydust-would-you-rather",
                    action=f"would-you-rather-{game_length.value}-extra",
                    request_metadata=request_metadata,
                )

                extra_questions = _parse_questions_response(extra_completion, category)
                extra_questions = _filter_duplicate_questions(extra_questions, existing_hashes)

                # Add the extras to our main list
                questions.extend(extra_questions[:shortage])
                print(
                    f"✅ WYR_DUPLICATE: Added {len(extra_questions[:shortage])} extra questions",
                    flush=True,
                )

            except Exception as e:
                print(f"⚠️ WYR_DUPLICATE: Failed to generate extra questions: {str(e)}", flush=True)

        print(
            f"✅ WYR_LLM: Final result: {len(questions)} questions (expected {game_length.value})",
            flush=True,
        )

        # Check if we got enough complete questions
        if len(questions) < game_length.value:
            print(
                f"⚠️ WYR_LLM: Insufficient questions - got {len(questions)}, expected {game_length.value}",
                flush=True,
            )

        return questions, generation_metadata

    except LLMError as e:
        print(f"❌ WYR_LLM: LLM error generating questions: {str(e)}", flush=True)
        return [], {
            "provider": "unknown",
            "model_id": "unknown",
            "cost_usd": 0.0,
            "generation_time_ms": 0,
            "was_fallback": False,
            "attempt_number": 1,
        }
    except Exception as e:
        print(f"❌ WYR_LLM: Unexpected error generating questions: {str(e)}", flush=True)
        return [], {
            "provider": "unknown",
            "model_id": "unknown",
            "cost_usd": 0.0,
            "generation_time_ms": 0,
            "was_fallback": False,
            "attempt_number": 1,
        }


def _build_questions_prompt(
    game_length: GameLength,
    category: GameCategory,
    custom_request: Optional[str],
    age_context: str,
    previous_question_count: int = 0,
    extra_creative: bool = False,
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

    # Add anti-duplicate instructions for experienced users
    if previous_question_count > 0:
        creativity_level = "MAXIMUM" if extra_creative else "HIGH"
        base_prompt += f"""

UNIQUENESS REQUIREMENT: This user has played {previous_question_count} previous questions.
Use {creativity_level} creativity to ensure all questions are completely different from typical "would you rather" questions.

AVOID COMMON QUESTIONS: Stay away from obvious classics like:
- Flying vs invisibility
- Past vs future travel
- Mind reading vs telepathy
- Unlimited money vs unlimited time
- Famous vs rich
- Always hot vs always cold

CREATIVITY STRATEGIES:
- Combine unexpected concepts and scenarios
- Create abstract or philosophical dilemmas
- Use specific situational contexts
- Mix emotions, senses, and unusual abilities
- Think of scenarios that make people pause and really think

{"EXTRA CREATIVE MODE: Push beyond normal boundaries with highly unusual, thought-provoking scenarios that most people have never considered." if extra_creative else ""}"""

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

CRITICAL: Each option_a and option_b should be a SINGLE choice only. Do NOT include both choices in one option or use "or" in the options.

FORMAT: Return ONLY a valid JSON array of objects with this exact structure (no other text):
[
  {{
    "question_number": 1,
    "option_a": "First choice description",
    "option_b": "Second choice description",
    "category": "{category.value if category != GameCategory.MIX_IT_UP else 'varies'}"
  }}
]

EXAMPLES showing how to split options correctly:"""

    # Add age-appropriate examples with proper option splitting
    if category == GameCategory.FAMILY_FRIENDLY or "children" in age_context.lower():
        base_prompt += """
- Question: "Would you rather have a pet dragon or a pet unicorn?"
  option_a: "Have a pet dragon"
  option_b: "Have a pet unicorn"

- Question: "Would you rather eat ice cream for breakfast or cookies for dinner?"
  option_a: "Eat ice cream for breakfast"
  option_b: "Eat cookies for dinner"

- Question: "Would you rather be able to talk to animals or make toys come to life?"
  option_a: "Be able to talk to animals"
  option_b: "Make toys come to life"
"""
    else:
        base_prompt += """
- Question: "Would you rather have the ability to fly but only 3 feet off the ground, or be invisible but only when no one is looking?"
  option_a: "Have the ability to fly but only 3 feet off the ground"
  option_b: "Be invisible but only when no one is looking"

- Question: "Would you rather always know when someone is lying but never be able to prove it, or never know when someone is lying but always trust people?"
  option_a: "Always know when someone is lying but never be able to prove it"
  option_b: "Never know when someone is lying but always trust people"
"""

    base_prompt += f"""

CORRECT JSON FORMAT EXAMPLE:
[
  {{
    "question_number": 1,
    "option_a": "Live in a treehouse",
    "option_b": "Live in a castle made of candy",
    "category": "{category.value if category != GameCategory.MIX_IT_UP else 'varies'}"
  }}
]

Generate exactly {game_length.value} creative, engaging questions now.

IMPORTANT:
- Return ONLY the JSON array, no explanations, no additional text
- Each option should be a single choice, not a full question
- Do NOT include "or" or both options in a single field"""

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
        json_match = re.search(r"\[.*\]", content, re.DOTALL)

        # Pattern 2: JSON in markdown code blocks
        if not json_match:
            json_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", content, re.DOTALL)
            if json_match:
                json_match = type("Match", (), {"group": lambda: json_match.group(1)})()

        # Pattern 3: JSON after some introductory text
        if not json_match:
            json_match = re.search(
                r"(?:here|questions|array).*?(\[.*\])", content, re.DOTALL | re.IGNORECASE
            )
            if json_match:
                json_match = type("Match", (), {"group": lambda: json_match.group(1)})()

        if not json_match:
            print("❌ WYR_PARSE: No JSON array found in response", flush=True)
            print(f"🔍 WYR_PARSE: Full response was: {content}", flush=True)
            return []

        questions_data = json.loads(json_match.group())
        questions = []

        for i, q_data in enumerate(questions_data):
            # Check for incomplete questions (empty or very short options)
            option_a = q_data.get("option_a", "").strip()
            option_b = q_data.get("option_b", "").strip()

            if not option_a or not option_b or len(option_a) < 10 or len(option_b) < 10:
                print(
                    f"⚠️ WYR_PARSE: Incomplete question {i+1}: A='{option_a}', B='{option_b}'",
                    flush=True,
                )
                continue  # Skip incomplete questions

            question = QuestionObject(
                id=generate_uuid7(),
                question_number=q_data.get("question_number", i + 1),
                option_a=option_a,
                option_b=option_b,
                category=q_data.get("category", category.value),
            )
            questions.append(question)

        print(f"✅ WYR_PARSE: Successfully parsed {len(questions)} complete questions", flush=True)
        return questions

    except Exception as e:
        print(f"❌ WYR_PARSE: Error parsing questions: {str(e)}", flush=True)
        return []


async def _save_game_session(
    db: Database,
    user_id: UUID,
    game_length: GameLength,
    category: GameCategory,
    custom_request: Optional[str],
    questions: list[QuestionObject],
) -> UUID:
    """Save new game session to database"""
    try:
        session_id = generate_uuid7()

        insert_query = """
            INSERT INTO wyr_game_sessions (
                id, user_id, game_length, category, custom_request, status,
                current_question, questions, answers, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, 'in_progress', 1, $6::jsonb, '[]'::jsonb,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """

        # Convert questions to JSON, ensuring UUIDs are properly serialized
        questions_json = json.dumps([q.model_dump(mode="json") for q in questions])

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


async def _get_session(db: Database, session_id: UUID, user_id: str) -> Optional[dict]:
    """Get session by ID and verify ownership"""
    try:
        query = """
            SELECT id, user_id, game_length, category, custom_request, status,
                   current_question, started_at, completed_at, summary, questions, answers
            FROM wyr_game_sessions
            WHERE id = $1 AND user_id = $2
        """

        result = await db.fetch_one(query, session_id, UUID(user_id))
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
                id=UUID(q["id"]),
                question_number=q["question_number"],
                option_a=q["option_a"],
                option_b=q["option_b"],
                category=q["category"],
            )
            for q in questions_data
        ]

        answers = [
            AnswerObject(
                question_id=UUID(a["question_id"]),
                chosen_option=a.get("chosen_option"),
                answered_at=datetime.fromisoformat(a["answered_at"])
                if a.get("answered_at")
                else None,
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
    user_id: UUID,
    db: Database,
) -> tuple[str, dict]:
    """Generate personality analysis using centralized LLM client"""
    try:
        # Get user age context for appropriate language
        age_context = await _get_user_age_context(db, user_id)

        # Build analysis prompt
        prompt = _build_analysis_prompt(questions, answers, category, age_context)

        # Use simpler config for analysis - fixed model with appropriate parameters
        app_config = {
            "primary_provider": "anthropic",
            "primary_model_id": "claude-3-5-sonnet-20241022",
            "primary_parameters": {
                "max_tokens": 100,  # Much shorter for whimsical summaries
                "temperature": 0.8,  # Higher creativity for whimsical tone
                "top_p": 0.9,
            },
        }

        # Create request metadata for logging
        request_metadata = {
            "parameters": {
                "category": category,
                "age_context": age_context,
                "num_questions": len(questions),
                "num_answers": len(answers),
            }
        }

        # Use centralized LLM client
        analysis, generation_metadata = await llm_client.generate_completion(
            prompt=prompt,
            app_config=app_config,
            user_id=user_id,
            app_id="fairydust-would-you-rather",
            action="would-you-rather-analysis",
            request_metadata=request_metadata,
        )

        return analysis, generation_metadata

    except LLMError as e:
        print(f"❌ WYR_ANALYSIS: LLM error generating analysis: {str(e)}", flush=True)
        return "Analysis temporarily unavailable", {
            "provider": "unknown",
            "model_id": "unknown",
            "cost_usd": 0.0,
            "generation_time_ms": 0,
            "was_fallback": False,
            "attempt_number": 1,
        }
    except Exception as e:
        print(f"❌ WYR_ANALYSIS: Unexpected error generating analysis: {str(e)}", flush=True)
        return "Analysis temporarily unavailable", {
            "provider": "unknown",
            "model_id": "unknown",
            "cost_usd": 0.0,
            "generation_time_ms": 0,
            "was_fallback": False,
            "attempt_number": 1,
        }


def _build_analysis_prompt(
    questions: list[dict], answers: list[AnswerObject], category: str, age_context: str
) -> str:
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

        qa_text.append(
            f"Q{q.get('question_number', '')}: {q.get('option_a', '')} vs {q.get('option_b', '')}\n{chosen_text}"
        )

    qa_string = "\n\n".join(qa_text)

    # Check if this is for a child or family-friendly content
    is_child_friendly = category == "family-friendly" or "children" in age_context.lower()

    if is_child_friendly:
        prompt = f"""Look at these fun "Would You Rather" choices and write something nice about this person!

THEIR CHOICES:
{qa_string}

Write a super short, happy message (about 30-40 words, just 1-2 sentences) that:
- Says something awesome about their choices
- Uses simple words kids understand
- Makes them smile

Be like their best friend! Use fun words like "awesome", "cool", "amazing"!

IMPORTANT: Keep it REALLY short and sweet - just 1-2 sentences!"""
    else:
        prompt = f"""Create a fun, whimsical personality summary based on these "Would You Rather" choices from the {category} category.

THEIR CHOICES:
{qa_string}

Write a playful, lighthearted personality snapshot (40-60 words max, 2-3 sentences) that:
- Captures their vibe with a fun twist
- Uses creative, whimsical language
- Feels like a magical personality spell

Write like a quirky fairy godmother giving them their personality reading. Be specific, playful, and delightfully weird.

IMPORTANT: Maximum 60 words. Make it whimsical and fun, not serious. Return ONLY the personality reading."""

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
                    option_b="[Hidden]",  # Hide unchosen option with placeholder
                    category=question.category,
                )
            elif chosen_option == "b":
                # User chose option B, only show option B text
                scrubbed_question = QuestionObject(
                    id=question.id,
                    question_number=question.question_number,
                    option_a="[Hidden]",  # Hide unchosen option with placeholder
                    option_b=question.option_b,  # Show chosen text
                    category=question.category,
                )
            else:
                # No answer recorded, hide both options
                scrubbed_question = QuestionObject(
                    id=question.id,
                    question_number=question.question_number,
                    option_a="[Not answered]",
                    option_b="[Not answered]",
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
