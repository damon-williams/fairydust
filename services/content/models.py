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
class StoryGenre(str, Enum):
    ADVENTURE = "adventure"
    FANTASY = "fantasy"
    ROMANCE = "romance"
    COMEDY = "comedy"
    MYSTERY = "mystery"
    FAMILY = "family"
    BEDTIME = "bedtime"


class StoryLength(str, Enum):
    SHORT = "short"  # 300-500 words
    MEDIUM = "medium"  # 600-1000 words
    LONG = "long"  # 1000-1500 words


class TargetAudience(str, Enum):
    CHILD = "child"
    ADULT = "adult"
    FAMILY = "family"


class StoryCharacter(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    relationship: str = Field(..., min_length=1, max_length=100)
    age: Optional[int] = Field(None, ge=0, le=120)
    traits: list[str] = Field(default_factory=list, max_items=10)
    role_in_story: Optional[str] = None
    personality_description: Optional[str] = None


class StoryGenerationRequest(BaseModel):
    genre: StoryGenre
    story_length: StoryLength
    characters: list[StoryCharacter] = Field(..., min_items=1, max_items=8)
    setting: Optional[str] = Field(None, max_length=500)
    theme: Optional[str] = Field(None, max_length=500)
    custom_prompt: Optional[str] = Field(None, max_length=1000)
    target_audience: Optional[TargetAudience] = TargetAudience.FAMILY


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
    genre: StoryGenre
    story_length: StoryLength
    characters_involved: list[StoryCharacter]
    metadata: dict
    is_favorited: bool
    dust_cost: int
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


class TokenUsage(BaseModel):
    prompt: int
    completion: int
    total: int


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


# Error Response Model
class ErrorResponse(BaseModel):
    error: dict

    @classmethod
    def create(cls, code: str, message: str, details: dict = None):
        return cls(error={"code": code, "message": message, "details": details or {}})
