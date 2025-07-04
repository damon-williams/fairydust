# services/content/models.py
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# Recipe Storage Models
class RecipeMetadata(BaseModel):
    complexity: Optional[str] = None  # "Simple", "Medium", "Gourmet"
    dish: Optional[str] = None
    include: Optional[str] = None  # Included ingredients
    exclude: Optional[str] = None  # Excluded ingredients
    generation_params: Optional[dict] = Field(default_factory=dict)
    parsed_data: Optional[dict] = Field(default_factory=dict)


class UserRecipeCreate(BaseModel):
    app_id: str = Field(..., max_length=255)
    title: Optional[str] = Field(None, max_length=500)
    content: str = Field(..., min_length=1)
    category: Optional[str] = Field(None, max_length=255)
    metadata: Optional[RecipeMetadata] = Field(default_factory=RecipeMetadata)


class UserRecipeUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    is_favorited: Optional[bool] = None


class UserRecipe(BaseModel):
    id: UUID
    user_id: UUID
    app_id: str
    title: Optional[str]
    content: str
    category: Optional[str]
    metadata: dict
    is_favorited: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RecipesResponse(BaseModel):
    recipes: list[UserRecipe]
    total_count: int
    has_more: bool


class LocalRecipe(BaseModel):
    local_id: str
    app_id: str
    title: Optional[str] = None
    content: str
    category: Optional[str] = None
    metadata: Optional[dict] = Field(default_factory=dict)
    created_at: datetime


class RecipeSyncRequest(BaseModel):
    local_recipes: list[LocalRecipe]
    last_sync_timestamp: Optional[datetime] = None


class RecipeSyncResponse(BaseModel):
    server_recipes: list[UserRecipe]
    sync_conflicts: list[dict] = Field(default_factory=list)
    sync_timestamp: datetime


# Story App Models
class StoryLength(str, Enum):
    QUICK = "quick"  # 2-3 minute read
    MEDIUM = "medium"  # 5-7 minute read
    LONG = "long"  # 8-12 minute read


class TargetAudience(str, Enum):
    KIDS = "kids"
    ADULTS = "adults"


