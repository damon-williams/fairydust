"""Background video generation processor for async job processing"""

import asyncio
import json
import time
from typing import Any
from uuid import UUID

from models import (
    VideoAspectRatio,
    VideoDuration,
    VideoGenerationType,
    VideoJobStatus,
    VideoReferencePerson,
    VideoResolution,
)
from video_generation_service import video_generation_service
from video_job_service import video_job_service
from video_routes import _upload_video_to_r2

from shared.database import get_db


class VideoBackgroundProcessor:
    """Processes video generation jobs in the background"""

    def __init__(self):
        self.is_running = False
        self.max_concurrent_jobs = 3  # Limit concurrent video generations
        self.active_jobs = set()
        self.poll_interval = 5  # seconds

    async def start(self):
        """Start the background processor"""
        if self.is_running:
            return

        self.is_running = True
        print("🎬 BACKGROUND_PROCESSOR: Starting video job processor")

        try:
            while self.is_running:
                await self._process_queued_jobs()
                await asyncio.sleep(self.poll_interval)
        except Exception as e:
            print(f"❌ BACKGROUND_PROCESSOR: Fatal error: {str(e)}")
        finally:
            self.is_running = False
            print("🎬 BACKGROUND_PROCESSOR: Stopped")

    async def stop(self):
        """Stop the background processor"""
        print("🎬 BACKGROUND_PROCESSOR: Stopping...")
        self.is_running = False

        # Wait for active jobs to complete or timeout
        timeout = 30  # seconds
        start_time = time.time()

        while self.active_jobs and (time.time() - start_time) < timeout:
            print(
                f"🎬 BACKGROUND_PROCESSOR: Waiting for {len(self.active_jobs)} active jobs to complete..."
            )
            await asyncio.sleep(2)

        if self.active_jobs:
            print(
                f"⚠️ BACKGROUND_PROCESSOR: Force stopping with {len(self.active_jobs)} active jobs"
            )

    async def _process_queued_jobs(self):
        """Process queued video generation jobs"""
        if len(self.active_jobs) >= self.max_concurrent_jobs:
            return  # Too many active jobs

        try:
            db = await get_db()

            # Get oldest queued job
            job = await db.fetch_one(
                """
                SELECT id, user_id, generation_type, input_parameters
                FROM video_generation_jobs
                WHERE status = 'queued'
                ORDER BY created_at ASC
                LIMIT 1
                """
            )

            if not job:
                return  # No queued jobs

            job_id = job["id"]

            # Mark job as starting to prevent duplicate processing
            updated = await video_job_service.update_job_status(
                db=db,
                job_id=job_id,
                status=VideoJobStatus.STARTING.value,
            )

            if not updated:
                return  # Job was already taken

            print(f"🎬 BACKGROUND_PROCESSOR: Starting job {job_id}")

            # Add to active jobs and process
            self.active_jobs.add(job_id)

            # Process job asynchronously (don't await - let it run in background)
            asyncio.create_task(self._process_single_job(job))

        except Exception as e:
            print(f"❌ BACKGROUND_PROCESSOR: Error processing queued jobs: {str(e)}")

    async def _process_single_job(self, job_data: dict[str, Any]):
        """Process a single video generation job"""
        job_id = job_data["id"]
        user_id = job_data["user_id"]
        generation_type = job_data["generation_type"]

        try:
            # Parse input parameters
            input_params = json.loads(job_data["input_parameters"])

            print(f"🎬 BACKGROUND_PROCESSOR: Processing job {job_id}")
            print(f"   Type: {generation_type}")
            print(f"   User: {user_id}")
            print(f"   Prompt: {input_params['prompt'][:100]}...")

            db = await get_db()

            # Convert input parameters to models
            duration = VideoDuration(input_params["duration"])
            resolution = VideoResolution(input_params["resolution"])
            aspect_ratio = VideoAspectRatio(input_params["aspect_ratio"])
            camera_fixed = input_params.get("camera_fixed", False)

            reference_person = None
            if input_params.get("reference_person"):
                ref_data = input_params["reference_person"]
                reference_person = VideoReferencePerson(
                    person_id=UUID(ref_data["person_id"]),
                    photo_url=ref_data["photo_url"],
                    description=ref_data["description"],
                )

            source_image_url = input_params.get("source_image_url")

            # Update job status to processing
            await video_job_service.update_job_status(
                db=db,
                job_id=job_id,
                status=VideoJobStatus.PROCESSING.value,
            )

            # Create replicate prediction and get prediction ID
            start_time = time.time()

            # Generate video using existing service
            video_url, generation_metadata = await video_generation_service.generate_video(
                prompt=input_params["prompt"],
                generation_type=VideoGenerationType(generation_type),
                duration=duration,
                resolution=resolution,
                aspect_ratio=aspect_ratio,
                reference_person=reference_person,
                source_image_url=source_image_url,
                camera_fixed=camera_fixed,
            )

            print(f"✅ BACKGROUND_PROCESSOR: Video generated for job {job_id}: {video_url}")

            # Upload to R2 and generate thumbnail
            final_video_url, thumbnail_url = await _upload_video_to_r2(video_url, user_id, job_id)

            # Save video to user_videos table
            video_metadata = {
                "prompt": input_params["prompt"],
                "duration": duration.value,
                "resolution": resolution.value,
                "aspect_ratio": aspect_ratio.value,
                "generation_type": generation_type,
                "model_used": generation_metadata.get("model_used"),
                "generation_time_ms": generation_metadata.get("generation_time_ms"),
                "replicate_prediction_id": generation_metadata.get("prediction_id"),
            }

            result = await db.fetch_one(
                """
                INSERT INTO user_videos (
                    id, user_id, url, thumbnail_url, prompt, duration, resolution,
                    aspect_ratio, is_favorited, reference_people, metadata,
                    created_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW(), NOW())
                RETURNING id
                """,
                job_id,  # Use job_id as video_id for consistency
                user_id,
                final_video_url,
                thumbnail_url,
                input_params["prompt"],
                duration.value,
                resolution.value,
                aspect_ratio.value,
                False,  # is_favorited
                json.dumps([]),  # reference_people (empty for now)
                json.dumps(video_metadata),
            )
            video_id = result["id"]

            # Update job as completed
            await video_job_service.update_job_status(
                db=db,
                job_id=job_id,
                status=VideoJobStatus.COMPLETED.value,
                video_id=video_id,
                video_url=final_video_url,
                generation_metadata=generation_metadata,
            )

            # Log usage for analytics (like the sync version does)
            await self._log_video_usage(
                user_id=user_id,
                generation_type=generation_type,
                generation_metadata=generation_metadata,
                duration=duration,
                resolution=resolution,
                prompt=input_params["prompt"],
            )

            total_time = int((time.time() - start_time) * 1000)
            print(f"✅ BACKGROUND_PROCESSOR: Job {job_id} completed in {total_time}ms")

        except Exception as e:
            print(f"❌ BACKGROUND_PROCESSOR: Job {job_id} failed: {str(e)}")

            # Update job as failed
            error_code = "GENERATION_FAILED"
            error_message = f"Video generation failed: {str(e)}"

            # Categorize common errors
            error_str = str(e).lower()
            if "nsfw" in error_str or "inappropriate" in error_str:
                error_code = "CONTENT_FLAGGED"
                error_message = "Content flagged as inappropriate"
            elif "timeout" in error_str:
                error_code = "TIMEOUT"
                error_message = "Video generation timed out"
            elif "connection" in error_str or "network" in error_str:
                error_code = "NETWORK_ERROR"
                error_message = "Network connection error during generation"

            try:
                db = await get_db()
                await video_job_service.update_job_status(
                    db=db,
                    job_id=job_id,
                    status=VideoJobStatus.FAILED.value,
                    error_code=error_code,
                    error_message=error_message,
                    error_details={"details": str(e), "type": type(e).__name__},
                )
            except Exception as db_error:
                print(f"❌ BACKGROUND_PROCESSOR: Failed to update job status: {str(db_error)}")

        finally:
            # Remove from active jobs
            self.active_jobs.discard(job_id)

    async def _log_video_usage(
        self,
        user_id: UUID,
        generation_type: str,
        generation_metadata: dict[str, Any],
        duration: VideoDuration,
        resolution: VideoResolution,
        prompt: str,
    ):
        """Log video usage for analytics (replicates sync version logic)"""
        try:
            import os

            import httpx

            # Calculate duration for cost calculation
            duration_seconds = 5 if duration == VideoDuration.SHORT else 10

            # Apps Service URL - environment-based routing
            environment = os.getenv("ENVIRONMENT", "staging")
            if environment == "staging":
                apps_service_url = "https://fairydust-apps-staging.up.railway.app"
            else:
                apps_service_url = "https://fairydust-apps-production.up.railway.app"

            # Prepare video usage payload
            usage_payload = {
                "user_id": str(user_id),
                "app_id": "fairydust-video",
                "provider": generation_metadata.get("model_used", "unknown").split("/")[0]
                if "/" in generation_metadata.get("model_used", "")
                else "replicate",
                "model_id": generation_metadata.get("model_used", "unknown"),
                "videos_generated": 1,
                "video_duration_seconds": duration_seconds,
                "video_resolution": resolution.value,
                "latency_ms": generation_metadata.get("generation_time_ms", 0),
                "prompt_text": prompt[:500],  # Truncate long prompts
                "finish_reason": "completed",
                "was_fallback": False,
                "fallback_reason": None,
                "request_metadata": {
                    "action": "video_generate"
                    if generation_type == "text_to_video"
                    else "video_animate",
                    "duration": duration.value,
                    "resolution": resolution.value,
                    "generation_type": generation_type,
                    "background_processing": True,  # Flag to indicate async processing
                },
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{apps_service_url}/video/usage",
                    json=usage_payload,
                )

                if response.status_code == 201:
                    print("✅ BACKGROUND_PROCESSOR: Video usage logged successfully")
                else:
                    print(
                        f"⚠️ BACKGROUND_PROCESSOR: Failed to log video usage: {response.status_code}"
                    )

        except Exception as e:
            print(f"⚠️ BACKGROUND_PROCESSOR: Error logging video usage: {str(e)}")
            # Don't fail the job if logging fails

    async def get_stats(self) -> dict[str, Any]:
        """Get processor statistics"""
        try:
            db = await get_db()

            stats = await db.fetch_one(
                """
                SELECT
                    COUNT(*) FILTER (WHERE status = 'queued') as queued,
                    COUNT(*) FILTER (WHERE status = 'starting') as starting,
                    COUNT(*) FILTER (WHERE status = 'processing') as processing,
                    COUNT(*) FILTER (WHERE status = 'completed') as completed,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed,
                    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '1 hour') as last_hour
                FROM video_generation_jobs
                """
            )

            return {
                "processor_running": self.is_running,
                "active_jobs": len(self.active_jobs),
                "max_concurrent": self.max_concurrent_jobs,
                "job_counts": {
                    "queued": stats["queued"] if stats else 0,
                    "starting": stats["starting"] if stats else 0,
                    "processing": stats["processing"] if stats else 0,
                    "completed": stats["completed"] if stats else 0,
                    "failed": stats["failed"] if stats else 0,
                },
                "activity": {
                    "jobs_last_hour": stats["last_hour"] if stats else 0,
                },
            }

        except Exception as e:
            print(f"❌ BACKGROUND_PROCESSOR: Error getting stats: {str(e)}")
            return {
                "processor_running": self.is_running,
                "active_jobs": len(self.active_jobs),
                "error": str(e),
            }


# Global instance
video_background_processor = VideoBackgroundProcessor()
