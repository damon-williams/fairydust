# services/content/character_routes.py
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, UploadFile
from models import (
    CustomCharacter,
    CustomCharacterCreate,
    CustomCharacterDeleteResponse,
    CustomCharacterErrorResponse,
    CustomCharacterResponse,
    CustomCharactersResponse,
    CustomCharacterUpdate,
)

from shared.auth_middleware import TokenData, get_current_user
from shared.database import Database, get_db
from shared.storage_service import delete_character_image, upload_character_image

router = APIRouter()


@router.get("/users/{user_id}/characters", response_model=CustomCharactersResponse)
async def get_user_characters(
    user_id: UUID = Path(..., description="User ID"),
    active_only: bool = Query(True, description="Only return active characters"),
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get all custom characters for a user"""
    # Verify user can only access their own characters
    if current_user.user_id != str(user_id):
        return CustomCharacterErrorResponse(
            error="Can only access your own characters", error_code="FORBIDDEN"
        )

    try:
        # Build query based on active_only parameter
        if active_only:
            query = """
                SELECT id, user_id, name, description, character_type, is_active,
                       image_url, image_uploaded_at, image_size_bytes, created_at, updated_at
                FROM custom_characters
                WHERE user_id = $1 AND is_active = true
                ORDER BY created_at DESC
            """
            characters_data = await db.fetch_all(query, user_id)
        else:
            query = """
                SELECT id, user_id, name, description, character_type, is_active,
                       image_url, image_uploaded_at, image_size_bytes, created_at, updated_at
                FROM custom_characters
                WHERE user_id = $1
                ORDER BY created_at DESC
            """
            characters_data = await db.fetch_all(query, user_id)

        # Convert to Pydantic models
        characters = [CustomCharacter(**char_data) for char_data in characters_data]

        return CustomCharactersResponse(characters=characters, total_count=len(characters))

    except Exception as e:
        print(f"🚨 CHARACTER: Error fetching characters for user {user_id}: {e}", flush=True)
        return CustomCharacterErrorResponse(
            error="Failed to fetch characters", error_code="DATABASE_ERROR"
        )


@router.post("/users/{user_id}/characters", response_model=CustomCharacterResponse)
async def create_character(
    user_id: UUID = Path(..., description="User ID"),
    character_data: CustomCharacterCreate = ...,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Create a new custom character for a user"""
    # Verify user can only create characters for themselves
    if current_user.user_id != str(user_id):
        return CustomCharacterErrorResponse(
            error="Can only create characters for yourself", error_code="FORBIDDEN"
        )

    try:
        # Check if character name already exists for this user
        existing_check = await db.fetch_one(
            "SELECT id FROM custom_characters WHERE user_id = $1 AND name = $2",
            user_id,
            character_data.name,
        )

        if existing_check:
            return CustomCharacterErrorResponse(
                error=f"Character with name '{character_data.name}' already exists",
                error_code="DUPLICATE_NAME",
            )

        # Insert new character
        query = """
            INSERT INTO custom_characters (user_id, name, description, character_type, is_active, created_at, updated_at)
            VALUES ($1, $2, $3, $4, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id, user_id, name, description, character_type, is_active,
                      image_url, image_uploaded_at, image_size_bytes, created_at, updated_at
        """

        character_record = await db.fetch_one(
            query,
            user_id,
            character_data.name,
            character_data.description,
            character_data.character_type,
        )

        if not character_record:
            return CustomCharacterErrorResponse(
                error="Failed to create character", error_code="DATABASE_ERROR"
            )

        character = CustomCharacter(**character_record)
        print(f"✅ CHARACTER: Created character '{character.name}' for user {user_id}", flush=True)

        return CustomCharacterResponse(character=character)

    except Exception as e:
        print(f"🚨 CHARACTER: Error creating character for user {user_id}: {e}", flush=True)
        return CustomCharacterErrorResponse(
            error="Failed to create character", error_code="DATABASE_ERROR"
        )


@router.put("/users/{user_id}/characters/{character_id}", response_model=CustomCharacterResponse)
async def update_character(
    user_id: UUID = Path(..., description="User ID"),
    character_id: UUID = Path(..., description="Character ID"),
    character_data: CustomCharacterUpdate = ...,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Update an existing custom character"""
    # Verify user can only update their own characters
    if current_user.user_id != str(user_id):
        return CustomCharacterErrorResponse(
            error="Can only update your own characters", error_code="FORBIDDEN"
        )

    try:
        # Check if character exists and belongs to user
        existing_character = await db.fetch_one(
            "SELECT id, user_id, name, description, character_type, is_active, image_url, image_uploaded_at, image_size_bytes, created_at, updated_at FROM custom_characters WHERE id = $1 AND user_id = $2",
            character_id,
            user_id,
        )

        if not existing_character:
            return CustomCharacterErrorResponse(
                error="Character not found", error_code="NOT_FOUND", character_id=character_id
            )

        # Check for duplicate name if name is being updated
        if character_data.name and character_data.name != existing_character["name"]:
            duplicate_check = await db.fetch_one(
                "SELECT id FROM custom_characters WHERE user_id = $1 AND name = $2 AND id != $3",
                user_id,
                character_data.name,
                character_id,
            )

            if duplicate_check:
                return CustomCharacterErrorResponse(
                    error=f"Character with name '{character_data.name}' already exists",
                    error_code="DUPLICATE_NAME",
                    character_id=character_id,
                )

        # Build update query dynamically based on provided fields
        update_fields = []
        update_values = []
        param_count = 1

        if character_data.name is not None:
            update_fields.append(f"name = ${param_count}")
            update_values.append(character_data.name)
            param_count += 1

        if character_data.description is not None:
            update_fields.append(f"description = ${param_count}")
            update_values.append(character_data.description)
            param_count += 1

        if character_data.character_type is not None:
            update_fields.append(f"character_type = ${param_count}")
            update_values.append(character_data.character_type)
            param_count += 1

        if character_data.is_active is not None:
            update_fields.append(f"is_active = ${param_count}")
            update_values.append(character_data.is_active)
            param_count += 1

        if not update_fields:
            # No fields to update, return existing character
            character = CustomCharacter(**existing_character)
            return CustomCharacterResponse(character=character)

        # Add updated_at timestamp
        update_fields.append(f"updated_at = ${param_count}")
        update_values.append(datetime.utcnow())
        param_count += 1

        # Add WHERE clause parameters
        update_values.extend([character_id, user_id])

        query = f"""
            UPDATE custom_characters
            SET {', '.join(update_fields)}
            WHERE id = ${param_count} AND user_id = ${param_count + 1}
            RETURNING id, user_id, name, description, character_type, is_active,
                      image_url, image_uploaded_at, image_size_bytes, created_at, updated_at
        """

        updated_character = await db.fetch_one(query, *update_values)

        if not updated_character:
            return CustomCharacterErrorResponse(
                error="Failed to update character",
                error_code="DATABASE_ERROR",
                character_id=character_id,
            )

        character = CustomCharacter(**updated_character)
        print(f"✅ CHARACTER: Updated character '{character.name}' for user {user_id}", flush=True)

        return CustomCharacterResponse(character=character)

    except Exception as e:
        print(
            f"🚨 CHARACTER: Error updating character {character_id} for user {user_id}: {e}",
            flush=True,
        )
        return CustomCharacterErrorResponse(
            error="Failed to update character",
            error_code="DATABASE_ERROR",
            character_id=character_id,
        )


@router.delete(
    "/users/{user_id}/characters/{character_id}", response_model=CustomCharacterDeleteResponse
)
async def delete_character(
    user_id: UUID = Path(..., description="User ID"),
    character_id: UUID = Path(..., description="Character ID"),
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Delete a custom character"""
    # Verify user can only delete their own characters
    if current_user.user_id != str(user_id):
        return CustomCharacterErrorResponse(
            error="Can only delete your own characters", error_code="FORBIDDEN"
        )

    try:
        # Check if character exists and belongs to user
        existing_character = await db.fetch_one(
            "SELECT id, name FROM custom_characters WHERE id = $1 AND user_id = $2",
            character_id,
            user_id,
        )

        if not existing_character:
            return CustomCharacterErrorResponse(
                error="Character not found", error_code="NOT_FOUND", character_id=character_id
            )

        # Delete the character
        result = await db.execute(
            "DELETE FROM custom_characters WHERE id = $1 AND user_id = $2", character_id, user_id
        )

        if result == "DELETE 0":
            return CustomCharacterErrorResponse(
                error="Failed to delete character",
                error_code="DATABASE_ERROR",
                character_id=character_id,
            )

        print(
            f"✅ CHARACTER: Deleted character '{existing_character['name']}' for user {user_id}",
            flush=True,
        )

        return CustomCharacterDeleteResponse(
            message=f"Character '{existing_character['name']}' deleted successfully"
        )

    except Exception as e:
        print(
            f"🚨 CHARACTER: Error deleting character {character_id} for user {user_id}: {e}",
            flush=True,
        )
        return CustomCharacterErrorResponse(
            error="Failed to delete character",
            error_code="DATABASE_ERROR",
            character_id=character_id,
        )


@router.post("/users/{user_id}/characters/{character_id}/image")
async def upload_character_image_endpoint(
    user_id: UUID = Path(..., description="User ID"),
    character_id: UUID = Path(..., description="Character ID"),
    file: UploadFile = File(...),
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Upload an image for a custom character"""
    # Verify user can only upload images for their own characters
    if current_user.user_id != str(user_id):
        return CustomCharacterErrorResponse(
            error="Can only upload images for your own characters", error_code="FORBIDDEN"
        )

    try:
        # Verify character exists and belongs to user
        existing = await db.fetch_one(
            "SELECT id, image_url FROM custom_characters WHERE id = $1 AND user_id = $2",
            character_id,
            user_id,
        )

        if not existing:
            return CustomCharacterErrorResponse(
                error="Character not found", error_code="NOT_FOUND", character_id=character_id
            )

        # Upload new image
        image_url, file_size = await upload_character_image(file, str(user_id), str(character_id))

        # Delete old image if it exists
        if existing["image_url"]:
            await delete_character_image(existing["image_url"])

        # Update database
        await db.execute(
            """UPDATE custom_characters
               SET image_url = $1, image_uploaded_at = CURRENT_TIMESTAMP,
                   image_size_bytes = $2, updated_at = CURRENT_TIMESTAMP
               WHERE id = $3""",
            image_url,
            file_size,
            character_id,
        )

        return {
            "success": True,
            "message": "Image uploaded successfully",
            "image_url": image_url,
            "file_size": file_size,
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"🚨 CHARACTER: Error uploading image for character {character_id}: {e}", flush=True)
        return CustomCharacterErrorResponse(
            error="Failed to upload image",
            error_code="UPLOAD_ERROR",
            character_id=character_id,
        )


@router.get("/users/{user_id}/characters/{character_id}/image")
async def get_character_image_endpoint(
    user_id: UUID = Path(..., description="User ID"),
    character_id: UUID = Path(..., description="Character ID"),
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get image info for a custom character"""
    # Verify user can only access their own character images
    if current_user.user_id != str(user_id):
        return CustomCharacterErrorResponse(
            error="Can only access your own character images", error_code="FORBIDDEN"
        )

    try:
        # Get character with image info
        character = await db.fetch_one(
            "SELECT image_url, image_uploaded_at, image_size_bytes FROM custom_characters WHERE id = $1 AND user_id = $2",
            character_id,
            user_id,
        )

        if not character:
            return CustomCharacterErrorResponse(
                error="Character not found", error_code="NOT_FOUND", character_id=character_id
            )

        if not character["image_url"]:
            return CustomCharacterErrorResponse(
                error="No image found", error_code="NOT_FOUND", character_id=character_id
            )

        return {
            "success": True,
            "image_url": character["image_url"],
            "image_uploaded_at": character["image_uploaded_at"],
            "image_size_bytes": character["image_size_bytes"],
        }

    except Exception as e:
        print(f"🚨 CHARACTER: Error getting image for character {character_id}: {e}", flush=True)
        return CustomCharacterErrorResponse(
            error="Failed to get image info",
            error_code="DATABASE_ERROR",
            character_id=character_id,
        )


@router.patch("/users/{user_id}/characters/{character_id}/image")
async def update_character_image_endpoint(
    user_id: UUID = Path(..., description="User ID"),
    character_id: UUID = Path(..., description="Character ID"),
    file: UploadFile = File(...),
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Update/replace an image for a custom character"""
    # Verify user can only update images for their own characters
    if current_user.user_id != str(user_id):
        return CustomCharacterErrorResponse(
            error="Can only update images for your own characters", error_code="FORBIDDEN"
        )

    try:
        # Verify character exists and belongs to user
        existing = await db.fetch_one(
            "SELECT id, image_url FROM custom_characters WHERE id = $1 AND user_id = $2",
            character_id,
            user_id,
        )

        if not existing:
            return CustomCharacterErrorResponse(
                error="Character not found", error_code="NOT_FOUND", character_id=character_id
            )

        # Upload new image
        image_url, file_size = await upload_character_image(file, str(user_id), str(character_id))

        # Delete old image if it exists
        if existing["image_url"]:
            await delete_character_image(existing["image_url"])

        # Update database
        await db.execute(
            """UPDATE custom_characters
               SET image_url = $1, image_uploaded_at = CURRENT_TIMESTAMP,
                   image_size_bytes = $2, updated_at = CURRENT_TIMESTAMP
               WHERE id = $3""",
            image_url,
            file_size,
            character_id,
        )

        return {
            "success": True,
            "message": "Image updated successfully",
            "image_url": image_url,
            "file_size": file_size,
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"🚨 CHARACTER: Error updating image for character {character_id}: {e}", flush=True)
        return CustomCharacterErrorResponse(
            error="Failed to update image",
            error_code="UPDATE_ERROR",
            character_id=character_id,
        )


@router.delete("/users/{user_id}/characters/{character_id}/image")
async def delete_character_image_endpoint(
    user_id: UUID = Path(..., description="User ID"),
    character_id: UUID = Path(..., description="Character ID"),
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Delete an image for a custom character"""
    # Verify user can only delete images for their own characters
    if current_user.user_id != str(user_id):
        return CustomCharacterErrorResponse(
            error="Can only delete images for your own characters", error_code="FORBIDDEN"
        )

    try:
        # Verify character exists and belongs to user and get image URL
        existing = await db.fetch_one(
            "SELECT image_url FROM custom_characters WHERE id = $1 AND user_id = $2",
            character_id,
            user_id,
        )

        if not existing:
            return CustomCharacterErrorResponse(
                error="Character not found", error_code="NOT_FOUND", character_id=character_id
            )

        if not existing["image_url"]:
            return CustomCharacterErrorResponse(
                error="No image to delete", error_code="NOT_FOUND", character_id=character_id
            )

        # Delete from R2
        deleted = await delete_character_image(existing["image_url"])

        # Update database (remove image reference)
        await db.execute(
            """UPDATE custom_characters
               SET image_url = NULL, image_uploaded_at = NULL,
                   image_size_bytes = NULL, updated_at = CURRENT_TIMESTAMP
               WHERE id = $1""",
            character_id,
        )

        return {
            "success": True,
            "message": "Image deleted successfully",
            "deleted_from_storage": deleted,
        }

    except Exception as e:
        print(f"🚨 CHARACTER: Error deleting image for character {character_id}: {e}", flush=True)
        return CustomCharacterErrorResponse(
            error="Failed to delete image",
            error_code="DELETE_ERROR",
            character_id=character_id,
        )
