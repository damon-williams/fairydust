# services/content/twenty_questions_routes.py
import logging
import random
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from shared.database import Database, get_db
from shared.llm_client import llm_client
from shared.rate_limiting import rate_limit_decorator

from .models import (
    TwentyQuestionsAnswer,
    TwentyQuestionsAnswerRequest,
    TwentyQuestionsAnswerResponse,
    TwentyQuestionsErrorResponse,
    TwentyQuestionsGameState,
    TwentyQuestionsGuessRequest,
    TwentyQuestionsGuessResponse,
    TwentyQuestionsHistoryEntry,
    TwentyQuestionsQuestionRequest,
    TwentyQuestionsQuestionResponse,
    TwentyQuestionsStartRequest,
    TwentyQuestionsStartResponse,
    TwentyQuestionsStatus,
    TwentyQuestionsStatusResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)


async def get_user_people(db: Database, user_id: UUID) -> list[dict]:
    """Get all people (and pets) associated with a user."""
    people = await db.fetch_all(
        """
        SELECT id, name, relationship, birth_date, entry_type, species, personality_description
        FROM people_in_my_life
        WHERE user_id = $1 AND name IS NOT NULL AND name != ''
        ORDER BY name
        """,
        user_id,
    )
    return people


async def select_target_person(people: list[dict]) -> dict:
    """Select a random person from the user's people list."""
    if not people:
        # Fallback to generic person if no people in database
        return {
            "id": None,
            "name": "Someone you know",
            "relationship": "unknown",
            "entry_type": "person",
        }

    return random.choice(people)


async def get_llm_model_config() -> dict:
    """Get LLM configuration for 20 Questions app using normalized structure"""
    from shared.app_config_cache import get_app_config_cache
    from shared.json_utils import parse_jsonb_field

    app_slug = "fairydust-20-questions"

    # First, get the app UUID from the slug
    from shared.database import get_db

    db = await get_db()
    app_result = await db.fetch_one("SELECT id FROM apps WHERE slug = $1", app_slug)

    if not app_result:
        logger.warning(f"App with slug '{app_slug}' not found in database")
        # Return default config if app not found
        return {
            "primary_provider": "anthropic",
            "primary_model_id": "claude-3-5-haiku-20241022",
            "primary_parameters": {"temperature": 0.8, "max_tokens": 150, "top_p": 0.9},
        }

    app_id = str(app_result["id"])

    try:
        # Try to get from cache first
        cache = await get_app_config_cache()
        cached_config = await cache.get_model_config(app_id)

        if cached_config:
            return cached_config

        # Fetch from database - normalized structure
        config_result = await db.fetch_one(
            """
            SELECT provider, model_id, parameters, is_enabled
            FROM app_model_configs
            WHERE app_id = $1 AND model_type = 'text' AND is_enabled = true
            """,
            app_result["id"],
        )

        if config_result:
            parameters = parse_jsonb_field(
                config_result, "parameters", expected_type=dict, default={}
            )

            model_config = {
                "primary_provider": config_result["provider"],
                "primary_model_id": config_result["model_id"],
                "primary_parameters": parameters,
            }
        else:
            # Use default configuration
            model_config = {
                "primary_provider": "anthropic",
                "primary_model_id": "claude-3-5-haiku-20241022",
                "primary_parameters": {"temperature": 0.8, "max_tokens": 150, "top_p": 0.9},
            }

        # Cache the result
        await cache.set_model_config(app_id, model_config)
        return model_config

    except Exception as e:
        logger.error(f"Error fetching LLM config for {app_slug}: {e}")
        # Return default on error
        return {
            "primary_provider": "anthropic",
            "primary_model_id": "claude-3-5-haiku-20241022",
            "primary_parameters": {"temperature": 0.8, "max_tokens": 150, "top_p": 0.9},
        }


