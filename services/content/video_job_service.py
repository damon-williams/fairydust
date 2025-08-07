"""Video generation job management service for async video processing"""

import json
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import UUID

from models import (
    VideoAspectRatio,
    VideoDuration,
    VideoGenerationType,
    VideoJobStatus,
    VideoReferencePerson,
    VideoResolution,
)

from shared.database import Database


class VideoJobService:
    """Service for managing async video generation jobs"""

    def __init__(self):
        self.status_to_progress = {
            "queued": 5,
            "starting": 15,
            "processing": 65,
            "succeeded": 100,
            "failed": 0,
            "cancelled": 0,
        }

    async def create_job(
        self,
        db: Database,
        user_id: UUID,
        prompt: str,
        generation_type: VideoGenerationType,
        duration: VideoDuration,
        resolution: VideoResolution,
        aspect_ratio: VideoAspectRatio,
        reference_person: Optional[VideoReferencePerson] = None,
        source_image_url: Optional[str] = None,
        camera_fixed: bool = False,
    ) -> UUID:
        """Create a new video generation job"""

        # Prepare input parameters
        input_params = {
            "prompt": prompt,
            "duration": duration.value,
            "resolution": resolution.value,
            "aspect_ratio": aspect_ratio.value,
            "camera_fixed": camera_fixed,
            "generation_type": generation_type.value,
        }

        if reference_person:
            input_params["reference_person"] = {
                "person_id": str(reference_person.person_id),
                "photo_url": reference_person.photo_url,
                "description": reference_person.description,
            }

        if source_image_url:
            input_params["source_image_url"] = source_image_url

        # Estimate completion time based on generation type
        estimated_seconds = 240 if generation_type == VideoGenerationType.TEXT_TO_VIDEO else 180

        # Insert job into database
        job_id = await db.fetch_val(
            """
            INSERT INTO video_generation_jobs (
                user_id, status, generation_type, input_parameters, estimated_completion_seconds
            )
            VALUES ($1, $2, $3, $4::jsonb, $5)
            RETURNING id
            """,
            user_id,
            VideoJobStatus.QUEUED.value,
            generation_type.value,
            json.dumps(input_params),
            estimated_seconds,
        )

        print(f"✅ VIDEO_JOB: Created job {job_id} for user {user_id}")
        return job_id

    async def get_job_status(
        self, db: Database, job_id: UUID, user_id: UUID
    ) -> Optional[dict[str, Any]]:
        """Get current status of a video generation job"""

        job = await db.fetch_one(
            """
            SELECT id, user_id, status, generation_type, replicate_prediction_id, replicate_status,
                   estimated_completion_seconds, created_at, updated_at, error_code, error_message
            FROM video_generation_jobs
            WHERE id = $1 AND user_id = $2
            """,
            job_id,
            user_id,
        )

        if not job:
            return None

        # Calculate progress based on status
        elapsed_seconds = int((datetime.utcnow() - job["created_at"]).total_seconds())
        replicate_status = job["replicate_status"] or "queued"
        estimated_percent = self.status_to_progress.get(replicate_status, 5)

        # Calculate remaining time estimate
        estimated_remaining = None
        if job["status"] in ["queued", "starting", "processing"]:
            total_estimate = job["estimated_completion_seconds"]
            progress_ratio = estimated_percent / 100
            if progress_ratio > 0:
                estimated_total_time = elapsed_seconds / progress_ratio
                estimated_remaining = max(0, int(estimated_total_time - elapsed_seconds))

        return {
            "job_id": job["id"],
            "status": job["status"],
            "progress": {
                "phase": replicate_status,
                "estimated_percent": estimated_percent,
                "elapsed_seconds": elapsed_seconds,
                "estimated_remaining_seconds": estimated_remaining,
            },
            "generation_info": {
                "generation_type": job["generation_type"],
                "model_used": None,  # Will be updated when job starts
                "replicate_prediction_id": job["replicate_prediction_id"],
            },
            "created_at": job["created_at"],
            "updated_at": job["updated_at"],
            "error": {
                "code": job["error_code"],
                "message": job["error_message"],
            }
            if job["error_code"]
            else None,
        }

    async def get_job_result(
        self, db: Database, job_id: UUID, user_id: UUID
    ) -> Optional[dict[str, Any]]:
        """Get result of a completed video generation job"""

        job = await db.fetch_one(
            """
            SELECT vj.id, vj.user_id, vj.status, vj.generation_type, vj.video_id,
                   vj.video_url, vj.generation_metadata, vj.error_code, vj.error_message, vj.error_details,
                   uv.id as video_id, uv.url, uv.thumbnail_url, uv.metadata as video_metadata
            FROM video_generation_jobs vj
            LEFT JOIN user_videos uv ON vj.video_id = uv.id
            WHERE vj.id = $1 AND vj.user_id = $2
            """,
            job_id,
            user_id,
        )

        if not job:
            return None

        result = {
            "job_id": job["id"],
            "status": job["status"],
        }

        if job["status"] == "completed" and job["video_id"]:
            # Parse video metadata
            video_metadata = json.loads(job["video_metadata"]) if job["video_metadata"] else {}

            result["video"] = {
                "id": job["video_id"],
                "url": job["url"],
                "thumbnail_url": job["thumbnail_url"],
                "metadata": video_metadata,
            }

            # Parse generation metadata
            gen_metadata = (
                json.loads(job["generation_metadata"]) if job["generation_metadata"] else {}
            )
            result["generation_info"] = {
                "model_used": gen_metadata.get("model_used"),
                "total_generation_time_ms": gen_metadata.get("generation_time_ms"),
                "cost_estimate": f"${gen_metadata.get('cost_usd', 0.15):.3f}",
                "generation_type": job["generation_type"],
            }

        elif job["status"] == "failed":
            error_details = json.loads(job["error_details"]) if job["error_details"] else {}
            result["error"] = {
                "code": job["error_code"] or "UNKNOWN_ERROR",
                "message": job["error_message"] or "Video generation failed",
                "details": error_details.get("details"),
            }

        return result

    async def update_job_status(
        self,
        db: Database,
        job_id: UUID,
        status: str,
        replicate_prediction_id: Optional[str] = None,
        replicate_status: Optional[str] = None,
        video_id: Optional[UUID] = None,
        video_url: Optional[str] = None,
        generation_metadata: Optional[dict] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        error_details: Optional[dict] = None,
    ) -> bool:
        """Update job status and related fields"""

        # Build dynamic update query
        update_fields = ["status = $2", "updated_at = NOW()"]
        params = [job_id, status]
        param_count = 2

        if replicate_prediction_id:
            param_count += 1
            update_fields.append(f"replicate_prediction_id = ${param_count}")
            params.append(replicate_prediction_id)

        if replicate_status:
            param_count += 1
            update_fields.append(f"replicate_status = ${param_count}")
            params.append(replicate_status)

        if video_id:
            param_count += 1
            update_fields.append(f"video_id = ${param_count}")
            params.append(video_id)

        if video_url:
            param_count += 1
            update_fields.append(f"video_url = ${param_count}")
            params.append(video_url)

        if generation_metadata:
            param_count += 1
            update_fields.append(f"generation_metadata = ${param_count}::jsonb")
            params.append(json.dumps(generation_metadata))

        if error_code:
            param_count += 1
            update_fields.append(f"error_code = ${param_count}")
            params.append(error_code)

        if error_message:
            param_count += 1
            update_fields.append(f"error_message = ${param_count}")
            params.append(error_message)

        if error_details:
            param_count += 1
            update_fields.append(f"error_details = ${param_count}::jsonb")
            params.append(json.dumps(error_details))

        if status == "completed":
            update_fields.append("completed_at = NOW()")

        query = f"""
            UPDATE video_generation_jobs
            SET {', '.join(update_fields)}
            WHERE id = $1
            RETURNING id
        """

        result = await db.fetch_one(query, *params)
        return result is not None

    async def cancel_job(self, db: Database, job_id: UUID, user_id: UUID) -> bool:
        """Cancel a video generation job (if not yet completed)"""

        result = await db.fetch_one(
            """
            UPDATE video_generation_jobs
            SET status = $3, updated_at = NOW()
            WHERE id = $1 AND user_id = $2 AND status NOT IN ('completed', 'failed', 'cancelled')
            RETURNING id
            """,
            job_id,
            user_id,
            VideoJobStatus.CANCELLED.value,
        )

        if result:
            print(f"✅ VIDEO_JOB: Cancelled job {job_id}")
            return True
        return False

    async def cleanup_old_jobs(self, db: Database, days_old: int = 7) -> int:
        """Clean up old completed/failed jobs"""

        cutoff_date = datetime.utcnow() - timedelta(days=days_old)

        result = await db.execute(
            """
            DELETE FROM video_generation_jobs
            WHERE status IN ('completed', 'failed', 'cancelled')
            AND created_at < $1
            """,
            cutoff_date,
        )

        # Parse the result string to get count (e.g., "DELETE 5")
        deleted_count = int(result.split()[1]) if result and result.startswith("DELETE") else 0

        if deleted_count > 0:
            print(f"✅ VIDEO_JOB: Cleaned up {deleted_count} old jobs")

        return deleted_count

    async def get_user_active_jobs(self, db: Database, user_id: UUID) -> list[dict[str, Any]]:
        """Get all active (non-completed) jobs for a user"""

        jobs = await db.fetch_all(
            """
            SELECT id, status, generation_type, created_at, estimated_completion_seconds
            FROM video_generation_jobs
            WHERE user_id = $1 AND status NOT IN ('completed', 'failed', 'cancelled')
            ORDER BY created_at DESC
            """,
            user_id,
        )

        active_jobs = []
        for job in jobs:
            elapsed_seconds = int((datetime.utcnow() - job["created_at"]).total_seconds())
            active_jobs.append(
                {
                    "job_id": job["id"],
                    "status": job["status"],
                    "generation_type": job["generation_type"],
                    "elapsed_seconds": elapsed_seconds,
                    "estimated_completion_seconds": job["estimated_completion_seconds"],
                    "created_at": job["created_at"],
                }
            )

        return active_jobs


# Global instance
video_job_service = VideoJobService()
