# services/content/twenty_questions_routes.py
import logging
import random
from typing import Union
from uuid import UUID
from shared.uuid_utils import generate_uuid7

from fastapi import APIRouter, Depends, HTTPException, status
from models import (
    TwentyQuestionsAnswer,
    TwentyQuestionsAnswerRequest,
    TwentyQuestionsAnswerResponse,
    TwentyQuestionsErrorResponse,
    TwentyQuestionsGameState,
    TwentyQuestionsGuessRequest,
    TwentyQuestionsGuessResponse,
    TwentyQuestionsHistoryEntry,
    TwentyQuestionsMode,
    TwentyQuestionsQuestionRequest,
    TwentyQuestionsQuestionResponse,
    TwentyQuestionsStartRequest,
    TwentyQuestionsStartResponse,
    TwentyQuestionsStatus,
    TwentyQuestionsStatusResponse,
)

from shared.database import Database, get_db
from shared.llm_client import llm_client

router = APIRouter()
logger = logging.getLogger(__name__)

# Constants
TWENTY_QUESTIONS_RATE_LIMIT = 10  # Max 10 games per hour per user




async def generate_secret_answer(category: str, user_id: UUID) -> str:
    """Generate a secret answer for fairydust_thinks mode, avoiding previous answers."""
    try:
        # Get database connection
        from shared.database import get_db
        db = await get_db()

        # Get user's previous secret answers from this category to avoid duplicates
        previous_answers = await db.fetch_all(
            """
            SELECT secret_answer 
            FROM twenty_questions_games 
            WHERE user_id = $1 AND category = $2 AND secret_answer IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 20
            """,
            user_id,
            category,
        )
        
        previous_list = [row["secret_answer"] for row in previous_answers if row["secret_answer"]]
        logger.info(f"🔍 SECRET_GEN: Found {len(previous_list)} previous answers for {category}: {previous_list}")

        # Get LLM model configuration
        model_config = await get_llm_model_config()

        # Build anti-duplication context
        avoid_text = ""
        if previous_list:
            avoid_text = f"\n\nIMPORTANT: Avoid these answers that have been used before:\n{', '.join(previous_list)}\n\nGenerate something completely different."

        # Build prompt for secret answer generation
        prompt = f"""You are playing 20 Questions. Generate a specific, concrete answer from the category "{category}" that would make for a fun and fair guessing game.

The answer should be:
- Specific and well-known
- Not too obscure or too obvious
- Something that can be guessed through yes/no questions
- One to three words maximum

Category: {category}

Examples by category:
- animals: "elephant", "golden retriever", "hummingbird"
- movies: "The Lion King", "Titanic", "Star Wars"
- objects: "bicycle", "coffee mug", "smartphone"
- food: "pizza", "chocolate cake", "apple"{avoid_text}

Generate one answer from the "{category}" category. Respond with just the answer, nothing else."""

        # Get app ID
        app_id = await get_app_id(db)

        # Try multiple times to avoid duplicates
        max_attempts = 3
        for attempt in range(max_attempts):
            logger.info(f"🎲 SECRET_GEN: Attempt {attempt + 1}/{max_attempts} for category {category}")
            
            # Use centralized LLM client
            completion, metadata = await llm_client.generate_completion(
                prompt=prompt,
                app_config=model_config,
                user_id=user_id,
                app_id=str(app_id),
                action="twenty_questions_secret_generation",
                request_metadata={
                    "category": category,
                    "attempt": attempt + 1,
                    "previous_answers": previous_list,
                },
            )

            new_answer = completion.strip()
            
            # Check if this answer was used before (case-insensitive)
            if not any(new_answer.lower() == prev.lower() for prev in previous_list):
                logger.info(f"✅ SECRET_GEN: Generated unique answer: {new_answer}")
                return new_answer
            else:
                logger.warning(f"⚠️ SECRET_GEN: Generated duplicate answer '{new_answer}', retrying...")

        # If all attempts failed, use fallback with uniqueness check
        logger.warning(f"❌ SECRET_GEN: All LLM attempts generated duplicates, using fallback")
        
    except Exception as e:
        logger.error(f"❌ SECRET_GEN: Failed to generate secret answer: {e}")

    # Fallback answers by category with uniqueness check
    fallback_answers = {
        "animals": ["elephant", "dolphin", "butterfly", "penguin", "giraffe", "kangaroo", "octopus", "flamingo", "zebra", "panda"],
        "movies": ["Titanic", "Star Wars", "The Lion King", "Avatar", "Frozen", "Jurassic Park", "The Matrix", "Finding Nemo", "Shrek", "Toy Story"],
        "food": ["pizza", "chocolate", "apple", "banana", "hamburger", "sushi", "ice cream", "pasta", "sandwich", "cookies"],
        "objects": ["bicycle", "smartphone", "book", "umbrella", "guitar", "camera", "lamp", "mirror", "clock", "pillow"],
        "general": ["tree", "ocean", "mountain", "rainbow", "sunset", "cloud", "river", "flower", "bridge", "castle"],
    }
    
    category_answers = fallback_answers.get(category.lower(), fallback_answers["general"])
    
    # Try to find a unique fallback answer
    for answer in category_answers:
        if not previous_list or not any(answer.lower() == prev.lower() for prev in previous_list):
            logger.info(f"🔄 SECRET_GEN: Using unique fallback answer: {answer}")
            return answer
    
    # If even fallbacks are all used, just return the first one (very unlikely)
    fallback_answer = category_answers[0]
    logger.warning(f"⚠️ SECRET_GEN: All fallbacks used, returning: {fallback_answer}")
    return fallback_answer