async def generate_ai_question(
    db: Database,
    game_id: UUID,
    user_id: UUID,
    target_person: dict,
    history: list[dict],
    question_number: int,
) -> str:
    """Generate an AI question using LLM with game context."""

    # Build context from game history
    history_context = ""
    if history:
        history_items = []
        for entry in history:
            if not entry.get("is_guess", False):
                history_items.append(
                    f"Q{entry['question_number']}: {entry['question_text']} - {entry['answer']}"
                )
        if history_items:
            history_context = "\n\nPrevious questions and answers:\n" + "\n".join(
                history_items[-5:]
            )  # Last 5 questions

    # Get user's people for context
    people = await get_user_people(db, user_id)
    people_names = [p["name"] for p in people if p.get("name")]
    people_context = (
        f"The user knows these people: {', '.join(people_names[:10])}"
        if people_names
        else "No people information available."
    )

    # Generate question prompt
    prompt = f"""You are playing 20 Questions. The user is thinking of someone in their life, and you need to ask a yes/no question to narrow down who it might be.

{people_context}

Target person info (DO NOT reveal this):
- Name: {target_person.get('name', 'Unknown')}
- Relationship: {target_person.get('relationship', 'Unknown')}
- Type: {target_person.get('entry_type', 'person')}
{f"- Species: {target_person.get('species')}" if target_person.get('species') else ""}

This is question #{question_number} out of 20.{history_context}

Ask a strategic yes/no question to help identify who the person is thinking of. Make it conversational and engaging. Focus on:
- Relationship to the user (family, friend, etc.)
- Age group or generation
- Gender
- How they know this person
- Whether it's a person or pet
- Physical characteristics
- Personality traits
- Shared activities or memories

Keep the question under 100 characters and make it natural.

Question:"""

    try:
        # Get LLM model configuration
        model_config = await get_llm_model_config()

        # Get app ID
        app_id = await get_app_id(db)

        # Use centralized LLM client
        completion, metadata = await llm_client.generate_completion(
            prompt=prompt,
            app_config=model_config,
            user_id=user_id,
            app_id=str(app_id),
            action="twenty_questions_generation",
            request_metadata={
                "game_id": str(game_id),
                "question_number": question_number,
                "target_person_name": target_person.get("name", "Unknown"),
            },
        )

        question = completion.strip()
        if question.endswith("?"):
            return question
        else:
            return question + "?"

    except Exception as e:
        logger.error(f"Failed to generate AI question: {e}")
        # Fallback questions based on question number
        fallback_questions = [
            "Is this person a family member?",
            "Is this person older than you?",
            "Do you see this person regularly?",
            "Is this person male?",
            "Do you work with this person?",
            "Is this person married?",
            "Does this person have children?",
            "Do you share hobbies with this person?",
            "Is this person from your hometown?",
            "Is this person taller than average?",
        ]
        return fallback_questions[min(question_number - 1, len(fallback_questions) - 1)]


async def determine_ai_answer(target_person: dict, question: str) -> TwentyQuestionsAnswer:
    """Determine how the AI should answer based on the target person and question."""

    # This is a simplified heuristic-based approach
    # In a more sophisticated implementation, this could use LLM to analyze the question

    question_lower = question.lower()
    person_data = {
        "name": target_person.get("name", "").lower(),
        "relationship": target_person.get("relationship", "").lower(),
        "entry_type": target_person.get("entry_type", "person").lower(),
        "species": target_person.get("species", "").lower(),
    }

    # Family relationship patterns
    if "family" in question_lower or "relative" in question_lower:
        family_terms = [
            "parent",
            "mother",
            "father",
            "mom",
            "dad",
            "sister",
            "brother",
            "sibling",
            "aunt",
            "uncle",
            "cousin",
            "grandparent",
            "grandmother",
            "grandfather",
            "child",
            "son",
            "daughter",
        ]
        if any(term in person_data["relationship"] for term in family_terms):
            return TwentyQuestionsAnswer.YES
        else:
            return TwentyQuestionsAnswer.NO

    # Pet vs person
    if "pet" in question_lower or "animal" in question_lower:
        if person_data["entry_type"] == "pet":
            return TwentyQuestionsAnswer.YES
        else:
            return TwentyQuestionsAnswer.NO

    if "person" in question_lower and "pet" not in question_lower:
        if person_data["entry_type"] == "person":
            return TwentyQuestionsAnswer.YES
        else:
            return TwentyQuestionsAnswer.NO

    # Default to unknown for complex questions that need more context
    return TwentyQuestionsAnswer.UNKNOWN


