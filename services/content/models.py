# services/content/models.py
from datetime import datetime
from typing import Optional, List
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