async def get_llm_model_config() -> dict:
    """Get LLM configuration for 20 Questions app using normalized structure"""
    from shared.app_config_cache import get_app_config_cache
    from shared.json_utils import parse_jsonb_field

    app_slug = "fairydust-20-questions"
    logger.info(f"🔍 20Q_CONFIG: Starting LLM config lookup for app: {app_slug}")

    # First, get the app UUID from the slug
    from shared.database import get_db

    db = await get_db()
    app_result = await db.fetch_one("SELECT id FROM apps WHERE slug = $1", app_slug)

    if not app_result:
        logger.warning(f"❌ 20Q_CONFIG: App with slug '{app_slug}' not found in database")
        # Return default config if app not found
        default_config = {
            "primary_provider": "anthropic",
            "primary_model_id": "claude-3-5-haiku-20241022",
            "primary_parameters": {"temperature": 0.8, "max_tokens": 150, "top_p": 0.9},
        }
        logger.info(f"🔄 20Q_CONFIG: Using default config: {default_config}")
        return default_config

    app_id = str(app_result["id"])
    logger.info(f"✅ 20Q_CONFIG: Found app {app_slug} with UUID: {app_id}")

    try:
        # Try to get from cache first
        cache = await get_app_config_cache()
        cached_config = await cache.get_model_config(app_id)

        if cached_config:
            logger.info(f"💾 20Q_CONFIG: Using cached config: {cached_config}")
            return cached_config
        else:
            logger.info("🔍 20Q_CONFIG: No cached config found, checking database")

        # Fetch from database - normalized structure
        config_result = await db.fetch_one(
            """
            SELECT provider, model_id, parameters, is_enabled
            FROM app_model_configs
            WHERE app_id = $1 AND model_type = 'text' AND is_enabled = true
            """,
            app_result["id"],
        )

        logger.info(f"📊 20Q_CONFIG: Database query result: {config_result}")

        if config_result:
            parameters = parse_jsonb_field(
                config_result["parameters"], default={}, field_name="parameters"
            )

            model_config = {
                "primary_provider": config_result["provider"],
                "primary_model_id": config_result["model_id"],
                "primary_parameters": parameters,
            }
            logger.info(f"✅ 20Q_CONFIG: Using database config: {model_config}")
        else:
            # Use default configuration
            model_config = {
                "primary_provider": "anthropic",
                "primary_model_id": "claude-3-5-haiku-20241022",
                "primary_parameters": {"temperature": 0.8, "max_tokens": 150, "top_p": 0.9},
            }
            logger.info(f"🔄 20Q_CONFIG: No database config found, using default: {model_config}")

        # Cache the result
        await cache.set_model_config(app_id, model_config)
        logger.info(f"💾 20Q_CONFIG: Cached config for future use")
        return model_config

    except Exception as e:
        logger.error(f"❌ 20Q_CONFIG: Error fetching LLM config for {app_slug}: {e}")
        # Return default on error
        default_config = {
            "primary_provider": "anthropic",
            "primary_model_id": "claude-3-5-haiku-20241022",
            "primary_parameters": {"temperature": 0.8, "max_tokens": 150, "top_p": 0.9},
        }
        logger.info(f"🔄 20Q_CONFIG: Using default config due to error: {default_config}")
        return default_config


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
            if not entry.get("is_guess", False) and entry.get("answer") != "pending":
                asked_by = entry.get("asked_by", "user")
                if asked_by == "ai":
                    history_items.append(
                        f"AI Q{entry['question_number']}: {entry['question_text']} - User answered: {entry['answer']}"
                    )
                else:
                    history_items.append(
                        f"User Q{entry['question_number']}: {entry['question_text']} - AI answered: {entry['answer']}"
                    )
        if history_items:
            history_context = "\n\nPrevious questions and answers:\n" + "\n".join(
                history_items
            )  # Include ALL Q&A pairs for full game context

    # Build prompt without category references
    prompt = f"""You are playing 20 Questions. I'm thinking of someone or something, and you need to ask a strategic yes/no question to narrow down what it might be.

This is question #{question_number} out of 20.{history_context}

Ask a strategic yes/no question to help identify what I'm thinking of. This could be a person, place, object, or concept. Make it conversational and engaging.

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
        # Fallback questions based on question number (generic)
        fallback_questions = [
            "Is it something living?",
            "Is it something you can touch?",
            "Is it bigger than a breadbox?",
            "Is it something found indoors?",
            "Is it man-made?",
            "Is it something you use every day?",
            "Is it electronic?",
            "Is it expensive?",
            "Is it colorful?",
            "Is it something that moves?",
        ]
        return fallback_questions[min(question_number - 1, len(fallback_questions) - 1)]


async def generate_ai_final_guess(
    db: Database,
    game_id: UUID,
    user_id: UUID,
    target_person: dict,
    history: list[dict],
) -> str:
    """Generate AI's final guess based on all Q&A history."""
    
    # Build context from game history
    history_context = ""
    if history:
        history_items = []
        for entry in history:
            if not entry.get("is_guess", False) and entry.get("answer") != "pending":
                asked_by = entry.get("asked_by", "user")
                if asked_by == "ai":
                    history_items.append(
                        f"Q{entry['question_number']}: {entry['question_text']} - Answer: {entry['answer']}"
                    )
        if history_items:
            history_context = "Based on these questions and answers:\n" + "\n".join(history_items)

    # Build prompt for final guess
    prompt = f"""You are playing 20 Questions. Based on all the questions and answers, make your final guess about what I'm thinking of.

{history_context}

Based on the answers to my questions, what do you think I'm thinking of? This could be a person, place, object, or concept. 

IMPORTANT: You must make a specific guess. Do not respond with "Unknown", "I don't know", or anything vague. Even if you're uncertain, make your best educated guess based on the information you have.

Examples of good guesses: "a cat", "pizza", "The Lion King", "Albert Einstein", "a bicycle"
Examples of bad responses: "Unknown", "I'm not sure", "Something living"

Respond with just your specific guess, nothing else:"""

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
            action="twenty_questions_final_guess",
            request_metadata={
                "game_id": str(game_id),
                "target_person_name": target_person.get("name", "Unknown"),
                "history_length": len(history),
            },
        )

        final_guess = completion.strip()
        
        # Post-processing: If AI somehow still returned "Unknown" or similar, fix it
        if final_guess.lower() in ["unknown", "i don't know", "not sure", "unclear", "uncertain", ""]:
            logger.warning(f"AI returned invalid guess '{final_guess}', using fallback")
            fallback_guesses = [
                "a cat", "a dog", "pizza", "a car", "a tree", "a book", 
                "a phone", "a movie", "music", "a game"
            ]
            import random
            final_guess = random.choice(fallback_guesses)
        
        return final_guess

    except Exception as e:
        logger.error(f"Failed to generate AI final guess: {e}")
        # Fallback guess - make a reasonable attempt based on common answers
        fallback_guesses = [
            "a cat", "a dog", "pizza", "a car", "a tree", "a book", 
            "a phone", "a movie", "music", "a game"
        ]
        import random
        return random.choice(fallback_guesses)


