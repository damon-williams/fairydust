# services/content/wyr_routes.py
import json
import os
import random
import uuid
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Path, Query, Request
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
from shared.json_utils import parse_jsonb_field
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
        return WyrGameErrorResponse(error="Can only create games for yourself")

    try:
        # Extract Authorization header for service-to-service calls
        auth_token = http_request.headers.get("authorization", "")
        if not auth_token:
            return WyrGameErrorResponse(error="Authorization header required")

        # Check rate limiting
        rate_limit_exceeded = await _check_rate_limit(db, request.user_id)
        if rate_limit_exceeded:
            return WyrGameErrorResponse(
                error=f"Rate limit exceeded. Maximum {WYR_RATE_LIMIT} games per hour.",
                error_code="RATE_LIMITED"
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
            return WyrGameErrorResponse(
                error="Failed to generate questions. Please try again.",
                error_code="GENERATION_FAILED"
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
        return WyrGameErrorResponse(
            error="Internal server error during game creation",
            error_code="INTERNAL_ERROR"
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
            return WyrGameErrorResponse(
                error="Session not found or access denied",
                error_code="INVALID_SESSION",
                session_id=session_id
            )

        # Check if session is already completed
        if session_data["status"] == "completed":
            return WyrGameErrorResponse(
                error="Cannot modify completed session",
                error_code="SESSION_COMPLETED",
                session_id=session_id
            )

        # Parse existing data
        existing_questions = parse_jsonb_field(session_data["questions"], default=[])
        existing_answers = parse_jsonb_field(session_data["answers"], default=[])

        # Validate question exists
        question_exists = any(q.get("id") == str(request.question_id) for q in existing_questions)
        if not question_exists:
            return WyrGameErrorResponse(
                error="Invalid question ID",
                error_code="INVALID_QUESTION"
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
            return WyrGameErrorResponse(
                error="Failed to update session",
                error_code="UPDATE_FAILED"
            )

        # Build response
        session = await _build_session_response(updated_session)
        print(f"✅ WYR: Updated progress for session {session_id}", flush=True)

        return WyrGameSessionResponse(session=session)

    except Exception as e:
        print(f"❌ WYR: Error updating progress: {str(e)}", flush=True)
        return WyrGameErrorResponse(
            error="Failed to save progress",
            error_code="INTERNAL_ERROR"
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
            return WyrGameErrorResponse(
                error="Session not found or access denied",
                error_code="INVALID_SESSION",
                session_id=session_id
            )

        # Check if already completed
        if session_data["status"] == "completed":
            session = await _build_session_response(session_data)
            return WyrGameCompleteResponse(
                session=session,
                summary=session_data["summary"] or "Analysis not available"
            )

        # Generate personality analysis
        print("🧠 WYR: Generating personality analysis", flush=True)
        summary = await _generate_personality_analysis(
            questions=parse_jsonb_field(session_data["questions"], default=[]),
            answers=request.final_answers,
            category=session_data["category"],
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
            json.dumps([answer.dict() for answer in request.final_answers]),
            session_id,
            uuid.UUID(current_user.user_id),
        )

        if not completed_session:
            return WyrGameErrorResponse(
                error="Failed to complete session",
                error_code="UPDATE_FAILED"
            )

        session = await _build_session_response(completed_session)
        print(f"✅ WYR: Completed session {session_id}", flush=True)

        return WyrGameCompleteResponse(session=session, summary=summary)

    except Exception as e:
        print(f"❌ WYR: Error completing session: {str(e)}", flush=True)
        return WyrGameErrorResponse(
            error="Failed to complete session",
            error_code="INTERNAL_ERROR"
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
        return WyrGameErrorResponse(
            error="Can only access your own sessions",
            error_code="FORBIDDEN"
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
        return WyrGameErrorResponse(
            error="Failed to retrieve sessions",
            error_code="INTERNAL_ERROR"
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
            return WyrGameErrorResponse(
                error="Session not found or access denied",
                error_code="INVALID_SESSION",
                session_id=session_id
            )

        session = await _build_session_response(session_data)
        return WyrGameSessionResponse(session=session)

    except Exception as e:
        print(f"❌ WYR: Error getting session: {str(e)}", flush=True)
        return WyrGameErrorResponse(
            error="Failed to retrieve session",
            error_code="INTERNAL_ERROR"
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
            return WyrGameErrorResponse(
                error="Session not found or access denied",
                error_code="INVALID_SESSION",
                session_id=session_id
            )

        # Delete session
        delete_query = """
            DELETE FROM wyr_game_sessions
            WHERE id = $1 AND user_id = $2
        """

        result = await db.execute(delete_query, session_id, uuid.UUID(current_user.user_id))

        if "DELETE 0" in result:
            return WyrGameErrorResponse(
                error="Failed to delete session",
                error_code="DELETE_FAILED"
            )

        print(f"✅ WYR: Deleted session {session_id}", flush=True)
        return WyrGameDeleteResponse()

    except Exception as e:
        print(f"❌ WYR: Error deleting session: {str(e)}", flush=True)
        return WyrGameErrorResponse(
            error="Failed to delete session",
            error_code="INTERNAL_ERROR"
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

        # Make LLM API call
        provider = "anthropic"
        model_id = "claude-3-5-sonnet-20241022"
        
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            print("❌ WYR_LLM: Missing ANTHROPIC_API_KEY", flush=True)
            return [], provider, model_id, {}, 0.0, 0

        start_time = datetime.now()
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
                    "max_tokens": 3000,
                    "temperature": 0.8,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )

        latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        if response.status_code == 200:
            result = response.json()
            content = result["content"][0]["text"].strip()

            # Parse questions from response
            questions = _parse_questions_response(content, category)
            
            # Calculate cost
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
        GameCategory.FAMILY_FRIENDLY: "Questions appropriate for all ages that bring families together",
        GameCategory.WORK_CAREER: "Professional scenarios and career-related dilemmas",
        GameCategory.RELATIONSHIPS_LOVE: "Questions about friendship, romance, and human connections",
        GameCategory.FANTASY_SUPERPOWERS: "Magical abilities, fictional scenarios, and superhero choices",
        GameCategory.POP_CULTURE: "Movies, music, celebrities, and entertainment",
        GameCategory.TRAVEL_ADVENTURE: "Exploration, travel destinations, and adventurous experiences",
        GameCategory.MIX_IT_UP: "A random mix from all categories for variety",
    }

    base_prompt = f"""Create exactly {game_length} "Would You Rather" questions for a {age_context} audience.

CATEGORY: {category_descriptions.get(category, category.value)}"""

    if custom_request:
        base_prompt += f"""
CUSTOM THEME: {custom_request}"""

    if category == GameCategory.MIX_IT_UP:
        base_prompt += f"""

VARIETY REQUIREMENT: Since this is "Mix It Up", include questions from different categories:
- {game_length // 3} thought-provoking questions
- {game_length // 3} funny/silly questions  
- Remaining questions from other categories (relationships, fantasy, pop culture, etc.)"""

    base_prompt += f"""

AGE APPROPRIATENESS: Content must be suitable for {age_context}

QUALITY REQUIREMENTS:
- Each question should present two genuinely difficult choices
- Options should be balanced (neither obviously better)
- Questions should spark interesting discussions
- Avoid offensive, inappropriate, or insensitive content
- Make dilemmas meaningful and engaging

FORMAT: Return as a JSON array of objects with this exact structure:
[
  {{
    "question_number": 1,
    "option_a": "First choice description",
    "option_b": "Second choice description",
    "category": "{category.value if category != GameCategory.MIX_IT_UP else 'varies'}"
  }}
]

EXAMPLES of good "Would You Rather" questions:
- "Would you rather have the ability to fly but only 3 feet off the ground, or be invisible but only when no one is looking?"
- "Would you rather always know when someone is lying but never be able to prove it, or never know when someone is lying but always trust people?"

Generate exactly {game_length} creative, engaging questions now:"""

    return base_prompt


def _parse_questions_response(content: str, category: GameCategory) -> list[QuestionObject]:
    """Parse LLM response into QuestionObject list"""
    try:
        # Try to extract JSON from response
        import re
        
        # Look for JSON array in the response
        json_match = re.search(r'\[.*\]', content, re.DOTALL)
        if not json_match:
            print("❌ WYR_PARSE: No JSON array found in response", flush=True)
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

        questions_json = json.dumps([q.dict() for q in questions])

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
        questions_data = parse_jsonb_field(session_data["questions"], default=[])
        answers_data = parse_jsonb_field(session_data["answers"], default=[])

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
) -> str:
    """Generate personality analysis based on user's answers"""
    try:
        # Build analysis prompt
        prompt = _build_analysis_prompt(questions, answers, category)

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
                    "max_tokens": 500,
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


def _build_analysis_prompt(questions: list[dict], answers: list[AnswerObject], category: str) -> str:
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

    prompt = f"""Analyze this person's personality based on their "Would You Rather" choices in the {category} category.

THEIR CHOICES:
{qa_string}

Create a fun, engaging personality analysis (200-300 words) that:
- Identifies patterns in their decision-making
- Highlights interesting personality traits
- Keeps a positive, encouraging tone
- Avoids psychological jargon
- Feels personal and insightful
- Is entertaining to read

Write as if you're a wise friend who knows them well. Be specific about what their choices reveal, not generic.

IMPORTANT: Return ONLY the personality analysis text. No explanations, no meta-commentary, just the analysis itself."""

    return prompt