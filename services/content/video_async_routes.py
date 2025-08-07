"""Async video generation routes for fairydust content service"""

from datetime import datetime
from typing import Union
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path
from models import (
    UserVideo,
    VideoAnimateRequest,
    VideoGenerateRequest,
    VideoGenerationInfo,
    VideoGenerationType,
    VideoJobCancelResponse,
    VideoJobError,
    VideoJobGenerationInfo,
    VideoJobProgress,
    VideoJobResultFailed,
    VideoJobResultInProgress,
    VideoJobResultResponse,
    VideoJobStartResponse,
    VideoJobStatus,
    VideoJobStatusResponse,
)
from video_job_service import video_job_service

from shared.auth_middleware import TokenData, get_current_user
from shared.database import Database, get_db

# Create router for async video operations
video_async_router = APIRouter(prefix="/videos", tags=["videos-async"])


@video_async_router.post("/generate", response_model=VideoJobStartResponse)
async def start_video_generation(
    request: VideoGenerateRequest,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Start video generation job (returns immediately with job_id)"""

    try:
        print(f"🎬 ASYNC_VIDEO: Starting generation job for user {request.user_id}")
        print(f"   Prompt: {request.prompt[:100]}...")
        print(f"   Duration: {request.duration.value}")
        print(f"   Resolution: {request.resolution.value}")
        print(f"   Has reference: {request.reference_person is not None}")

        # Verify user can only create videos for themselves
        if current_user.user_id != str(request.user_id):
            raise HTTPException(
                status_code=403, detail="Can only create video generation jobs for yourself"
            )

        # Create job
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

        # TODO: Trigger background job processing here
        # For now, we'll add this to the background processing phase

        return VideoJobStartResponse(
            job_id=job_id,
            status=VideoJobStatus.QUEUED,
            estimated_completion_seconds=240,  # 4 minutes for text-to-video
            created_at=datetime.utcnow(),
            generation_type="text_to_video",
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ ASYNC_VIDEO: Error starting generation job: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start video generation: {str(e)}")


@video_async_router.post("/animate", response_model=VideoJobStartResponse)
async def start_video_animation(
    request: VideoAnimateRequest,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Start image-to-video animation job (returns immediately with job_id)"""

    try:
        print(f"🎬 ASYNC_VIDEO: Starting animation job for user {request.user_id}")
        print(f"   Prompt: {request.prompt[:100]}...")
        print(f"   Source image: {request.source_image_id}")
        print(f"   Duration: {request.duration.value}")

        # Verify user can only create videos for themselves
        if current_user.user_id != str(request.user_id):
            raise HTTPException(
                status_code=403, detail="Can only create video animation jobs for yourself"
            )

        # Get source image URL from user's images
        source_image = await db.fetch_one(
            "SELECT url FROM user_images WHERE id = $1 AND user_id = $2",
            request.source_image_id,
            request.user_id,
        )

        if not source_image:
            raise HTTPException(
                status_code=404, detail="Source image not found or doesn't belong to user"
            )

        # Create job
        job_id = await video_job_service.create_job(
            db=db,
            user_id=request.user_id,
            prompt=request.prompt,
            generation_type=VideoGenerationType.IMAGE_TO_VIDEO,
            duration=request.duration,
            resolution=request.resolution,
            aspect_ratio=request.aspect_ratio,
            source_image_url=source_image["url"],
            camera_fixed=request.camera_fixed,
        )

        # TODO: Trigger background job processing here

        return VideoJobStartResponse(
            job_id=job_id,
            status=VideoJobStatus.QUEUED,
            estimated_completion_seconds=180,  # 3 minutes for image-to-video
            created_at=datetime.utcnow(),
            generation_type="image_to_video",
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ ASYNC_VIDEO: Error starting animation job: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start video animation: {str(e)}")


@video_async_router.get("/jobs/{job_id}/status", response_model=VideoJobStatusResponse)
async def get_job_status(
    job_id: UUID = Path(..., description="Job ID"),
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get current status and progress of a video generation job"""

    try:
        job_status = await video_job_service.get_job_status(
            db=db,
            job_id=job_id,
            user_id=UUID(current_user.user_id),
        )

        if not job_status:
            raise HTTPException(status_code=404, detail="Job not found or access denied")

        return VideoJobStatusResponse(
            job_id=job_status["job_id"],
            status=VideoJobStatus(job_status["status"]),
            progress=VideoJobProgress(**job_status["progress"]),
            generation_info=VideoJobGenerationInfo(**job_status["generation_info"]),
            created_at=job_status["created_at"],
            updated_at=job_status["updated_at"],
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ ASYNC_VIDEO: Error getting job status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get job status: {str(e)}")


@video_async_router.get(
    "/jobs/{job_id}/result",
    response_model=Union[VideoJobResultResponse, VideoJobResultInProgress, VideoJobResultFailed],
)
async def get_job_result(
    job_id: UUID = Path(..., description="Job ID"),
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get result of a video generation job (when completed)"""

    try:
        job_result = await video_job_service.get_job_result(
            db=db,
            job_id=job_id,
            user_id=UUID(current_user.user_id),
        )

        if not job_result:
            raise HTTPException(status_code=404, detail="Job not found or access denied")

        status = VideoJobStatus(job_result["status"])

        if status == VideoJobStatus.COMPLETED:
            # Parse video data properly
            video_data = job_result["video"]
            video_metadata = video_data.get("metadata", {})

            user_video = UserVideo(
                id=video_data["id"],
                user_id=UUID(current_user.user_id),
                url=video_data["url"],
                thumbnail_url=video_data["thumbnail_url"],
                prompt=video_metadata.get("prompt", ""),
                duration=video_metadata.get("duration", "short"),
                resolution=video_metadata.get("resolution", "1080p"),
                aspect_ratio=video_metadata.get("aspect_ratio", "16:9"),
                is_favorited=False,
                reference_people=[],
                metadata=video_metadata,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )

            generation_info = VideoGenerationInfo(
                model_used=job_result["generation_info"]["model_used"],
                generation_time_ms=job_result["generation_info"]["total_generation_time_ms"],
                cost_estimate=job_result["generation_info"]["cost_estimate"],
            )

            return VideoJobResultResponse(
                job_id=job_id,
                status=status,
                video=user_video,
                generation_info=generation_info,
            )

        elif status == VideoJobStatus.FAILED:
            return VideoJobResultFailed(
                job_id=job_id,
                status=status,
                error=VideoJobError(**job_result["error"]),
            )

        else:
            # Still in progress
            return VideoJobResultInProgress(
                job_id=job_id,
                status=status,
            )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ ASYNC_VIDEO: Error getting job result: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get job result: {str(e)}")


@video_async_router.delete("/jobs/{job_id}", response_model=VideoJobCancelResponse)
async def cancel_job(
    job_id: UUID = Path(..., description="Job ID"),
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Cancel a video generation job (if not yet completed)"""

    try:
        success = await video_job_service.cancel_job(
            db=db,
            job_id=job_id,
            user_id=UUID(current_user.user_id),
        )

        if not success:
            raise HTTPException(
                status_code=400, detail="Job not found, already completed, or cannot be cancelled"
            )

        return VideoJobCancelResponse(
            job_id=job_id,
            status=VideoJobStatus.CANCELLED,
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ ASYNC_VIDEO: Error cancelling job: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel job: {str(e)}")


@video_async_router.get("/jobs/active")
async def get_active_jobs(
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get all active video generation jobs for the current user"""

    try:
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
