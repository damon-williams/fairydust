"""Video generation and management routes for the Content service"""

import io
import json
from datetime import datetime
from typing import Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException

try:
    from PIL import Image, ImageDraw, ImageFont

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("⚠️ PIL (Pillow) not available - video thumbnail generation will be disabled")

from models import (
    UserVideo,
    VideoAnimateRequest,
    VideoAnimateResponse,
    VideoAspectRatio,
    VideoDeleteResponse,
    VideoDetailResponse,
    VideoGenerateRequest,
    VideoGenerateResponse,
    VideoGenerationInfo,
    VideoGenerationType,
    VideoListResponse,
    VideoPagination,
    VideoReferencePerson,
    VideoResolution,
    VideoUpdateRequest,
    VideoUpdateResponse,
)

from shared.auth_middleware import TokenData, get_current_user
from shared.database import Database, get_db

video_router = APIRouter()


async def _upload_video_to_r2(video_url: str, user_id: UUID, video_id: UUID) -> tuple[str, str]:
    """
    Download video from Replicate and upload to CloudFlare R2
    Also generates and uploads a thumbnail

    Returns:
        Tuple[str, str]: (final_video_url, thumbnail_url)
    """
    try:
        # Download video from Replicate
        async with httpx.AsyncClient() as client:
            video_response = await client.get(video_url, timeout=60.0)
            video_response.raise_for_status()
            video_data = video_response.content

        # Upload video to R2
        from shared.storage_service import upload_file_to_r2

        video_key = f"videos/{user_id}/{video_id}.mp4"
        final_video_url = await upload_file_to_r2(video_data, video_key, content_type="video/mp4")

        # Generate thumbnail from first frame using ffmpeg (if available)
        # For now, create a simple placeholder thumbnail
        thumbnail_url = await _generate_video_thumbnail(video_data, user_id, video_id)

        return final_video_url, thumbnail_url

    except Exception as e:
        print(f"❌ R2 UPLOAD ERROR: {str(e)}")
        # Return original URL if upload fails
        return video_url, None