async def get_app_id(db: Database) -> UUID:
    """Get the 20 Questions app ID."""
    app = await db.fetch_one("SELECT id FROM apps WHERE slug = 'fairydust-20-questions'")
    if not app:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="20 Questions app not configured",
        )
    return app["id"]


@router.post("/start", response_model=TwentyQuestionsStartResponse)
@rate_limit_decorator(max_requests=10, window_seconds=3600)  # 10 games per hour
async def start_game(
    request: TwentyQuestionsStartRequest,
    db: Database = Depends(get_db),
):
    """Start a new 20 Questions game."""
    try:
        # Check if user has an active game
        existing_game = await db.fetch_one(
            """
            SELECT id FROM twenty_questions_games
            WHERE user_id = $1 AND status = 'active'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            request.user_id,
        )

        if existing_game:
            return TwentyQuestionsErrorResponse(
                error="You already have an active game. Complete it first or check your game status.",
                error_code="GAME_ALREADY_ACTIVE",
                game_id=existing_game["id"],
            )

        # Get user's people
        people = await get_user_people(db, request.user_id)
        if not people:
            return TwentyQuestionsErrorResponse(
                error="You need to add some people to your profile first to play this game.",
                error_code="NO_PEOPLE_FOUND",
            )

        # Select target person
        target_person = await select_target_person(people)

        # Create new game
        game_id = uuid4()
        await db.execute(
            """
            INSERT INTO twenty_questions_games (
                id, user_id, category, target_person_id, target_person_name,
                status, questions_asked, questions_remaining
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            game_id,
            request.user_id,
            request.category.value,
            target_person.get("id"),
            target_person["name"],
            TwentyQuestionsStatus.ACTIVE.value,
            0,
            20,
        )

        # Fetch created game
        game_data = await db.fetch_one(
            """
            SELECT id, user_id, category, target_person_id, target_person_name,
                   status, questions_asked, questions_remaining, final_guess,
                   answer_revealed, is_correct, created_at, updated_at
            FROM twenty_questions_games
            WHERE id = $1
            """,
            game_id,
        )

        game = TwentyQuestionsGameState(**game_data)

        return TwentyQuestionsStartResponse(
            game=game,
            message="Game started! I'm thinking of someone in your life. Ask yes/no questions to figure out who it is!",
        )

    except Exception as e:
        logger.error(f"Error starting 20 Questions game: {e}")
        return TwentyQuestionsErrorResponse(
            error="Failed to start game. Please try again.",
            error_code="GAME_START_ERROR",
        )


@router.post("/{game_id}/question", response_model=TwentyQuestionsQuestionResponse)
async def ask_question(
    game_id: UUID,
    request: TwentyQuestionsQuestionRequest,
    db: Database = Depends(get_db),
):
    """User asks a question to the AI."""
    try:
        # Get game
        game_data = await db.fetch_one(
            """
            SELECT id, user_id, category, target_person_id, target_person_name,
                   status, questions_asked, questions_remaining, final_guess,
                   answer_revealed, is_correct, created_at, updated_at
            FROM twenty_questions_games
            WHERE id = $1 AND user_id = $2
            """,
            game_id,
            request.user_id,
        )

        if not game_data:
            return TwentyQuestionsErrorResponse(
                error="Game not found",
                error_code="GAME_NOT_FOUND",
                game_id=game_id,
            )

        if game_data["status"] != TwentyQuestionsStatus.ACTIVE.value:
            return TwentyQuestionsErrorResponse(
                error="Game is not active",
                error_code="GAME_NOT_ACTIVE",
                game_id=game_id,
            )

        if game_data["questions_remaining"] <= 0:
            return TwentyQuestionsErrorResponse(
                error="No questions remaining",
                error_code="NO_QUESTIONS_REMAINING",
                game_id=game_id,
            )

        # Get target person info
        target_person = {"name": game_data["target_person_name"]}
        if game_data["target_person_id"]:
            person_data = await db.fetch_one(
                """
                SELECT name, relationship, entry_type, species, personality_description
                FROM people_in_my_life
                WHERE id = $1
                """,
                game_data["target_person_id"],
            )
            if person_data:
                target_person.update(person_data)

        # Determine AI's answer
        ai_answer = await determine_ai_answer(target_person, request.question)

        # Update game state
        new_questions_asked = game_data["questions_asked"] + 1
        new_questions_remaining = game_data["questions_remaining"] - 1

        await db.execute(
            """
            UPDATE twenty_questions_games
            SET questions_asked = $1, questions_remaining = $2, updated_at = CURRENT_TIMESTAMP
            WHERE id = $3
            """,
            new_questions_asked,
            new_questions_remaining,
            game_id,
        )

        # Add to history
        await db.execute(
            """
            INSERT INTO twenty_questions_history (
                game_id, question_number, question_text, answer, is_guess
            ) VALUES ($1, $2, $3, $4, $5)
            """,
            game_id,
            new_questions_asked,
            request.question,
            ai_answer.value,
            False,
        )

        # Get updated game
        updated_game_data = await db.fetch_one(
            """
            SELECT id, user_id, category, target_person_id, target_person_name,
                   status, questions_asked, questions_remaining, final_guess,
                   answer_revealed, is_correct, created_at, updated_at
            FROM twenty_questions_games
            WHERE id = $1
            """,
            game_id,
        )

        game = TwentyQuestionsGameState(**updated_game_data)

        # Generate AI's next question if game continues
        ai_question = None
        if new_questions_remaining > 0:
            # Get history for context
            history = await db.fetch_all(
                """
                SELECT question_number, question_text, answer, is_guess, created_at
                FROM twenty_questions_history
                WHERE game_id = $1
                ORDER BY question_number
                """,
                game_id,
            )

            ai_question = await generate_ai_question(
                db, game_id, request.user_id, target_person, history, new_questions_asked + 1
            )

        return TwentyQuestionsQuestionResponse(
            game=game,
            ai_question=ai_question or f"I answered '{ai_answer.value}' to your question.",
            question_number=new_questions_asked + 1,
        )

    except Exception as e:
        logger.error(f"Error processing question in game {game_id}: {e}")
        return TwentyQuestionsErrorResponse(
            error="Failed to process question. Please try again.",
            error_code="QUESTION_ERROR",
            game_id=game_id,
        )


@router.post("/{game_id}/answer", response_model=TwentyQuestionsAnswerResponse)
async def answer_ai_question(
    game_id: UUID,
    request: TwentyQuestionsAnswerRequest,
    db: Database = Depends(get_db),
):
    """User answers the AI's question."""
    try:
        # Get game
        game_data = await db.fetch_one(
            """
            SELECT id, user_id, category, target_person_id, target_person_name,
                   status, questions_asked, questions_remaining, final_guess,
                   answer_revealed, is_correct, created_at, updated_at
            FROM twenty_questions_games
            WHERE id = $1 AND user_id = $2
            """,
            game_id,
            request.user_id,
        )

        if not game_data:
            return TwentyQuestionsErrorResponse(
                error="Game not found",
                error_code="GAME_NOT_FOUND",
                game_id=game_id,
            )

        if game_data["status"] != TwentyQuestionsStatus.ACTIVE.value:
            return TwentyQuestionsErrorResponse(
                error="Game is not active",
                error_code="GAME_NOT_ACTIVE",
                game_id=game_id,
            )

        if game_data["questions_remaining"] <= 0:
            return TwentyQuestionsErrorResponse(
                error="No questions remaining",
                error_code="NO_QUESTIONS_REMAINING",
                game_id=game_id,
            )

        # Get the last AI question from history
        last_ai_question = await db.fetch_one(
            """
            SELECT question_text, question_number
            FROM twenty_questions_history
            WHERE game_id = $1 AND is_guess = false
            ORDER BY question_number DESC
            LIMIT 1
            """,
            game_id,
        )

        if not last_ai_question:
            return TwentyQuestionsErrorResponse(
                error="No AI question found to answer",
                error_code="NO_AI_QUESTION",
                game_id=game_id,
            )

        # Update game state
        new_questions_asked = game_data["questions_asked"] + 1
        new_questions_remaining = game_data["questions_remaining"] - 1

        await db.execute(
            """
            UPDATE twenty_questions_games
            SET questions_asked = $1, questions_remaining = $2, updated_at = CURRENT_TIMESTAMP
            WHERE id = $3
            """,
            new_questions_asked,
            new_questions_remaining,
            game_id,
        )

        # Add answer to history
        await db.execute(
            """
            INSERT INTO twenty_questions_history (
                game_id, question_number, question_text, answer, is_guess
            ) VALUES ($1, $2, $3, $4, $5)
            """,
            game_id,
            new_questions_asked,
            last_ai_question["question_text"],
            request.answer.value,
            False,
        )

        # Get updated game
        updated_game_data = await db.fetch_one(
            """
            SELECT id, user_id, category, target_person_id, target_person_name,
                   status, questions_asked, questions_remaining, final_guess,
                   answer_revealed, is_correct, created_at, updated_at
            FROM twenty_questions_games
            WHERE id = $1
            """,
            game_id,
        )

        game = TwentyQuestionsGameState(**updated_game_data)

        # Generate next AI question if game continues
        next_question = None
        question_number = None
        if new_questions_remaining > 0:
            # Get target person info
            target_person = {"name": game_data["target_person_name"]}
            if game_data["target_person_id"]:
                person_data = await db.fetch_one(
                    """
                    SELECT name, relationship, entry_type, species, personality_description
                    FROM people_in_my_life
                    WHERE id = $1
                    """,
                    game_data["target_person_id"],
                )
                if person_data:
                    target_person.update(person_data)

            # Get history for context
            history = await db.fetch_all(
                """
                SELECT question_number, question_text, answer, is_guess, created_at
                FROM twenty_questions_history
                WHERE game_id = $1
                ORDER BY question_number
                """,
                game_id,
            )

            next_question = await generate_ai_question(
                db, game_id, request.user_id, target_person, history, new_questions_asked + 1
            )
            question_number = new_questions_asked + 1

        return TwentyQuestionsAnswerResponse(
            game=game,
            next_question=next_question,
            question_number=question_number,
        )

    except Exception as e:
        logger.error(f"Error processing answer in game {game_id}: {e}")
        return TwentyQuestionsErrorResponse(
            error="Failed to process answer. Please try again.",
            error_code="ANSWER_ERROR",
            game_id=game_id,
        )


@router.post("/{game_id}/guess", response_model=TwentyQuestionsGuessResponse)
async def make_guess(
    game_id: UUID,
    request: TwentyQuestionsGuessRequest,
    db: Database = Depends(get_db),
):
    """User makes a final guess."""
    try:
        # Get game
        game_data = await db.fetch_one(
            """
            SELECT id, user_id, category, target_person_id, target_person_name,
                   status, questions_asked, questions_remaining, final_guess,
                   answer_revealed, is_correct, created_at, updated_at
            FROM twenty_questions_games
            WHERE id = $1 AND user_id = $2
            """,
            game_id,
            request.user_id,
        )

        if not game_data:
            return TwentyQuestionsErrorResponse(
                error="Game not found",
                error_code="GAME_NOT_FOUND",
                game_id=game_id,
            )

        if game_data["status"] != TwentyQuestionsStatus.ACTIVE.value:
            return TwentyQuestionsErrorResponse(
                error="Game is not active",
                error_code="GAME_NOT_ACTIVE",
                game_id=game_id,
            )

        # Check if guess is correct (case-insensitive partial match)
        target_name = game_data["target_person_name"].lower()
        guess_name = request.guess.lower()

        # Simple matching - could be made more sophisticated
        is_correct = (
            guess_name in target_name or target_name in guess_name or guess_name == target_name
        )

        # Determine game outcome
        new_status = TwentyQuestionsStatus.WON if is_correct else TwentyQuestionsStatus.LOST

        # Update game
        await db.execute(
            """
            UPDATE twenty_questions_games
            SET status = $1, final_guess = $2, answer_revealed = $3, is_correct = $4, updated_at = CURRENT_TIMESTAMP
            WHERE id = $5
            """,
            new_status.value,
            request.guess,
            game_data["target_person_name"],
            is_correct,
            game_id,
        )

        # Add guess to history
        await db.execute(
            """
            INSERT INTO twenty_questions_history (
                game_id, question_number, question_text, answer, is_guess
            ) VALUES ($1, $2, $3, $4, $5)
            """,
            game_id,
            game_data["questions_asked"] + 1,
            f"Final guess: {request.guess}",
            "correct" if is_correct else "incorrect",
            True,
        )

        # Get updated game
        updated_game_data = await db.fetch_one(
            """
            SELECT id, user_id, category, target_person_id, target_person_name,
                   status, questions_asked, questions_remaining, final_guess,
                   answer_revealed, is_correct, created_at, updated_at
            FROM twenty_questions_games
            WHERE id = $1
            """,
            game_id,
        )

        game = TwentyQuestionsGameState(**updated_game_data)

        # Generate response message
        if is_correct:
            message = f"🎉 Correct! I was thinking of {game_data['target_person_name']}. Great job!"
        else:
            message = f"❌ Sorry, that's not correct. I was thinking of {game_data['target_person_name']}. Better luck next time!"

        return TwentyQuestionsGuessResponse(
            game=game,
            is_correct=is_correct,
            answer_revealed=game_data["target_person_name"],
            message=message,
        )

    except Exception as e:
        logger.error(f"Error processing guess in game {game_id}: {e}")
        return TwentyQuestionsErrorResponse(
            error="Failed to process guess. Please try again.",
            error_code="GUESS_ERROR",
            game_id=game_id,
        )


@router.get("/{game_id}/status", response_model=TwentyQuestionsStatusResponse)
async def get_game_status(
    game_id: UUID,
    user_id: UUID,
    db: Database = Depends(get_db),
):
    """Get current game status and history."""
    try:
        # Get game
        game_data = await db.fetch_one(
            """
            SELECT id, user_id, category, target_person_id, target_person_name,
                   status, questions_asked, questions_remaining, final_guess,
                   answer_revealed, is_correct, created_at, updated_at
            FROM twenty_questions_games
            WHERE id = $1 AND user_id = $2
            """,
            game_id,
            user_id,
        )

        if not game_data:
            return TwentyQuestionsErrorResponse(
                error="Game not found",
                error_code="GAME_NOT_FOUND",
                game_id=game_id,
            )

        # Get history
        history_data = await db.fetch_all(
            """
            SELECT question_number, question_text, answer, is_guess, created_at
            FROM twenty_questions_history
            WHERE game_id = $1
            ORDER BY question_number
            """,
            game_id,
        )

        game = TwentyQuestionsGameState(**game_data)
        history = [TwentyQuestionsHistoryEntry(**entry) for entry in history_data]

        return TwentyQuestionsStatusResponse(
            game=game,
            history=history,
        )

    except Exception as e:
        logger.error(f"Error getting game status for {game_id}: {e}")
        return TwentyQuestionsErrorResponse(
            error="Failed to get game status. Please try again.",
            error_code="STATUS_ERROR",
            game_id=game_id,
        )