def check_guess_accuracy(guess: str, correct_answer: str) -> bool:
    """Check if the guess matches the correct answer (case-insensitive partial match)."""
    if not guess or not correct_answer:
        return False
    
    guess_lower = guess.lower().strip()
    answer_lower = correct_answer.lower().strip()
    
    # Exact match
    if guess_lower == answer_lower:
        return True
    
    # Partial matches (one contains the other)
    if guess_lower in answer_lower or answer_lower in guess_lower:
        return True
    
    # Check individual words for name variations
    guess_words = set(guess_lower.split())
    answer_words = set(answer_lower.split())
    
    # If they share significant words, consider it correct
    shared_words = guess_words.intersection(answer_words)
    if len(shared_words) > 0 and len(shared_words) / max(len(guess_words), len(answer_words)) > 0.5:
        return True
    
    return False


async def generate_ai_answer_to_user_question(
    db: Database,
    game_id: UUID,
    user_id: UUID,
    secret_answer: str,
    question: str,
    category: str,
    history: list[dict],
) -> TwentyQuestionsAnswer:
    """Generate AI's answer to user's question in fairydust_thinks mode."""
    
    # Build context from previous Q&A
    history_context = ""
    if history:
        history_items = []
        for entry in history:
            if not entry.get("is_guess", False):
                history_items.append(
                    f"Q: {entry['question_text']} - A: {entry['answer']}"
                )
        if history_items:
            history_context = "\n\nPrevious Q&A:\n" + "\n".join(history_items)
    
    prompt = f"""You are playing 20 Questions. I'm thinking of "{secret_answer}" from the category "{category}".

A user just asked: "{question}"

Based on my secret answer "{secret_answer}", how should I respond to this question?

{history_context}

Answer with exactly one of these responses:
- "yes" if the answer is clearly yes
- "no" if the answer is clearly no  
- "sometimes" if it depends or is partially true
- "unknown" if the information is not clear or not applicable

Consider the secret answer "{secret_answer}" and respond appropriately to the question "{question}".

Response:"""

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
            action="twenty_questions_answer_generation",
            request_metadata={
                "game_id": str(game_id),
                "secret_answer": secret_answer,
                "user_question": question,
                "category": category,
            },
        )

        # Parse the response and return appropriate enum
        response = completion.strip().lower()
        if response in ["yes", "y"]:
            return TwentyQuestionsAnswer.YES
        elif response in ["no", "n"]:
            return TwentyQuestionsAnswer.NO
        elif response in ["sometimes", "maybe", "partially"]:
            return TwentyQuestionsAnswer.SOMETIMES
        else:
            return TwentyQuestionsAnswer.UNKNOWN

    except Exception as e:
        logger.error(f"Failed to generate AI answer: {e}")
        # Fallback to SOMETIMES for playability
        return TwentyQuestionsAnswer.SOMETIMES


