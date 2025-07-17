"""Image generation app routes for fairydust content service"""

import json
import os
from datetime import datetime
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer

from image_generation_service import image_generation_service
from image_storage_service import image_storage_service
from models import (
    ImageDeleteResponse,
    ImageDetailResponse,
    ImageErrorResponse,
    ImageGenerateRequest,
    ImageGenerateResponse,
    ImageGenerationInfo,
    ImageListRequest,
    ImageListResponse,
    ImagePagination,
    ImagePersonReference,
    ImageRegenerateRequest,
    ImageRegenerateResponse,
    ImageUpdateRequest,
    ImageUpdateResponse,
    UserImage,
)
from shared.database import Database, get_db

security = HTTPBearer()

# Create router
image_router = APIRouter(prefix="/images", tags=["images"])


async def validate_user_people(db: Database, user_id: str, person_ids: list[str]) -> dict:
    """Validate that all person IDs belong to the user and get their names"""
    if not person_ids:
        return {}
    
    # Get people from identity service
    identity_base_url = _get_identity_service_url()
    service_token = os.getenv("SERVICE_JWT_TOKEN")
    
    if not service_token:
        raise HTTPException(
            status_code=500,
            detail="SERVICE_JWT_TOKEN not configured for inter-service authentication"
        )
    
    people_map = {}
    
    # Separate user avatar references from actual people
    people_to_validate = []
    for person_id in person_ids:
        if person_id == user_id:
            # This is the user themselves - get their name
            async with httpx.AsyncClient() as client:
                user_response = await client.get(
                    f"{identity_base_url}/users/me",
                    headers={"Authorization": f"Bearer {service_token}"},
                    timeout=10.0
                )
                if user_response.status_code == 200:
                    user_data = user_response.json()
                    people_map[person_id] = user_data.get("first_name", "Me")
                else:
                    people_map[person_id] = "Me"
        else:
            people_to_validate.append(person_id)
    
    # Validate actual people in their life
    if people_to_validate:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{identity_base_url}/users/{user_id}/people",
                headers={"Authorization": f"Bearer {service_token}"},
                timeout=10.0
            )
            if response.status_code != 200:
                raise HTTPException(
                    status_code=400,
                    detail="Failed to validate people references"
                )
            
            people_data = response.json()
            people_data_map = {str(person["id"]): person["name"] for person in people_data}
            
            # Validate all people IDs exist
            for person_id in people_to_validate:
                if person_id not in people_data_map:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Person {person_id} not found or does not belong to user"
                    )
            
            people_map.update(people_data_map)
        
    return people_map


def _get_identity_service_url() -> str:
    """Get identity service URL based on environment"""
    environment = os.getenv('ENVIRONMENT', 'staging')
    base_url_suffix = 'production' if environment == 'production' else 'staging'
    return f"https://fairydust-identity-{base_url_suffix}.up.railway.app"


