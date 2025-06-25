# services/content/models.py
from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field
from enum import Enum

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
    recipes: List[UserRecipe]
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
    local_recipes: List[LocalRecipe]
    last_sync_timestamp: Optional[datetime] = None

class RecipeSyncResponse(BaseModel):
    server_recipes: List[UserRecipe]
    sync_conflicts: List[dict] = Field(default_factory=list)
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
    SHORT = "short"     # 300-500 words
    MEDIUM = "medium"   # 600-1000 words
    LONG = "long"       # 1000-1500 words

class TargetAudience(str, Enum):
    CHILD = "child"
    ADULT = "adult"
    FAMILY = "family"

class StoryCharacter(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    relationship: str = Field(..., min_length=1, max_length=100)
    age: Optional[int] = Field(None, ge=0, le=120)
    traits: List[str] = Field(default_factory=list, max_items=10)
    role_in_story: Optional[str] = None
    personality_description: Optional[str] = None

class StoryGenerationRequest(BaseModel):
    genre: StoryGenre
    story_length: StoryLength
    characters: List[StoryCharacter] = Field(..., min_items=1, max_items=8)
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
    characters_involved: List[StoryCharacter]
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
    stories: List[UserStory]
    total_count: int
    has_more: bool

class StoryFavoriteRequest(BaseModel):
    is_favorited: bool

class StoryStatistics(BaseModel):
    total_stories: int
    favorite_stories: int
    total_words: int
    genres_explored: List[str]
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
    cuisine_types: Optional[List[str]] = Field(default_factory=list)
    opentable_only: bool = Field(False)
    time_preference: Optional[str] = Field(None, pattern="^(now|tonight|weekend)$")
    special_occasion: Optional[str] = Field(None, max_length=200)
    max_results: int = Field(10, ge=1, le=20)

class RestaurantGenerateRequest(BaseModel):
    user_id: UUID
    location: RestaurantLocation
    preferences: RestaurantPreferences
    selected_people: List[UUID] = Field(default_factory=list)
    session_id: Optional[UUID] = None

class OpenTableInfo(BaseModel):
    has_reservations: bool
    available_times: List[str] = Field(default_factory=list)
    booking_url: str

class Restaurant(BaseModel):
    id: str
    name: str
    cuisine: str
    address: str
    distance_miles: float
    price_level: str = Field(..., pattern="^(\$|\$\$|\$\$\$)$")
    rating: float = Field(..., ge=0, le=5)
    phone: Optional[str] = None
    google_place_id: Optional[str] = None
    opentable: OpenTableInfo
    highlights: List[str] = Field(default_factory=list)

class RestaurantResponse(BaseModel):
    restaurants: List[Restaurant]
    session_id: UUID
    generated_at: datetime

class RestaurantRegenerateRequest(BaseModel):
    session_id: UUID
    exclude_restaurants: List[str] = Field(default_factory=list)

class PersonRestaurantPreferences(BaseModel):
    person_id: UUID
    favorite_restaurants: List[str] = Field(default_factory=list)
    notes: Optional[str] = None

class UserRestaurantPreferences(BaseModel):
    personal_preferences: dict = Field(default_factory=lambda: {
        "default_radius": "10mi",
        "preferred_cuisines": []
    })
    people_preferences: List[PersonRestaurantPreferences] = Field(default_factory=list)

class UserRestaurantPreferencesUpdate(BaseModel):
    personal_preferences: Optional[dict] = None
    people_preferences: Optional[List[PersonRestaurantPreferences]] = None

# Error Response Model
class ErrorResponse(BaseModel):
    error: dict

    @classmethod
    def create(cls, code: str, message: str, details: dict = None):
        return cls(error={
            "code": code,
            "message": message,
            "details": details or {}
        })