async def determine_ai_answer(
    target_person: dict, question: str, category: str = "general"
) -> TwentyQuestionsAnswer:
    """Determine how the AI should answer based on the target and question."""
    
    # For all categories, the AI conceptually chooses and answers
    # This should eventually use LLM to determine answers based on the category
    # For now, return SOMETIMES to make the game playable
    return TwentyQuestionsAnswer.SOMETIMES


async def get_app_id(db: Database) -> UUID:
    """Get the 20 Questions app ID."""
    app = await db.fetch_one("SELECT id FROM apps WHERE slug = 'fairydust-20-questions'")
    if not app:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="20 Questions app not configured",
        )
    return app["id"]


async def check_rate_limit(db: Database, user_id: UUID) -> bool:
    """Check if user has exceeded rate limit for game creation"""
    try:
        # Count games started in the last hour
        query = """
            SELECT COUNT(*) as game_count
            FROM twenty_questions_games
            WHERE user_id = $1
            AND created_at > NOW() - INTERVAL '1 hour'
        """

        result = await db.fetch_one(query, user_id)
        game_count = result["game_count"] if result else 0

        if game_count >= TWENTY_QUESTIONS_RATE_LIMIT:
            logger.warning(
                f"User {user_id} exceeded rate limit: {game_count}/{TWENTY_QUESTIONS_RATE_LIMIT}"
            )
            return True

        return False

    except Exception as e:
        logger.error(f"Error checking rate limit: {e}")
        return False  # Allow on error