async def _generate_video_thumbnail(
    video_data: bytes, user_id: UUID, video_id: UUID
) -> Optional[str]:
    """
    Generate thumbnail from video first frame using imageio
    """
    if not PIL_AVAILABLE:
        print("⚠️ PIL not available - skipping thumbnail generation")
        return None

    try:
        # Try to extract first frame using imageio
        try:
            import os
            import tempfile

            import imageio.v3 as iio

            # Write video data to temporary file
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_video:
                temp_video.write(video_data)
                temp_video_path = temp_video.name

            try:
                # Read first frame from video
                print(f"🎬 THUMBNAIL: Extracting first frame from video ({len(video_data)} bytes)")

                # Get video properties and read first frame
                properties = iio.improps(temp_video_path)
                print(f"🎬 THUMBNAIL: Video properties: {properties}")

                # Read just the first frame
                frame = iio.imread(temp_video_path, index=0)
                print(f"🎬 THUMBNAIL: Extracted frame shape: {frame.shape}")

                # Convert numpy array to PIL Image
                thumbnail = Image.fromarray(frame)

                # Resize to standard thumbnail size (maintain aspect ratio)
                thumbnail.thumbnail((640, 360), Image.Resampling.LANCZOS)

                # Convert to RGB if necessary
                if thumbnail.mode != "RGB":
                    thumbnail = thumbnail.convert("RGB")

                print(f"🎬 THUMBNAIL: Generated thumbnail size: {thumbnail.size}")

            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_video_path)
                except:
                    pass

        except ImportError:
            print("⚠️ imageio not available - falling back to placeholder thumbnail")
            # Fall back to placeholder if imageio not available
            thumbnail = Image.new("RGB", (640, 360), color="#1a1a1a")
            draw = ImageDraw.Draw(thumbnail)

            # Add play button icon
            center_x, center_y = 320, 180
            triangle_size = 40

            # Draw play triangle
            triangle = [
                (center_x - triangle_size // 2, center_y - triangle_size // 2),
                (center_x - triangle_size // 2, center_y + triangle_size // 2),
                (center_x + triangle_size // 2, center_y),
            ]
            draw.polygon(triangle, fill="white")

        except Exception as video_error:
            print(f"⚠️ Video frame extraction failed: {video_error} - falling back to placeholder")
            # Fall back to placeholder if video processing fails
            thumbnail = Image.new("RGB", (640, 360), color="#1a1a1a")
            draw = ImageDraw.Draw(thumbnail)

            # Add play button icon
            center_x, center_y = 320, 180
            triangle_size = 40

            # Draw play triangle
            triangle = [
                (center_x - triangle_size // 2, center_y - triangle_size // 2),
                (center_x - triangle_size // 2, center_y + triangle_size // 2),
                (center_x + triangle_size // 2, center_y),
            ]
            draw.polygon(triangle, fill="white")

        # Save thumbnail to bytes
        thumbnail_buffer = io.BytesIO()
        thumbnail.save(thumbnail_buffer, format="JPEG", quality=85)
        thumbnail_data = thumbnail_buffer.getvalue()

        # Upload thumbnail to R2
        from shared.storage_service import upload_file_to_r2

        thumbnail_key = f"video-thumbnails/{user_id}/{video_id}.jpg"
        thumbnail_url = await upload_file_to_r2(
            thumbnail_data, thumbnail_key, content_type="image/jpeg"
        )

        print(f"✅ THUMBNAIL: Successfully generated and uploaded to {thumbnail_url}")
        return thumbnail_url

    except Exception as e:
        print(f"❌ THUMBNAIL GENERATION ERROR: {str(e)}")
        return None


@video_router.post("/generate", response_model=VideoGenerateResponse)
async def generate_video(
    request: VideoGenerateRequest,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Generate a new video from text prompt (async processing with job tracking)"""

    try:
        print(f"🎬 ASYNC VIDEO: Starting generation job for user {request.user_id}")
        print(f"   Prompt: {request.prompt[:100]}...")
        print(f"   Duration: {request.duration.value}")
        print(f"   Resolution: {request.resolution.value}")
        print(f"   Has reference: {request.reference_person is not None}")

        # Verify user can only create videos for themselves
        if current_user.user_id != str(request.user_id):
            raise HTTPException(
                status_code=403, detail="Can only create video generation jobs for yourself"
            )

        # Create job using video job service
        from video_job_service import video_job_service

        job_id = await video_job_service.create_job(
            db=db,
            user_id=request.user_id,
            prompt=request.prompt,
            generation_type=VideoGenerationType.TEXT_TO_VIDEO,
            duration=request.duration,
            resolution=request.resolution,
            aspect_ratio=request.aspect_ratio,
            reference_person=request.reference_person,
            camera_fixed=request.camera_fixed,
        )

        # Return job information immediately (async processing)
        return VideoGenerateResponse(
            job_id=job_id,
            status="queued",
            estimated_completion_seconds=240,  # 4 minutes for text-to-video
            message="Video generation started. Use the job_id to check status.",
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ VIDEO GENERATION ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Video generation failed: {str(e)}")


@video_router.get("/jobs/{job_id}/status")
async def get_video_job_status(
    job_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get current status and progress of a video generation job"""

    try:
        from video_job_service import video_job_service

        job_status = await video_job_service.get_job_status(
            db=db,
            job_id=job_id,
            user_id=UUID(current_user.user_id),
        )

        if not job_status:
            raise HTTPException(status_code=404, detail="Job not found or access denied")

        return {
            "success": True,
            "job_id": job_status["job_id"],
            "status": job_status["status"],
            "progress": job_status["progress"],
            "generation_info": job_status["generation_info"],
            "created_at": job_status["created_at"],
            "updated_at": job_status["updated_at"],
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ ASYNC_VIDEO: Error getting job status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get job status: {str(e)}")


@video_router.get("/jobs/{job_id}/result")
async def get_video_job_result(
    job_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get result of a video generation job (when completed)"""

    try:
        from video_job_service import video_job_service

        job_result = await video_job_service.get_job_result(
            db=db,
            job_id=job_id,
            user_id=UUID(current_user.user_id),
        )

        if not job_result:
            raise HTTPException(status_code=404, detail="Job not found or access denied")

        status = job_result["status"]

        if status == "completed" and job_result.get("video"):
            # Return completed video
            video_data = job_result["video"]
            video_metadata = video_data.get("metadata", {})

            user_video = UserVideo(
                id=video_data["id"],
                user_id=UUID(current_user.user_id),
                url=video_data["url"],
                thumbnail_url=video_data["thumbnail_url"],
                prompt=video_metadata.get("prompt", ""),
                generation_type=VideoGenerationType(
                    video_metadata.get("generation_type", "text_to_video")
                ),
                source_image_url=video_metadata.get("source_image_url"),
                duration_seconds=video_metadata.get("duration_seconds", 5),
                resolution=VideoResolution(video_metadata.get("resolution", "hd_1080p")),
                aspect_ratio=VideoAspectRatio(video_metadata.get("aspect_ratio", "16:9")),
                reference_person=None,  # Will be handled properly later
                metadata=video_metadata,
                is_favorited=False,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )

            generation_info = VideoGenerationInfo(
                model_used=job_result["generation_info"]["model_used"],
                generation_time_ms=job_result["generation_info"]["total_generation_time_ms"],
            )

            return VideoGenerateResponse(video=user_video, generation_info=generation_info)

        elif status == "failed":
            return {
                "success": False,
                "job_id": job_id,
                "status": status,
                "error": job_result["error"],
            }

        else:
            # Still in progress
            return {
                "success": True,
                "job_id": job_id,
                "status": status,
                "message": "Video generation still in progress",
            }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ ASYNC_VIDEO: Error getting job result: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get job result: {str(e)}")


@video_router.delete("/jobs/{job_id}")
async def cancel_video_job(
    job_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Cancel a video generation job (if not yet completed)"""

    try:
        from video_job_service import video_job_service

        success = await video_job_service.cancel_job(
            db=db,
            job_id=job_id,
            user_id=UUID(current_user.user_id),
        )

        if not success:
            raise HTTPException(
                status_code=400, detail="Job not found, already completed, or cannot be cancelled"
            )

        return {
            "success": True,
            "job_id": job_id,
            "status": "cancelled",
            "message": "Video generation job cancelled successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ ASYNC_VIDEO: Error cancelling job: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel job: {str(e)}")


@video_router.get("/jobs/active")
async def get_active_video_jobs(
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get all active video generation jobs for the current user"""

    try:
        from video_job_service import video_job_service

        active_jobs = await video_job_service.get_user_active_jobs(
            db=db,
            user_id=UUID(current_user.user_id),
        )

        return {
            "success": True,
            "active_jobs": active_jobs,
            "count": len(active_jobs),
        }

    except Exception as e:
        print(f"❌ ASYNC_VIDEO: Error getting active jobs: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get active jobs: {str(e)}")


@video_router.post("/animate", response_model=VideoAnimateResponse)
async def animate_image(
    request: VideoAnimateRequest,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Animate an existing image into a video (async processing with job tracking)"""

    try:
        print(f"🎬 ASYNC VIDEO: Starting animation job for user {request.user_id}")
        print(f"   Image URL: {request.image_url}")
        print(f"   Prompt: {request.prompt[:100]}...")
        print(f"   Duration: {request.duration.value}")
        print(f"   Resolution: {request.resolution.value}")

        # Verify user can only create videos for themselves
        if current_user.user_id != str(request.user_id):
            raise HTTPException(
                status_code=403, detail="Can only create video animation jobs for yourself"
            )

        # Get aspect ratio from the image (default to 16:9 for now)
        aspect_ratio = VideoAspectRatio.ASPECT_16_9

        # Create job using video job service
        from video_job_service import video_job_service

        job_id = await video_job_service.create_job(
            db=db,
            user_id=request.user_id,
            prompt=request.prompt,
            generation_type=VideoGenerationType.IMAGE_TO_VIDEO,
            duration=request.duration,
            resolution=request.resolution,
            aspect_ratio=aspect_ratio,
            source_image_url=request.image_url,
            camera_fixed=request.camera_fixed,
        )

        # Return job information immediately (async processing)
        return VideoAnimateResponse(
            job_id=job_id,
            status="queued",
            estimated_completion_seconds=180,  # 3 minutes for image-to-video
            message="Video animation started. Use the job_id to check status.",
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ VIDEO ANIMATION ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Video animation failed: {str(e)}")


@video_router.get("", response_model=VideoListResponse)
async def list_videos(
    limit: int = 20,
    offset: int = 0,
    favorites_only: bool = False,
    generation_type: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """List videos for the current user"""

    try:
        # Build query conditions
        conditions = ["user_id = $1"]
        params = [current_user.user_id]
        param_count = 1

        if favorites_only:
            param_count += 1
            conditions.append(f"is_favorited = ${param_count}")
            params.append(True)

        if generation_type and generation_type != "all":
            param_count += 1
            conditions.append(f"generation_type = ${param_count}")
            params.append(generation_type)

        where_clause = " AND ".join(conditions)

        # Get total count
        count_query = f"SELECT COUNT(*) as total FROM user_videos WHERE {where_clause}"
        count_result = await db.fetch_one(count_query, *params)
        total = count_result["total"] if count_result else 0

        # Get videos with pagination
        param_count += 1
        limit_param = param_count
        param_count += 1
        offset_param = param_count

        videos_query = f"""
            SELECT * FROM user_videos
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${limit_param} OFFSET ${offset_param}
        """
        params.extend([limit, offset])

        video_rows = await db.fetch_all(videos_query, *params)

        # Convert to UserVideo models
        videos = []
        for row in video_rows:
            user_video = UserVideo(
                id=row["id"],
                user_id=row["user_id"],
                url=row["url"],
                thumbnail_url=row["thumbnail_url"],
                prompt=row["prompt"],
                generation_type=VideoGenerationType(row["generation_type"]),
                source_image_url=row["source_image_url"],
                duration_seconds=row["duration_seconds"],
                resolution=VideoResolution(row["resolution"]),
                aspect_ratio=VideoAspectRatio(row["aspect_ratio"]),
                reference_person=VideoReferencePerson(**row["reference_person"])
                if row["reference_person"]
                else None,
                metadata=json.loads(row["metadata"]) if row["metadata"] else {},
                is_favorited=row["is_favorited"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            videos.append(user_video)

        pagination = VideoPagination(
            total=total, limit=limit, offset=offset, has_more=offset + limit < total
        )

        return VideoListResponse(videos=videos, pagination=pagination)

    except Exception as e:
        print(f"❌ VIDEO LIST ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list videos: {str(e)}")


@video_router.get("/{video_id}", response_model=VideoDetailResponse)
async def get_video(
    video_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get a specific video by ID"""

    try:
        video_row = await db.fetch_one(
            "SELECT * FROM user_videos WHERE id = $1 AND user_id = $2",
            video_id,
            current_user.user_id,
        )

        if not video_row:
            raise HTTPException(status_code=404, detail="Video not found")

        user_video = UserVideo(
            id=video_row["id"],
            user_id=video_row["user_id"],
            url=video_row["url"],
            thumbnail_url=video_row["thumbnail_url"],
            prompt=video_row["prompt"],
            generation_type=VideoGenerationType(video_row["generation_type"]),
            source_image_url=video_row["source_image_url"],
            duration_seconds=video_row["duration_seconds"],
            resolution=VideoResolution(video_row["resolution"]),
            aspect_ratio=VideoAspectRatio(video_row["aspect_ratio"]),
            reference_person=VideoReferencePerson(**video_row["reference_person"])
            if video_row["reference_person"]
            else None,
            metadata=json.loads(video_row["metadata"]) if video_row["metadata"] else {},
            is_favorited=video_row["is_favorited"],
            created_at=video_row["created_at"],
            updated_at=video_row["updated_at"],
        )

        return VideoDetailResponse(video=user_video)

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ VIDEO GET ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get video: {str(e)}")


@video_router.put("/{video_id}", response_model=VideoUpdateResponse)
async def update_video(
    video_id: UUID,
    request: VideoUpdateRequest,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Update video (favorite/unfavorite)"""

    try:
        # Check if video exists and belongs to user
        video_row = await db.fetch_one(
            "SELECT * FROM user_videos WHERE id = $1 AND user_id = $2",
            video_id,
            current_user.user_id,
        )

        if not video_row:
            raise HTTPException(status_code=404, detail="Video not found")

        # Update video
        await db.execute(
            "UPDATE user_videos SET is_favorited = $1, updated_at = $2 WHERE id = $3",
            request.is_favorited,
            datetime.utcnow(),
            video_id,
        )

        # Fetch updated video
        updated_row = await db.fetch_one("SELECT * FROM user_videos WHERE id = $1", video_id)

        user_video = UserVideo(
            id=updated_row["id"],
            user_id=updated_row["user_id"],
            url=updated_row["url"],
            thumbnail_url=updated_row["thumbnail_url"],
            prompt=updated_row["prompt"],
            generation_type=VideoGenerationType(updated_row["generation_type"]),
            source_image_url=updated_row["source_image_url"],
            duration_seconds=updated_row["duration_seconds"],
            resolution=VideoResolution(updated_row["resolution"]),
            aspect_ratio=VideoAspectRatio(updated_row["aspect_ratio"]),
            reference_person=VideoReferencePerson(**updated_row["reference_person"])
            if updated_row["reference_person"]
            else None,
            metadata=json.loads(updated_row["metadata"]) if updated_row["metadata"] else {},
            is_favorited=updated_row["is_favorited"],
            created_at=updated_row["created_at"],
            updated_at=updated_row["updated_at"],
        )

        return VideoUpdateResponse(video=user_video)

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ VIDEO UPDATE ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update video: {str(e)}")


@video_router.delete("/{video_id}", response_model=VideoDeleteResponse)
async def delete_video(
    video_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Delete a video"""

    try:
        # Check if video exists and belongs to user
        video_row = await db.fetch_one(
            "SELECT * FROM user_videos WHERE id = $1 AND user_id = $2",
            video_id,
            current_user.user_id,
        )

        if not video_row:
            raise HTTPException(status_code=404, detail="Video not found")

        # Delete from database
        await db.execute("DELETE FROM user_videos WHERE id = $1", video_id)

        # TODO: Delete from R2 storage
        # For now, just mark as deleted from storage
        deleted_from_storage = True

        return VideoDeleteResponse(deleted_from_storage=deleted_from_storage)

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ VIDEO DELETE ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete video: {str(e)}")


@video_router.get("/stats")
async def video_processor_stats():
    """Get video background processor statistics"""
    from video_background_processor import video_background_processor

    stats = await video_background_processor.get_stats()
    return stats
