# services/content/routes.py
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from models import (
    RecipesResponse,
    RecipeSyncRequest,
    RecipeSyncResponse,
    UserRecipe,
    UserRecipeCreate,
    UserRecipeUpdate,
)

from shared.auth_middleware import TokenData, get_current_user
from shared.database import Database, get_db
from shared.json_utils import parse_recipe_metadata as parse_recipe_data
from shared.json_utils import safe_json_dumps
from shared.uuid_utils import generate_uuid7

# Create router
content_router = APIRouter()

# Note: parse_recipe_metadata now imported from shared.json_utils as parse_recipe_data

# ============================================================================
# RECIPE STORAGE ROUTES
# ============================================================================


@content_router.get("/users/{user_id}/recipes", response_model=RecipesResponse)
async def get_user_recipes(
    user_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    app_id: Optional[str] = Query("fairydust-recipe"),
    favorited_only: bool = Query(False),
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get user recipes with pagination and filtering"""
    print(
        f"🍳 RECIPE_GET: Getting recipes for user {user_id}, limit={limit}, offset={offset}, app_id={app_id}, favorited_only={favorited_only}",
        flush=True,
    )

    # Users can only access their own recipes unless admin
    if current_user.user_id != str(user_id) and not current_user.is_admin:
        print(
            f"🚨 RECIPE_GET: Access denied for user {current_user.user_id} trying to access {user_id}",
            flush=True,
        )
        raise HTTPException(status_code=403, detail="Access denied")

    # Build query conditions
    conditions = ["user_id = $1"]
    params = [user_id]
    param_count = 2

    if app_id:
        conditions.append(f"app_id = ${param_count}")
        params.append(app_id)
        param_count += 1

    if favorited_only:
        conditions.append(f"is_favorited = ${param_count}")
        params.append(True)
        param_count += 1

    where_clause = " AND ".join(conditions)

    # Get total count
    count_result = await db.fetch_one(
        f"SELECT COUNT(*) as total FROM user_recipes WHERE {where_clause}", *params
    )
    total_count = count_result["total"]

    # Get recipes with pagination
    recipes = await db.fetch_all(
        f"""
        SELECT * FROM user_recipes
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT ${param_count} OFFSET ${param_count + 1}
    """,
        *params,
        limit,
        offset,
    )

    has_more = (offset + limit) < total_count

    print(
        f"✅ RECIPE_GET: Successfully retrieved {len(recipes)} recipes for user {user_id}, total_count={total_count}",
        flush=True,
    )
    return RecipesResponse(
        recipes=[UserRecipe(**parse_recipe_data(recipe)) for recipe in recipes],
        total_count=total_count,
        has_more=has_more,
    )


@content_router.post(
    "/users/{user_id}/recipes", response_model=dict, status_code=status.HTTP_201_CREATED
)
async def save_recipe(
    user_id: UUID,
    recipe_data: UserRecipeCreate,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Save a new recipe for the user"""
    print(
        f"🍳 RECIPE_SAVE: Saving recipe for user {user_id}, app_id={recipe_data.app_id}, category={recipe_data.category}",
        flush=True,
    )

    # Users can only save to their own account unless admin
    if current_user.user_id != str(user_id) and not current_user.is_admin:
        print(
            f"🚨 RECIPE_SAVE: Access denied for user {current_user.user_id} trying to save for {user_id}",
            flush=True,
        )
        raise HTTPException(status_code=403, detail="Access denied")

    # Validate content size (10MB limit as per spec)
    content_size = len(recipe_data.content.encode("utf-8"))
    print(f"🔍 RECIPE_SAVE: Content size validation - {content_size} bytes", flush=True)
    if content_size > 10 * 1024 * 1024:
        print(f"🚨 RECIPE_SAVE: Content too large - {content_size} bytes > 10MB limit", flush=True)
        raise HTTPException(status_code=413, detail="Recipe content too large (>10MB)")

    # Extract title from content if not provided
    title = recipe_data.title
    if not title and recipe_data.content:
        # Try to extract title from first line of content
        first_line = recipe_data.content.split("\n")[0].strip()
        if first_line.startswith("#"):
            title = first_line.lstrip("#").strip()
        elif first_line.startswith("**") and first_line.endswith("**"):
            title = first_line.strip("*").strip()
        else:
            title = first_line[:100] + "..." if len(first_line) > 100 else first_line

    recipe_id = generate_uuid7()

    # Convert metadata to JSON
    metadata_json = safe_json_dumps(recipe_data.metadata.dict() if recipe_data.metadata else {})

    # Insert recipe
    recipe = await db.fetch_one(
        """
        INSERT INTO user_recipes (
            id, user_id, app_id, title, content, category, metadata, is_favorited
        ) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
        RETURNING *
    """,
        recipe_id,
        user_id,
        recipe_data.app_id,
        title,
        recipe_data.content,
        recipe_data.category,
        metadata_json,
        False,
    )

    print(
        f"✅ RECIPE_SAVE: Successfully saved recipe {recipe_id} for user {user_id}, title='{title}'",
        flush=True,
    )
    return {"recipe": UserRecipe(**parse_recipe_data(recipe))}


@content_router.put("/users/{user_id}/recipes/{recipe_id}", response_model=dict)
async def update_recipe(
    user_id: UUID,
    recipe_id: UUID,
    recipe_update: UserRecipeUpdate,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Update recipe (favorite status or title)"""
    print(
        f"🍳 RECIPE_UPDATE: Updating recipe {recipe_id} for user {user_id}, title={recipe_update.title}, favorited={recipe_update.is_favorited}",
        flush=True,
    )

    # Users can only update their own recipes unless admin
    if current_user.user_id != str(user_id) and not current_user.is_admin:
        print(
            f"🚨 RECIPE_UPDATE: Access denied for user {current_user.user_id} trying to update {user_id}'s recipe",
            flush=True,
        )
        raise HTTPException(status_code=403, detail="Access denied")

    # Check if recipe exists and belongs to user
    recipe = await db.fetch_one(
        "SELECT * FROM user_recipes WHERE id = $1 AND user_id = $2", recipe_id, user_id
    )

    if not recipe:
        print(f"🚨 RECIPE_UPDATE: Recipe {recipe_id} not found for user {user_id}", flush=True)
        raise HTTPException(status_code=404, detail="Recipe not found")

    # Build update query dynamically
    update_fields = []
    update_values = []
    param_count = 1

    if recipe_update.title is not None:
        update_fields.append(f"title = ${param_count}")
        update_values.append(recipe_update.title)
        param_count += 1

    if recipe_update.is_favorited is not None:
        update_fields.append(f"is_favorited = ${param_count}")
        update_values.append(recipe_update.is_favorited)
        param_count += 1

    if not update_fields:
        # Return current recipe if no updates
        print(
            f"📝 RECIPE_UPDATE: No updates provided for recipe {recipe_id}, returning current data",
            flush=True,
        )
        return {"recipe": UserRecipe(**parse_recipe_data(recipe))}

    # Add updated_at field
    update_fields.append(f"updated_at = ${param_count}")
    update_values.append(datetime.utcnow())
    param_count += 1

    # Add recipe_id and user_id for WHERE clause
    update_values.extend([recipe_id, user_id])

    query = f"""
        UPDATE user_recipes
        SET {', '.join(update_fields)}
        WHERE id = ${param_count} AND user_id = ${param_count + 1}
        RETURNING *
    """

    updated_recipe = await db.fetch_one(query, *update_values)
    print(
        f"✅ RECIPE_UPDATE: Successfully updated recipe {recipe_id} for user {user_id}", flush=True
    )
    return {"recipe": UserRecipe(**parse_recipe_data(updated_recipe))}


@content_router.delete("/users/{user_id}/recipes/{recipe_id}")
async def delete_recipe(
    user_id: UUID,
    recipe_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Delete a recipe"""
    print(f"🍳 RECIPE_DELETE: Deleting recipe {recipe_id} for user {user_id}", flush=True)

    # Users can only delete their own recipes unless admin
    if current_user.user_id != str(user_id) and not current_user.is_admin:
        print(
            f"🚨 RECIPE_DELETE: Access denied for user {current_user.user_id} trying to delete {user_id}'s recipe",
            flush=True,
        )
        raise HTTPException(status_code=403, detail="Access denied")

    # Check if recipe exists and belongs to user
    recipe = await db.fetch_one(
        "SELECT id FROM user_recipes WHERE id = $1 AND user_id = $2", recipe_id, user_id
    )

    if not recipe:
        print(f"🚨 RECIPE_DELETE: Recipe {recipe_id} not found for user {user_id}", flush=True)
        raise HTTPException(status_code=404, detail="Recipe not found")

    # Delete recipe
    await db.execute("DELETE FROM user_recipes WHERE id = $1 AND user_id = $2", recipe_id, user_id)

    print(
        f"✅ RECIPE_DELETE: Successfully deleted recipe {recipe_id} for user {user_id}", flush=True
    )
    return {"success": True, "message": "Recipe deleted successfully"}


@content_router.post("/users/{user_id}/recipes/sync", response_model=RecipeSyncResponse)
async def sync_recipes(
    user_id: UUID,
    sync_request: RecipeSyncRequest,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Bulk sync recipes for mobile app"""
    print(
        f"🍳 RECIPE_SYNC: Starting sync for user {user_id}, local_recipes={len(sync_request.local_recipes)}, last_sync={sync_request.last_sync_timestamp}",
        flush=True,
    )

    # Users can only sync their own recipes unless admin
    if current_user.user_id != str(user_id) and not current_user.is_admin:
        print(
            f"🚨 RECIPE_SYNC: Access denied for user {current_user.user_id} trying to sync {user_id}'s recipes",
            flush=True,
        )
        raise HTTPException(status_code=403, detail="Access denied")

    sync_timestamp = datetime.utcnow()

    # Get server recipes updated after last sync
    server_conditions = ["user_id = $1"]
    server_params = [user_id]

    if sync_request.last_sync_timestamp:
        server_conditions.append("updated_at > $2")
        server_params.append(sync_request.last_sync_timestamp)

    server_recipes = await db.fetch_all(
        f"""
        SELECT * FROM user_recipes
        WHERE {' AND '.join(server_conditions)}
        ORDER BY created_at DESC
    """,
        *server_params,
    )

    # Process local recipes for upload
    sync_conflicts = []

    for local_recipe in sync_request.local_recipes:
        # Validate content size
        if len(local_recipe.content.encode("utf-8")) > 10 * 1024 * 1024:
            continue  # Skip recipes that are too large

        # Extract title if not provided
        title = local_recipe.title
        if not title and local_recipe.content:
            first_line = local_recipe.content.split("\n")[0].strip()
            if first_line.startswith("#"):
                title = first_line.lstrip("#").strip()
            elif first_line.startswith("**") and first_line.endswith("**"):
                title = first_line.strip("*").strip()
            else:
                title = first_line[:100] + "..." if len(first_line) > 100 else first_line

        # Check for conflicts (recipe with same content created around same time)
        # For simplicity, we'll just insert new recipes for now
        # Real conflict resolution would be more complex

        recipe_id = generate_uuid7()
        metadata_json = safe_json_dumps(local_recipe.metadata or {})

        try:
            await db.execute(
                """
                INSERT INTO user_recipes (
                    id, user_id, app_id, title, content, category, metadata,
                    is_favorited, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9)
            """,
                recipe_id,
                user_id,
                local_recipe.app_id,
                title,
                local_recipe.content,
                local_recipe.category,
                metadata_json,
                False,
                local_recipe.created_at,
            )
        except Exception as e:
            # Log the error but continue with sync
            print(f"🚨 RECIPE_SYNC: Error syncing recipe {local_recipe.local_id}: {e}", flush=True)
            continue

    print(
        f"✅ RECIPE_SYNC: Sync completed for user {user_id}, server_recipes={len(server_recipes)}, conflicts={len(sync_conflicts)}",
        flush=True,
    )
    return RecipeSyncResponse(
        server_recipes=[UserRecipe(**parse_recipe_data(recipe)) for recipe in server_recipes],
        sync_conflicts=sync_conflicts,
        sync_timestamp=sync_timestamp,
    )


# Health check endpoint
@content_router.get("/health")
async def health_check():
    return {"status": "healthy", "service": "content", "version": "1.0.0"}