@router.post(
    "/start", response_model=Union[TwentyQuestionsStartResponse, TwentyQuestionsErrorResponse]
)
async def start_game(
    request: TwentyQuestionsStartRequest,
    db: Database = Depends(get_db),
):
    """Start a new 20 Questions game."""
    try:
        # Check rate limit
        rate_limit_exceeded = await check_rate_limit(db, request.user_id)
        if rate_limit_exceeded:
            return TwentyQuestionsErrorResponse(
                error=f"Rate limit exceeded. Maximum {TWENTY_QUESTIONS_RATE_LIMIT} games per hour.",
                error_code="RATE_LIMIT_EXCEEDED",
            )
        # Auto-abandon any existing active games
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
            # Mark the old game as abandoned
            await db.execute(
                """
                UPDATE twenty_questions_games
                SET status = 'abandoned', updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
                """,
                existing_game["id"],
            )
            logger.info(
                f"Auto-abandoned existing game {existing_game['id']} for user {request.user_id}"
            )

        # Handle different game modes
        if request.mode == TwentyQuestionsMode.FAIRYDUST_THINKS:
            # Fairydust thinks mode - generate secret answer
            secret_answer = await generate_secret_answer(request.category, request.user_id)
            target_name = "Secret Answer"  # Will be revealed only at game end
            current_ai_question = None  # No AI question in this mode
            start_message = f"Game started! I'm thinking of something from {request.category}. Ask me yes/no questions to figure out what it is!"
        else:
            # User thinks mode - AI will ask questions
            secret_answer = None
            target_name = f"Something from {request.category}"
            start_message = f"Game started! I'm thinking of something. Here's my first question:"

        # Create new game
        game_id = generate_uuid7()
        await db.execute(
            """
            INSERT INTO twenty_questions_games (
                id, user_id, category, mode, target_person_id, target_person_name, secret_answer,
                status, questions_asked, questions_remaining
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            game_id,
            request.user_id,
            request.category,
            request.mode.value,
            None,  # No target person ID
            target_name,
            secret_answer,
            TwentyQuestionsStatus.ACTIVE.value,
            0,
            20,
        )

        # Generate AI's first question only for user_thinks mode
        first_ai_question = None
        if request.mode == TwentyQuestionsMode.USER_THINKS:
            target_person = {"name": target_name}
            first_ai_question = await generate_ai_question(
                db, game_id, request.user_id, target_person, [], 1
            )

            # Update game with the first AI question
            await db.execute(
                """
                UPDATE twenty_questions_games
                SET current_ai_question = $1, updated_at = CURRENT_TIMESTAMP
                WHERE id = $2
                """,
                first_ai_question,
                game_id,
            )

            # Add AI's first question to history
            await db.execute(
                """
                INSERT INTO twenty_questions_history (
                    id, game_id, question_number, question_text, answer, is_guess, asked_by, mode
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                generate_uuid7(),
                game_id,
                1,
                first_ai_question,
                "pending",  # No answer yet
                False,
                "ai",
                request.mode.value,
            )

            start_message = f"{start_message} {first_ai_question}"

        # Fetch created game
        game_data = await db.fetch_one(
            """
            SELECT id, user_id, category, mode, target_person_id, target_person_name, secret_answer,
                   status, questions_asked, questions_remaining, current_ai_question,
                   final_guess, answer_revealed, is_correct, created_at, updated_at
            FROM twenty_questions_games
            WHERE id = $1
            """,
            game_id,
        )

        # Create game state - hide secret answer from response
        game_data_dict = dict(game_data)
        if request.mode == TwentyQuestionsMode.FAIRYDUST_THINKS:
            game_data_dict["secret_answer"] = None  # Hide secret answer
            game_data_dict["target_person_name"] = None  # Hide target name

        game = TwentyQuestionsGameState(**game_data_dict)

        return TwentyQuestionsStartResponse(
            game=game,
            message=start_message,
        )

    except Exception as e:
        logger.error(f"Error starting 20 Questions game: {e}")
        return TwentyQuestionsErrorResponse(
            error="Failed to start game. Please try again.",
            error_code="GAME_START_ERROR",
        )


@router.post(
    "/{game_id}/question",
    response_model=Union[TwentyQuestionsQuestionResponse, TwentyQuestionsErrorResponse],
)
async def ask_question(
    game_id: UUID,
    request: TwentyQuestionsQuestionRequest,
    db: Database = Depends(get_db),
):
    """Handle user questions - works differently for each mode."""
    try:
        # Get game
        game_data = await db.fetch_one(
            """
            SELECT id, user_id, category, mode, target_person_id, target_person_name, secret_answer,
                   status, questions_asked, questions_remaining, current_ai_question,
                   final_guess, answer_revealed, is_correct, created_at, updated_at
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

        game_mode = game_data["mode"]

        if game_mode == TwentyQuestionsMode.USER_THINKS.value:
            # User thinks mode - This endpoint shouldn't be used, user should use /answer
            return TwentyQuestionsErrorResponse(
                error="In user_thinks mode, use /answer endpoint to respond to AI questions",
                error_code="WRONG_ENDPOINT_FOR_MODE",
                game_id=game_id,
            )

        elif game_mode == TwentyQuestionsMode.FAIRYDUST_THINKS.value:
            # Fairydust thinks mode - User is asking the AI a question
            
            # Get game history for context
            history = await db.fetch_all(
                """
                SELECT question_number, question_text, answer, is_guess, asked_by, mode, created_at
                FROM twenty_questions_history
                WHERE game_id = $1
                ORDER BY question_number
                """,
                game_id,
            )

            # Generate AI's answer to user's question
            ai_answer = await generate_ai_answer_to_user_question(
                db, game_id, request.user_id, game_data["secret_answer"], 
                request.question, game_data["category"], history
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

            # Add to history
            await db.execute(
                """
                INSERT INTO twenty_questions_history (
                    id, game_id, question_number, question_text, answer, is_guess, asked_by, mode
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                generate_uuid7(),
                game_id,
                new_questions_asked,
                request.question,
                ai_answer.value,
                False,
                "user",
                game_mode,
            )

            # Get updated game state
            updated_game_data = await db.fetch_one(
                """
                SELECT id, user_id, category, mode, target_person_id, target_person_name, secret_answer,
                       status, questions_asked, questions_remaining, current_ai_question,
                       final_guess, answer_revealed, is_correct, created_at, updated_at
                FROM twenty_questions_games
                WHERE id = $1
                """,
                game_id,
            )

            # Hide secret answer from response
            game_data_dict = dict(updated_game_data)
            game_data_dict["secret_answer"] = None
            game_data_dict["target_person_name"] = None

            game = TwentyQuestionsGameState(**game_data_dict)

            return TwentyQuestionsQuestionResponse(
                game=game,
                ai_answer=ai_answer,
                question_number=new_questions_asked,
            )

        else:
            return TwentyQuestionsErrorResponse(
                error="Unknown game mode",
                error_code="UNKNOWN_MODE",
                game_id=game_id,
            )

    except Exception as e:
        logger.error(f"Error processing question in game {game_id}: {e}")
        return TwentyQuestionsErrorResponse(
            error="Failed to process question. Please try again.",
            error_code="QUESTION_ERROR",
            game_id=game_id,
        )


@router.post(
    "/{game_id}/answer",
    response_model=Union[TwentyQuestionsAnswerResponse, TwentyQuestionsErrorResponse],
)
async def answer_ai_question(
    game_id: UUID,
    request: TwentyQuestionsAnswerRequest,
    db: Database = Depends(get_db),
):
    """User answers the AI's question (only works in user_thinks mode)."""
    try:
        # Get game
        game_data = await db.fetch_one(
            """
            SELECT id, user_id, category, mode, target_person_id, target_person_name, secret_answer,
                   status, questions_asked, questions_remaining, current_ai_question,
                   final_guess, answer_revealed, is_correct, created_at, updated_at
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

        # Check if this endpoint is being used in the correct mode
        if game_data["mode"] != TwentyQuestionsMode.USER_THINKS.value:
            return TwentyQuestionsErrorResponse(
                error="In fairydust_thinks mode, use /question endpoint to ask questions",
                error_code="WRONG_ENDPOINT_FOR_MODE",
                game_id=game_id,
            )

        # Get the current AI question that needs to be answered
        current_ai_question = game_data.get("current_ai_question")
        if not current_ai_question:
            return TwentyQuestionsErrorResponse(
                error="No AI question to answer",
                error_code="NO_AI_QUESTION",
                game_id=game_id,
            )

        # Update the pending AI question in history with the user's answer
        await db.execute(
            """
            UPDATE twenty_questions_history
            SET answer = $1
            WHERE game_id = $2 AND asked_by = 'ai' AND answer = 'pending'
            """,
            request.answer.value,
            game_id,
        )

        # Update game state - questions asked/remaining
        new_questions_asked = game_data["questions_asked"] + 1
        new_questions_remaining = game_data["questions_remaining"] - 1

        # Generate next AI question or make final guess
        next_ai_question = None
        ai_final_guess = None
        
        if new_questions_remaining > 0:
            # Get target info
            target_person = {"name": game_data["target_person_name"]}

            # Get full history for context (including the answer we just recorded)
            history = await db.fetch_all(
                """
                SELECT question_number, question_text, answer, is_guess, asked_by, mode, created_at
                FROM twenty_questions_history
                WHERE game_id = $1
                ORDER BY question_number
                """,
                game_id,
            )

            next_ai_question = await generate_ai_question(
                db, game_id, request.user_id, target_person, history, new_questions_asked + 1
            )

            # Add the next AI question to history and update game state
            await db.execute(
                """
                INSERT INTO twenty_questions_history (
                    id, game_id, question_number, question_text, answer, is_guess, asked_by, mode
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                generate_uuid7(),
                game_id,
                new_questions_asked + 1,
                next_ai_question,
                "pending",
                False,
                "ai",
                game_data["mode"],
            )
        else:
            # No questions remaining - AI makes final guess
            target_person = {"name": game_data["target_person_name"]}

            # Get full history for AI's final guess
            history = await db.fetch_all(
                """
                SELECT question_number, question_text, answer, is_guess, asked_by, mode, created_at
                FROM twenty_questions_history
                WHERE game_id = $1
                ORDER BY question_number
                """,
                game_id,
            )

            ai_final_guess = await generate_ai_final_guess(
                db, game_id, request.user_id, target_person, history
            )
            
            # Check if AI's guess is correct
            is_ai_correct = check_guess_accuracy(ai_final_guess, game_data["target_person_name"])
            
            # Update game with AI's final guess and result
            new_status = TwentyQuestionsStatus.LOST if is_ai_correct else TwentyQuestionsStatus.WON
            
            await db.execute(
                """
                UPDATE twenty_questions_games
                SET status = $1, final_guess = $2, answer_revealed = $3, is_correct = $4, updated_at = CURRENT_TIMESTAMP
                WHERE id = $5
                """,
                new_status.value,
                ai_final_guess,
                game_data["target_person_name"],
                is_ai_correct,
                game_id,
            )
            
            # Add AI's final guess to history
            await db.execute(
                """
                INSERT INTO twenty_questions_history (
                    id, game_id, question_number, question_text, answer, is_guess, asked_by, mode
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                generate_uuid7(),
                game_id,
                new_questions_asked + 1,
                f"My final guess: {ai_final_guess}",
                "correct" if is_ai_correct else "incorrect",
                True,
                "ai",
                game_data["mode"],
            )

        # Update game with new state and next AI question (only if not final guess)
        if next_ai_question:
            await db.execute(
                """
                UPDATE twenty_questions_games
                SET questions_asked = $1, questions_remaining = $2, current_ai_question = $3, updated_at = CURRENT_TIMESTAMP
                WHERE id = $4
                """,
                new_questions_asked,
                new_questions_remaining,
                next_ai_question,
                game_id,
            )
        else:
            # Final guess scenario - just update basic counters
            await db.execute(
                """
                UPDATE twenty_questions_games
                SET questions_asked = $1, questions_remaining = $2, current_ai_question = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE id = $3
                """,
                new_questions_asked,
                new_questions_remaining,
                game_id,
            )

        # Get updated game
        updated_game_data = await db.fetch_one(
            """
            SELECT id, user_id, category, mode, target_person_id, target_person_name, secret_answer,
                   status, questions_asked, questions_remaining, current_ai_question,
                   final_guess, answer_revealed, is_correct, created_at, updated_at
            FROM twenty_questions_games
            WHERE id = $1
            """,
            game_id,
        )

        # Hide secret fields for frontend
        game_data_dict = dict(updated_game_data)
        if game_data_dict["mode"] == TwentyQuestionsMode.FAIRYDUST_THINKS.value:
            game_data_dict["secret_answer"] = None

        game = TwentyQuestionsGameState(**game_data_dict)

        # Build response with AI final guess information if applicable
        if ai_final_guess:
            is_ai_correct = check_guess_accuracy(ai_final_guess, game_data["target_person_name"])
            if is_ai_correct:
                message = f"🤖 I guessed '{ai_final_guess}' and I was correct! I win this round! 🏆"
            else:
                message = f"🤖 I guessed '{ai_final_guess}' but I was wrong. You win! The correct answer was '{game_data['target_person_name']}'. 🎉"
                
            return TwentyQuestionsAnswerResponse(
                game=game,
                ai_final_guess=ai_final_guess,
                is_ai_correct=is_ai_correct,
                answer_revealed=game_data["target_person_name"],
                message=message,
            )
        else:
            return TwentyQuestionsAnswerResponse(
                game=game,
                next_question=next_ai_question,
                question_number=new_questions_asked + 1 if next_ai_question else None,
            )

    except Exception as e:
        logger.error(f"Error processing answer in game {game_id}: {e}")
        return TwentyQuestionsErrorResponse(
            error="Failed to process answer. Please try again.",
            error_code="ANSWER_ERROR",
            game_id=game_id,
        )


@router.post(
    "/{game_id}/guess",
    response_model=Union[TwentyQuestionsGuessResponse, TwentyQuestionsErrorResponse],
)
async def make_guess(
    game_id: UUID,
    request: TwentyQuestionsGuessRequest,
    db: Database = Depends(get_db),
):
    """User makes a final guess (works for both modes)."""
    try:
        # Get game
        game_data = await db.fetch_one(
            """
            SELECT id, user_id, category, mode, target_person_id, target_person_name, secret_answer,
                   status, questions_asked, questions_remaining, current_ai_question,
                   final_guess, answer_revealed, is_correct, created_at, updated_at
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

        # Check if guess is correct based on game mode
        if game_data["mode"] == TwentyQuestionsMode.FAIRYDUST_THINKS.value:
            # In fairydust_thinks mode, compare against secret_answer
            target_name = game_data["secret_answer"]
            answer_revealed = game_data["secret_answer"]
        else:
            # In user_thinks mode, compare against target_person_name
            target_name = game_data["target_person_name"]
            answer_revealed = game_data["target_person_name"]

        # Simple matching - could be made more sophisticated
        is_correct = check_guess_accuracy(request.guess, target_name)

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
            answer_revealed,
            is_correct,
            game_id,
        )

        # Add guess to history
        await db.execute(
            """
            INSERT INTO twenty_questions_history (
                id, game_id, question_number, question_text, answer, is_guess, asked_by, mode
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            generate_uuid7(),
            game_id,
            game_data["questions_asked"] + 1,
            f"Final guess: {request.guess}",
            "correct" if is_correct else "incorrect",
            True,
            "user",
            game_data["mode"],
        )

        # Get updated game
        updated_game_data = await db.fetch_one(
            """
            SELECT id, user_id, category, mode, target_person_id, target_person_name, secret_answer,
                   status, questions_asked, questions_remaining, current_ai_question,
                   final_guess, answer_revealed, is_correct, created_at, updated_at
            FROM twenty_questions_games
            WHERE id = $1
            """,
            game_id,
        )

        # Hide secret fields for frontend
        game_data_dict = dict(updated_game_data)
        if game_data_dict["mode"] == TwentyQuestionsMode.FAIRYDUST_THINKS.value:
            game_data_dict["secret_answer"] = None

        game = TwentyQuestionsGameState(**game_data_dict)

        # Generate response message
        if is_correct:
            message = f"🎉 Correct! I was thinking of {answer_revealed}. Great job!"
        else:
            message = f"❌ Sorry, that's not correct. I was thinking of {answer_revealed}. Better luck next time!"

        return TwentyQuestionsGuessResponse(
            game=game,
            is_correct=is_correct,
            answer_revealed=answer_revealed,
            message=message,
        )

    except Exception as e:
        logger.error(f"Error processing guess in game {game_id}: {e}")
        return TwentyQuestionsErrorResponse(
            error="Failed to process guess. Please try again.",
            error_code="GUESS_ERROR",
            game_id=game_id,
        )


@router.get(
    "/{game_id}/status",
    response_model=Union[TwentyQuestionsStatusResponse, TwentyQuestionsErrorResponse],
)
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
            SELECT id, user_id, category, mode, target_person_id, target_person_name, secret_answer,
                   status, questions_asked, questions_remaining, current_ai_question,
                   final_guess, answer_revealed, is_correct, created_at, updated_at
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
            SELECT question_number, question_text, answer, is_guess, asked_by, mode, created_at
            FROM twenty_questions_history
            WHERE game_id = $1
            ORDER BY question_number
            """,
            game_id,
        )

        # Hide secret fields for frontend
        game_data_dict = dict(game_data)
        if game_data_dict["mode"] == TwentyQuestionsMode.FAIRYDUST_THINKS.value:
            game_data_dict["secret_answer"] = None
            # Only reveal target name if game is over
            if game_data_dict["status"] not in ["won", "lost"]:
                game_data_dict["target_person_name"] = None

        game = TwentyQuestionsGameState(**game_data_dict)
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