class StoryCharacter(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    relationship: str = Field(..., min_length=1, max_length=100)
    birth_date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    traits: list[str] = Field(default_factory=list, max_items=10)


class TokenUsage(BaseModel):
    prompt: int
    completion: int
    total: int


class StoryGenerationRequest(BaseModel):
    user_id: UUID
    story_length: StoryLength  # Reading time instead of word count
    characters: list[StoryCharacter] = Field(default_factory=list, max_items=8)
    custom_prompt: Optional[str] = Field(None, max_length=1000)
    target_audience: TargetAudience = TargetAudience.KIDS
    session_id: Optional[UUID] = None


class StoryGenerationMetadata(BaseModel):
    model_config = {"protected_namespaces": ()}

    model_used: str
    tokens_used: int
    generation_time_ms: int


class UserStory(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    content: str
    story_length: StoryLength  # Reading time
    characters_involved: list[StoryCharacter]
    metadata: dict
    is_favorited: bool
    word_count: Optional[int]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class StoryGenerationResponse(BaseModel):
    story: UserStory
    generation_metadata: StoryGenerationMetadata


class StoriesResponse(BaseModel):
    stories: list[UserStory]
    total_count: int
    has_more: bool


class StoryFavoriteRequest(BaseModel):
    is_favorited: bool


class StoryStatistics(BaseModel):
    total_stories: int
    favorite_stories: int
    total_words: int
    genres_explored: list[str]
    most_common_genre: Optional[str]
    dust_spent: int
    average_story_length: str


class StoryGenerationLog(BaseModel):
    id: UUID
    user_id: UUID
    story_id: Optional[UUID]
    generation_prompt: str
    llm_model: Optional[str]
    tokens_used: Optional[int]
    generation_time_ms: Optional[int]
    success: bool
    error_message: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# New Story App Models for Enhanced API
class UserStoryNew(BaseModel):
    id: UUID
    title: str
    content: str
    story_length: StoryLength  # Reading time instead of word count
    target_audience: TargetAudience
    word_count: int
    estimated_reading_time: str
    created_at: datetime
    is_favorited: bool = False
    metadata: dict = Field(default_factory=dict)

    class Config:
        from_attributes = True


class StoryGenerationResponseNew(BaseModel):
    success: bool = True
    story: UserStoryNew
    model_used: str
    tokens_used: TokenUsage
    cost: float

    class Config:
        protected_namespaces = ()


class StoriesListResponse(BaseModel):
    success: bool = True
    stories: list[UserStoryNew]
    total_count: int
    favorites_count: int


class StoryFavoriteResponse(BaseModel):
    success: bool = True
    story: UserStoryNew


class StoryDeleteResponse(BaseModel):
    success: bool = True
    message: str = "Story deleted successfully"


class StoryConfigResponse(BaseModel):
    success: bool = True
    config: dict


class StoryErrorResponse(BaseModel):
    success: bool = False
    error: str
    valid_genres: Optional[list[str]] = None
    valid_lengths: Optional[list[dict]] = None
    story_id: Optional[UUID] = None


# Fortune Teller App Models
class ReadingType(str, Enum):
    QUESTION = "question"
    DAILY = "daily"


class CosmicInfluences(BaseModel):
    zodiac_sign: str
    moon_phase: str
    planetary_focus: str
    life_path_number: int


class LuckyElements(BaseModel):
    color: str
    number: int
    element: str
    gemstone: str


class FortuneReading(BaseModel):
    id: UUID
    content: str
    reading_type: ReadingType
    question: Optional[str] = None
    target_person_id: Optional[UUID] = None  # None for self-readings, UUID for others
    target_person_name: str
    created_at: datetime
    is_favorited: bool = False


class FortuneGenerationRequest(BaseModel):
    user_id: UUID
    target_person_id: Optional[UUID] = None  # NULL for self-readings
    reading_type: ReadingType
    question: Optional[str] = Field(None, max_length=500)
    birth_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    birth_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    birth_location: Optional[str] = Field(None, max_length=200)
    name: str = Field(..., min_length=1, max_length=100)
    gender: Optional[str] = Field(None, max_length=20)


class FortuneGenerationResponse(BaseModel):
    success: bool = True
    reading: FortuneReading
    model_used: str
    tokens_used: TokenUsage
    cost: float


class FortuneHistoryResponse(BaseModel):
    success: bool = True
    readings: list[FortuneReading]
    total_count: int
    favorites_count: int


class FortuneProfile(BaseModel):
    birth_date: str
    birth_time: Optional[str] = None
    birth_location: Optional[str] = None
    zodiac_sign: str
    zodiac_element: str
    life_path_number: int
    ruling_planet: str


class FortuneProfileRequest(BaseModel):
    birth_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    birth_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    birth_location: Optional[str] = Field(None, max_length=200)
    gender: Optional[str] = Field(None, max_length=20)


class FortuneProfileResponse(BaseModel):
    success: bool = True
    person: dict  # Will contain person data with fortune_profile


class FortuneFavoriteRequest(BaseModel):
    is_favorited: bool


class FortuneFavoriteResponse(BaseModel):
    success: bool = True
    reading: FortuneReading


class FortuneDeleteResponse(BaseModel):
    success: bool = True
    message: str = "Reading deleted successfully"


class FortuneErrorResponse(BaseModel):
    success: bool = False
    error: str
    reading_id: Optional[UUID] = None


# Restaurant App Models
class RestaurantLocation(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    address: str = Field(..., min_length=1, max_length=500)


class RestaurantPreferences(BaseModel):
    party_size: int = Field(2, ge=1, le=20)
    cuisine_types: Optional[list[str]] = Field(default_factory=list)
    opentable_only: bool = Field(False)
    time_preference: Optional[str] = Field(None, pattern="^(now|tonight|weekend)$")
    special_occasion: Optional[str] = Field(None, max_length=200)
    max_results: int = Field(10, ge=1, le=20)


class RestaurantGenerateRequest(BaseModel):
    user_id: UUID
    location: RestaurantLocation
    preferences: RestaurantPreferences
    selected_people: list[UUID] = Field(default_factory=list)
    session_id: Optional[UUID] = None


class OpenTableInfo(BaseModel):
    has_reservations: bool
    available_times: list[str] = Field(default_factory=list)
    booking_url: str


class Restaurant(BaseModel):
    id: str
    name: str
    cuisine: str
    address: str
    distance_miles: float
    price_level: str = Field(..., pattern=r"^(\$|\$\$|\$\$\$)$")
    rating: float = Field(..., ge=0, le=5)
    phone: Optional[str] = None
    google_place_id: Optional[str] = None
    opentable: OpenTableInfo
    highlights: list[str] = Field(default_factory=list)


class RestaurantResponse(BaseModel):
    restaurants: list[Restaurant]
    session_id: UUID
    generated_at: datetime


class RestaurantRegenerateRequest(BaseModel):
    session_id: UUID
    exclude_restaurants: list[str] = Field(default_factory=list)


class PersonRestaurantPreferences(BaseModel):
    person_id: UUID
    favorite_restaurants: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


class UserRestaurantPreferences(BaseModel):
    personal_preferences: dict = Field(
        default_factory=lambda: {"default_radius": "10mi", "preferred_cuisines": []}
    )
    people_preferences: list[PersonRestaurantPreferences] = Field(default_factory=list)


class UserRestaurantPreferencesUpdate(BaseModel):
    personal_preferences: Optional[dict] = None
    people_preferences: Optional[list[PersonRestaurantPreferences]] = None


# Activity App Models
class ActivityLocation(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    radius_miles: int = Field(10, ge=1, le=50)


class ActivityLocationType(str, Enum):
    ATTRACTIONS = "attractions"
    DESTINATIONS = "destinations"
    BOTH = "both"


class ActivitySearchRequest(BaseModel):
    user_id: UUID
    location: ActivityLocation
    location_type: ActivityLocationType = ActivityLocationType.BOTH
    selected_people: list[str] = Field(default_factory=list)  # person_id strings


class ActivityHours(BaseModel):
    monday: Optional[str] = None
    tuesday: Optional[str] = None
    wednesday: Optional[str] = None
    thursday: Optional[str] = None
    friday: Optional[str] = None
    saturday: Optional[str] = None
    sunday: Optional[str] = None


class ActivityStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    CLOSING_SOON = "closing_soon"


class ActivityType(str, Enum):
    ATTRACTION = "attraction"
    DESTINATION = "destination"


class Activity(BaseModel):
    id: str
    tripadvisor_id: str
    name: str
    type: ActivityType

    # Location details
    address: str
    distance_miles: float
    latitude: float
    longitude: float

    # TripAdvisor data
    rating: Optional[float] = None
    num_reviews: Optional[int] = None
    price_level: Optional[str] = None  # "$", "$$", "$$$", "$$$$"
    photos: list[str] = Field(default_factory=list, max_items=5)
    hours: Optional[ActivityHours] = None
    current_status: Optional[ActivityStatus] = None
    phone: Optional[str] = None
    website: Optional[str] = None

    # AI-generated content
    ai_context: str
    suitability_tags: list[str] = Field(default_factory=list)


class ActivitySearchMetadata(BaseModel):
    total_found: int
    radius_used: int
    location_address: str


class ActivitySearchResponse(BaseModel):
    activities: list[Activity] = Field(..., max_items=12)
    search_metadata: ActivitySearchMetadata


# Inspire App Models
class InspirationCategory(str, Enum):
    CHALLENGE = "A challenge to try"
    CREATIVE = "A creative spark"
    SELF_CARE = "Something good for me"
    KIND_GESTURE = "Something nice for another"


class InspirationGenerateRequest(BaseModel):
    user_id: UUID
    category: InspirationCategory
    used_suggestions: list[str] = Field(default_factory=list, max_items=20)
    session_id: Optional[UUID] = None


class UserInspiration(BaseModel):
    id: UUID
    content: str
    category: InspirationCategory
    created_at: datetime
    is_favorited: bool = False

    class Config:
        from_attributes = True


class InspirationGenerateResponse(BaseModel):
    success: bool = True
    inspiration: UserInspiration
    model_used: str
    tokens_used: TokenUsage
    cost: float
    new_dust_balance: int

    class Config:
        protected_namespaces = ()


class InspirationsListResponse(BaseModel):
    success: bool = True
    inspirations: list[UserInspiration]
    total_count: int
    favorites_count: int


class InspirationFavoriteRequest(BaseModel):
    is_favorited: bool


class InspirationFavoriteResponse(BaseModel):
    success: bool = True
    inspiration: UserInspiration


class InspirationDeleteResponse(BaseModel):
    success: bool = True
    message: str = "Inspiration deleted successfully"


class InspirationErrorResponse(BaseModel):
    success: bool = False
    error: str
    current_balance: Optional[int] = None
    required_amount: Optional[int] = None
    valid_categories: Optional[list[str]] = None
    inspiration_id: Optional[UUID] = None


# Recipe App Models
class RecipeComplexity(str, Enum):
    SIMPLE = "Simple"
    MEDIUM = "Medium"
    GOURMET = "Gourmet"


class DietaryRestriction(str, Enum):
    VEGETARIAN = "vegetarian"
    VEGAN = "vegan"
    GLUTEN_FREE = "gluten_free"
    DAIRY_FREE = "dairy_free"
    NUT_FREE = "nut_free"
    SHELLFISH_FREE = "shellfish_free"
    SOY_FREE = "soy_free"
    EGG_FREE = "egg_free"
    LOW_CARB = "low_carb"
    KETO = "keto"
    PALEO = "paleo"
    WHOLE30 = "whole30"


class RecipeGenerateRequest(BaseModel):
    user_id: UUID
    dish: Optional[str] = None
    complexity: RecipeComplexity
    include_ingredients: Optional[str] = None
    exclude_ingredients: Optional[str] = None
    selected_people: list[UUID] = Field(default_factory=list)
    total_people: int = Field(..., ge=1, le=12)
    session_id: Optional[UUID] = None


class UserRecipeNew(BaseModel):
    id: UUID
    title: str
    content: str
    complexity: RecipeComplexity
    servings: int
    prep_time_minutes: Optional[int] = None
    cook_time_minutes: Optional[int] = None
    created_at: datetime
    is_favorited: bool = False
    metadata: dict = Field(default_factory=dict)

    class Config:
        from_attributes = True


class RecipeGenerateResponse(BaseModel):
    success: bool = True
    recipe: UserRecipeNew
    model_used: str
    tokens_used: TokenUsage
    cost: float
    new_dust_balance: int

    class Config:
        protected_namespaces = ()


class RecipesListResponse(BaseModel):
    success: bool = True
    recipes: list[UserRecipeNew]
    total_count: int
    favorites_count: int


class RecipeAdjustRequest(BaseModel):
    user_id: UUID
    recipe_id: UUID
    adjustment_instructions: str = Field(..., min_length=1, max_length=1000)


class RecipeFavoriteRequest(BaseModel):
    is_favorited: bool


class RecipeAdjustResponse(BaseModel):
    success: bool = True
    recipe: UserRecipeNew
    model_used: str
    tokens_used: TokenUsage
    cost: float
    adjustments_applied: str

    class Config:
        protected_namespaces = ()


class RecipeFavoriteResponse(BaseModel):
    success: bool = True
    recipe: UserRecipeNew


class RecipeDeleteResponse(BaseModel):
    success: bool = True
    message: str = "Recipe deleted successfully"


class PersonPreference(BaseModel):
    person_id: UUID
    person_name: Optional[str] = None
    selected_restrictions: list[DietaryRestriction] = Field(default_factory=list)
    foods_to_avoid: Optional[str] = None


class RecipePreferences(BaseModel):
    personal_restrictions: list[DietaryRestriction] = Field(default_factory=list)
    custom_restrictions: Optional[str] = None
    people_preferences: list[PersonPreference] = Field(default_factory=list)


class RecipePreferencesResponse(BaseModel):
    success: bool = True
    preferences: RecipePreferences


class RecipePreferencesUpdateRequest(BaseModel):
    personal_restrictions: list[DietaryRestriction] = Field(default_factory=list)
    custom_restrictions: Optional[str] = None
    people_preferences: list[PersonPreference] = Field(default_factory=list)


class RecipeErrorResponse(BaseModel):
    success: bool = False
    error: str
    current_balance: Optional[int] = None
    required_amount: Optional[int] = None
    valid_levels: Optional[list[str]] = None
    min_servings: Optional[int] = None
    max_servings: Optional[int] = None
    recipe_id: Optional[UUID] = None


# Custom Character Models
class CustomCharacterCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    description: str = Field(..., min_length=1, max_length=1000)
    character_type: str = Field("custom", max_length=20)


class CustomCharacterUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    description: Optional[str] = Field(None, min_length=1, max_length=1000)
    character_type: Optional[str] = Field(None, max_length=20)
    is_active: Optional[bool] = None


class CustomCharacter(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    description: str
    character_type: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CustomCharactersResponse(BaseModel):
    success: bool = True
    characters: list[CustomCharacter]
    total_count: int


class CustomCharacterResponse(BaseModel):
    success: bool = True
    character: CustomCharacter


class CustomCharacterDeleteResponse(BaseModel):
    success: bool = True
    message: str = "Character deleted successfully"


class CustomCharacterErrorResponse(BaseModel):
    success: bool = False
    error: str
    error_code: Optional[str] = None
    character_id: Optional[UUID] = None


# Would You Rather Game Models
class GameLength(int, Enum):
    SHORT = 5
    MEDIUM = 10
    LONG = 20


class GameCategory(str, Enum):
    THOUGHT_PROVOKING = "thought-provoking"
    FUNNY_SILLY = "funny-silly" 
    FAMILY_FRIENDLY = "family-friendly"
    WORK_CAREER = "work-career"
    RELATIONSHIPS_LOVE = "relationships-love"
    FANTASY_SUPERPOWERS = "fantasy-superpowers"
    POP_CULTURE = "pop-culture"
    TRAVEL_ADVENTURE = "travel-adventure"
    MIX_IT_UP = "mix-it-up"


class GameStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class QuestionObject(BaseModel):
    id: UUID
    question_number: int = Field(..., ge=1, le=20)
    option_a: str = Field(..., min_length=1, max_length=500)
    option_b: str = Field(..., min_length=1, max_length=500)
    category: str


class AnswerObject(BaseModel):
    question_id: UUID
    chosen_option: Optional[str] = Field(None, pattern=r"^[ab]$")
    answered_at: Optional[datetime] = None


class WyrGameSessionCreate(BaseModel):
    user_id: UUID
    game_length: GameLength
    category: GameCategory
    custom_request: Optional[str] = Field(None, max_length=1000)


class WyrGameSessionProgress(BaseModel):
    question_id: UUID
    chosen_option: str = Field(..., pattern=r"^[ab]$")
    current_question: int = Field(..., ge=1, le=20)


class WyrGameSessionComplete(BaseModel):
    final_answers: list[AnswerObject]


class WyrGameSession(BaseModel):
    session_id: UUID
    user_id: UUID
    game_length: int
    category: str
    custom_request: Optional[str] = None
    status: GameStatus
    current_question: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    questions: list[QuestionObject]
    answers: list[AnswerObject]
    summary: Optional[str] = None

    class Config:
        from_attributes = True


class WyrGameSessionResponse(BaseModel):
    success: bool = True
    session: WyrGameSession


class WyrGameSessionsResponse(BaseModel):
    success: bool = True
    sessions: list[WyrGameSession]
    total_count: int
    in_progress_count: int
    completed_count: int


class WyrGameCompleteResponse(BaseModel):
    success: bool = True
    session: WyrGameSession
    summary: str


class WyrGameDeleteResponse(BaseModel):
    success: bool = True
    message: str = "Session deleted successfully"


class WyrGameErrorResponse(BaseModel):
    success: bool = False
    error: str
    error_code: Optional[str] = None
    session_id: Optional[UUID] = None


# Error Response Model
class ErrorResponse(BaseModel):
    error: dict

    @classmethod
    def create(cls, code: str, message: str, details: dict = None):
        return cls(error={"code": code, "message": message, "details": details or {}})