@image_router.post("/generate", response_model=ImageGenerateResponse)
async def generate_image(
    request: ImageGenerateRequest,
    db: Database = Depends(get_db)
):
    """Generate a new AI image from text prompt with optional reference people"""
    
    try:
        # Validate reference people belong to user
        people_map = {}
        if request.reference_people:
            person_ids = [str(person.person_id) for person in request.reference_people]
            people_map = await validate_user_people(db, str(request.user_id), person_ids)
        
        
        # Generate image
        image_url, generation_metadata = await image_generation_service.generate_image(
            request.prompt,
            request.style,
            request.image_size,
            request.reference_people
        )
        
        # Store image in R2
        image_id = str(uuid4())
        stored_url, file_size, dimensions = await image_storage_service.store_generated_image(
            image_url,
            str(request.user_id),
            image_id
        )
        
        # Prepare reference people for database
        reference_people_data = []
        for person in request.reference_people:
            reference_people_data.append({
                "person_id": str(person.person_id),
                "person_name": people_map.get(str(person.person_id), "Unknown"),
                "description": person.description
            })
        
        # Prepare metadata
        full_metadata = {
            **generation_metadata,
            "file_size_bytes": file_size,
            "dimensions": dimensions,
            "is_regeneration": False
        }
        
        # Store in database
        image_record = await db.fetch_one(
            """
            INSERT INTO user_images (
                id, user_id, url, prompt, style, image_size, is_favorited,
                reference_people, metadata, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING *
            """,
            image_id,
            str(request.user_id),
            stored_url,
            request.prompt,
            request.style.value,
            request.image_size.value,
            False,  # is_favorited defaults to False
            json.dumps(reference_people_data),  # Convert to JSON string for JSONB
            json.dumps(full_metadata)  # Convert to JSON string for JSONB
        )
        
        # Create response - Parse JSONB fields back to Python objects
        image_data = dict(image_record)
        image_data["reference_people"] = json.loads(image_record["reference_people"])
        image_data["metadata"] = json.loads(image_record["metadata"])
        
        user_image = UserImage(**image_data)
        generation_info = ImageGenerationInfo(
            model_used=generation_metadata["model_used"],
            generation_time_ms=generation_metadata["generation_time_ms"],
            cost_estimate="$0.025"  # FLUX cost estimate - actual cost handled by apps service
        )
        
        return ImageGenerateResponse(
            image=user_image,
            generation_info=generation_info
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image generation failed: {str(e)}")


@image_router.post("/{image_id}/regenerate", response_model=ImageRegenerateResponse)
async def regenerate_image(
    image_id: str,
    request: ImageRegenerateRequest,
    db: Database = Depends(get_db)
):
    """Regenerate existing image with user feedback"""
    
    try:
        # Get original image
        original_image = await db.fetch_one(
            "SELECT * FROM user_images WHERE id = $1 AND user_id = $2",
            image_id,
            str(request.user_id)
        )
        
        if not original_image:
            raise HTTPException(status_code=404, detail="Original image not found")
        
        # Prepare reference people if keeping them
        reference_people = []
        if request.keep_people and original_image["reference_people"]:
            # Parse JSONB string to Python object if needed
            ref_people_data = original_image["reference_people"]
            if isinstance(ref_people_data, str):
                ref_people_data = json.loads(ref_people_data)
            
            for person_ref in ref_people_data:
                reference_people.append({
                    "person_id": person_ref["person_id"],
                    "photo_url": "placeholder",  # Will be validated separately
                    "description": person_ref["description"]
                })
        
        
        # Build enhanced prompt with feedback
        enhanced_prompt = f"{original_image['prompt']}. {request.feedback}"
        
        # Apply style adjustments
        style = original_image["style"]
        if request.style_adjustments and "style" in request.style_adjustments:
            style = request.style_adjustments["style"]
        
        # Generate new image
        image_url, generation_metadata = await image_generation_service.generate_image(
            enhanced_prompt,
            style,
            original_image["image_size"],
            reference_people
        )
        
        # Store new image
        new_image_id = str(uuid4())
        stored_url, file_size, dimensions = await image_storage_service.store_generated_image(
            image_url,
            str(request.user_id),
            new_image_id
        )
        
        # Prepare metadata
        full_metadata = {
            **generation_metadata,
            "file_size_bytes": file_size,
            "dimensions": dimensions,
            "is_regeneration": True,
            "original_image_id": image_id,
            "regeneration_feedback": request.feedback
        }
        
        # Store in database
        new_image_record = await db.fetch_one(
            """
            INSERT INTO user_images (
                id, user_id, url, prompt, style, image_size, is_favorited,
                reference_people, metadata, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING *
            """,
            new_image_id,
            str(request.user_id),
            stored_url,
            enhanced_prompt,
            style,
            original_image["image_size"],
            False,  # is_favorited defaults to False
            json.dumps(original_image["reference_people"] if request.keep_people else []),  # Convert to JSON string
            json.dumps(full_metadata)  # Convert to JSON string for JSONB
        )
        
        # Create response - Parse JSONB fields back to Python objects
        image_data = dict(new_image_record)
        image_data["reference_people"] = json.loads(new_image_record["reference_people"])
        image_data["metadata"] = json.loads(new_image_record["metadata"])
        
        user_image = UserImage(**image_data)
        generation_info = ImageGenerationInfo(
            model_used=generation_metadata["model_used"],
            generation_time_ms=generation_metadata["generation_time_ms"],
            cost_estimate="$0.025"  # FLUX cost estimate - actual cost handled by apps service
        )
        
        return ImageRegenerateResponse(
            image=user_image,
            generation_info=generation_info
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image regeneration failed: {str(e)}")


@image_router.get("/users/{user_id}", response_model=ImageListResponse)
async def get_user_images(
    user_id: str,
    limit: int = 20,
    offset: int = 0,
    favorites_only: bool = False,
    style: str = None,
    has_people: bool = None,
    db: Database = Depends(get_db)
):
    """Get user's generated images with pagination"""
    
    try:
        # Build query conditions
        conditions = ["user_id = $1"]
        params = [user_id]
        param_count = 2
        
        if favorites_only:
            conditions.append("is_favorited = true")
        
        if style:
            conditions.append(f"style = ${param_count}")
            params.append(style)
            param_count += 1
        
        if has_people is not None:
            if has_people:
                conditions.append("jsonb_array_length(reference_people) > 0")
            else:
                conditions.append("jsonb_array_length(reference_people) = 0")
        
        where_clause = " AND ".join(conditions)
        
        # Get total count
        count_query = f"SELECT COUNT(*) as total FROM user_images WHERE {where_clause}"
        total_result = await db.fetch_one(count_query, *params)
        total = total_result["total"]
        
        # Get images
        images_query = f"""
            SELECT id, user_id, url, prompt, style, image_size, is_favorited,
                   reference_people, jsonb_array_length(reference_people) as reference_people_count,
                   metadata, created_at, updated_at
            FROM user_images 
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_count} OFFSET ${param_count + 1}
        """
        params.extend([limit, offset])
        
        images = await db.fetch_all(images_query, *params)
        
        # Convert to response format
        user_images = []
        for image in images:
            try:
                # Build simplified image data for list view
                image_data = dict(image)
                image_data["has_reference_people"] = image_data["reference_people_count"] > 0
                
                # Parse JSONB fields back to Python objects
                image_data["reference_people"] = json.loads(image["reference_people"])
                image_data["metadata"] = json.loads(image["metadata"])
                
                user_images.append(UserImage(**image_data))
            except Exception as e:
                print(f"❌ Failed to process image {image.get('id')}: {e}")
                print(f"   Image data: {image}")
                raise
        
        pagination = ImagePagination(
            total=total,
            limit=limit,
            offset=offset,
            has_more=offset + limit < total
        )
        
        return ImageListResponse(
            images=user_images,
            pagination=pagination
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch images: {str(e)}")


@image_router.get("/{image_id}", response_model=ImageDetailResponse)
async def get_image_detail(
    image_id: str,
    db: Database = Depends(get_db)
):
    """Get detailed image information"""
    
    try:
        image = await db.fetch_one(
            "SELECT * FROM user_images WHERE id = $1",
            image_id
        )
        
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")
        
        # Parse JSONB fields back to Python objects
        image_data = dict(image)
        image_data["reference_people"] = json.loads(image["reference_people"])
        image_data["metadata"] = json.loads(image["metadata"])
        
        user_image = UserImage(**image_data)
        return ImageDetailResponse(image=user_image)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch image: {str(e)}")


@image_router.patch("/{image_id}", response_model=ImageUpdateResponse)
async def update_image(
    image_id: str,
    request: ImageUpdateRequest,
    db: Database = Depends(get_db)
):
    """Update image metadata (favoriting)"""
    
    try:
        # Update image
        updated_image = await db.fetch_one(
            """
            UPDATE user_images 
            SET is_favorited = $1, updated_at = CURRENT_TIMESTAMP
            WHERE id = $2
            RETURNING *
            """,
            request.is_favorited,
            image_id
        )
        
        if not updated_image:
            raise HTTPException(status_code=404, detail="Image not found")
        
        # Parse JSONB fields back to Python objects
        image_data = dict(updated_image)
        image_data["reference_people"] = json.loads(updated_image["reference_people"])
        image_data["metadata"] = json.loads(updated_image["metadata"])
        
        user_image = UserImage(**image_data)
        return ImageUpdateResponse(image=user_image)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update image: {str(e)}")


@image_router.delete("/{image_id}", response_model=ImageDeleteResponse)
async def delete_image(
    image_id: str,
    db: Database = Depends(get_db)
):
    """Delete generated image"""
    
    try:
        # Get image to delete
        image = await db.fetch_one(
            "SELECT url FROM user_images WHERE id = $1",
            image_id
        )
        
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")
        
        # Delete from storage
        deleted_from_storage = await image_storage_service.delete_generated_image(image["url"])
        
        # Delete from database
        await db.execute("DELETE FROM user_images WHERE id = $1", image_id)
        
        return ImageDeleteResponse(
            deleted_from_storage=deleted_from_storage
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete image: {str(e)}")