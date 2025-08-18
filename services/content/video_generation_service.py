"""AI Video generation service for ByteDance SeeDance-1-Pro and MiniMax Video-01 integration"""

import asyncio
import json
import os
import time

import httpx
from fastapi import HTTPException
from models import (
    VideoAspectRatio,
    VideoDuration,
    VideoGenerationType,
    VideoReferencePerson,
    VideoResolution,
)


class VideoGenerationService:
    """Service for generating AI videos using Replicate models"""

    def __init__(self):
        self.replicate_api_token = os.getenv("REPLICATE_API_TOKEN")

        if not self.replicate_api_token:
            raise ValueError("Missing REPLICATE_API_TOKEN environment variable")

    async def _get_video_model_config(self) -> dict:
        """Get video model configuration from app config (normalized structure)"""
        try:
            from shared.database import get_db
            from shared.json_utils import parse_jsonb_field

            # Get the Story app ID (which has video generation capabilities)
            STORY_APP_ID = "fairydust-story"

            # Fetch from database using new normalized structure
            db = await get_db()
            config = await db.fetch_one(
                """
                SELECT parameters FROM app_model_configs
                WHERE app_id = (SELECT id FROM apps WHERE slug = $1)
                AND model_type = 'video'
                AND is_enabled = true
                """,
                STORY_APP_ID,
            )

            if config and config["parameters"]:
                # Parse the JSONB parameters field
                params = parse_jsonb_field(
                    config["parameters"], default={}, field_name="video_parameters"
                )
                return params

            # Return defaults if no config found
            return {
                "text_to_video_model": "minimax/video-01",
                "text_to_video_with_reference_model": "minimax/video-01",
                "image_to_video_model": "bytedance/seedance-1-pro",
            }

        except Exception as e:
            print(f"⚠️ VIDEO_MODEL_CONFIG: Error loading config: {e}")
            # Return defaults on error
            return {
                "text_to_video_model": "minimax/video-01",
                "text_to_video_with_reference_model": "minimax/video-01",
                "image_to_video_model": "bytedance/seedance-1-pro",
            }

    async def generate_video(
        self,
        prompt: str,
        generation_type: VideoGenerationType,
        duration: int,
        resolution: VideoResolution,
        aspect_ratio: VideoAspectRatio,
        reference_person: VideoReferencePerson = None,
        source_image_url: str = None,
        camera_fixed: bool = False,
    ) -> tuple[str, dict]:
        """
        Generate an AI video using appropriate Replicate model

        Returns:
            Tuple[str, dict]: (video_url, metadata)
        """
        start_time = time.time()

        # Get video model configuration
        video_models = await self._get_video_model_config()

        # Choose model based on generation type and reference person
        if generation_type == VideoGenerationType.TEXT_TO_VIDEO and reference_person:
            # Text-to-video WITH reference person (Category 2)
            model = video_models.get("text_to_video_with_reference_model", "minimax/video-01")
            print(f"🎬 VIDEO_GENERATION: Using text-to-video with reference model: {model}")
            video_url, metadata = await self._generate_with_minimax(
                model, prompt, duration, resolution, aspect_ratio, reference_person, camera_fixed
            )
        elif generation_type == VideoGenerationType.IMAGE_TO_VIDEO:
            # Image-to-video (Category 3)
            model = video_models.get("image_to_video_model", "bytedance/seedance-1-pro")
            print(f"🎬 VIDEO_GENERATION: Using image-to-video model: {model}")
            video_url, metadata = await self._generate_with_seedance(
                model, prompt, source_image_url, duration, resolution, aspect_ratio, camera_fixed
            )
        else:
            # Text-to-video WITHOUT reference person (Category 1)
            model = video_models.get("text_to_video_model", "minimax/video-01")
            print(f"🎬 VIDEO_GENERATION: Using text-to-video model: {model}")
            video_url, metadata = await self._generate_with_seedance(
                model, prompt, None, duration, resolution, aspect_ratio, camera_fixed
            )

        generation_time_ms = int((time.time() - start_time) * 1000)
        metadata["generation_time_ms"] = generation_time_ms
        metadata["generation_type"] = generation_type.value

        return video_url, metadata

    async def _generate_with_minimax(
        self,
        model: str,
        prompt: str,
        duration: int,
        resolution: VideoResolution,
        aspect_ratio: VideoAspectRatio,
        reference_person: VideoReferencePerson,
        camera_fixed: bool,
    ) -> tuple[str, dict]:
        """Generate video using MiniMax Video-01 (text-to-video with reference person)"""

        print(f"🎭 MINIMAX GENERATION STARTING - Model: {model}")
        print(f"   Original prompt: {prompt}")
        print(f"   Duration: {duration} seconds")
        print(f"   Resolution: {resolution.value}")
        print(f"   Reference person: {reference_person.description if reference_person else None}")

        # Build payload for MiniMax Video-01
        payload = {
            "input": {
                "prompt": prompt,
                "prompt_optimizer": True,
            }
        }

        # Add reference person if provided
        if reference_person:
            payload["input"]["subject_reference"] = reference_person.photo_url
            # Enhance prompt with person description
            enhanced_prompt = f"{prompt}, featuring {reference_person.description}"
            payload["input"]["prompt"] = enhanced_prompt

        headers = {
            "Authorization": f"Token {self.replicate_api_token}",
            "Content-Type": "application/json",
        }

        # Start prediction
        async with httpx.AsyncClient() as client:
            try:
                print(f"🤖 REPLICATE REQUEST: {model}")
                print(f"🎨 FULL ENHANCED PROMPT: {payload['input']['prompt']}")
                print("⚙️ REQUEST PAYLOAD:")
                print(json.dumps(payload, indent=2))

                # Time the initial API request
                api_request_start = time.time()
                response = await client.post(
                    f"https://api.replicate.com/v1/models/{model}/predictions",
                    headers=headers,
                    json=payload,
                    timeout=120.0,  # Extended for slower video generation requests
                )
                api_request_time = time.time() - api_request_start
                print(f"⏱️ API_TIMING: Initial request took {api_request_time:.2f}s")

                if response.status_code != 201:
                    error_data = response.json() if response.content else {}
                    error_detail = error_data.get("detail", "Unknown error")

                    print(f"❌ REPLICATE API ERROR: {response.status_code}")
                    print(f"   Model: {model}")
                    print(f"   Error Detail: {error_detail}")
                    print(f"   Full Error Response: {error_data}")

                    raise HTTPException(
                        status_code=500, detail=f"Video generation service error: {error_detail}"
                    )

            except httpx.TimeoutException:
                print(f"⏱️ REPLICATE TIMEOUT: Request to {model} timed out after 10s")
                raise HTTPException(
                    status_code=500, detail="Video generation service timeout - please try again"
                )
            except httpx.RequestError as e:
                print(f"🌐 REPLICATE CONNECTION ERROR: {str(e)}")
                raise HTTPException(
                    status_code=500, detail="Unable to connect to video generation service"
                )

            prediction = response.json()
            prediction_id = prediction["id"]
            print(f"✅ REPLICATE PREDICTION STARTED: {prediction_id}")

        # Poll for completion (extended for character reference generations that can take 10+ minutes)
        video_url = await self._poll_for_completion(prediction_id, model, max_wait_time=600)

        metadata = {
            "model_used": model,
            "api_provider": "replicate",
            "enhanced_prompt": payload["input"]["prompt"],
            "prediction_id": prediction_id,
            "generation_approach": "minimax_text_to_video_with_reference",
            "api_request_time": api_request_time,
        }

        return video_url, metadata

    async def _generate_with_seedance(
        self,
        model: str,
        prompt: str,
        source_image_url: str,
        duration: int,
        resolution: VideoResolution,
        aspect_ratio: VideoAspectRatio,
        camera_fixed: bool,
    ) -> tuple[str, dict]:
        """Generate video using ByteDance SeeDance models (text-to-video or image-to-video)"""

        print(f"🎭 SEEDANCE GENERATION STARTING - Model: {model}")
        print(f"   Original prompt: {prompt}")
        print(f"   Duration: {duration} seconds")
        print(f"   Resolution: {resolution.value}")
        print(f"   Aspect ratio: {aspect_ratio.value}")
        print(f"   Source image: {source_image_url is not None}")

        # Duration is now provided in seconds directly
        duration_seconds = duration

        # Map resolution to SeeDance format
        if resolution == VideoResolution.SD_480P:
            seedance_resolution = "480p"
        elif resolution == VideoResolution.HD_720P:
            seedance_resolution = "720p"
        else:  # HD_1080P
            seedance_resolution = "1080p"

        # Build payload for SeeDance-1-Pro
        payload = {
            "input": {
                "prompt": prompt,
                "duration": duration_seconds,
                "resolution": seedance_resolution,
                "aspect_ratio": aspect_ratio.value,
                "fps": 24,
                "camera_fixed": camera_fixed,
            }
        }

        # Add image for image-to-video generation
        if source_image_url:
            payload["input"]["image"] = source_image_url

        headers = {
            "Authorization": f"Token {self.replicate_api_token}",
            "Content-Type": "application/json",
        }

        # Start prediction
        async with httpx.AsyncClient() as client:
            try:
                print(f"🤖 REPLICATE REQUEST: {model}")
                print(f"🎨 PROMPT: {prompt}")
                print("⚙️ REQUEST PAYLOAD:")
                print(json.dumps(payload, indent=2))

                # Time the initial API request
                api_request_start = time.time()
                response = await client.post(
                    f"https://api.replicate.com/v1/models/{model}/predictions",
                    headers=headers,
                    json=payload,
                    timeout=120.0,  # Extended for slower video generation requests
                )
                api_request_time = time.time() - api_request_start
                print(f"⏱️ API_TIMING: Initial request took {api_request_time:.2f}s")

                if response.status_code != 201:
                    error_data = response.json() if response.content else {}
                    error_detail = error_data.get("detail", "Unknown error")

                    print(f"❌ REPLICATE API ERROR: {response.status_code}")
                    print(f"   Model: {model}")
                    print(f"   Error Detail: {error_detail}")
                    print(f"   Full Error Response: {error_data}")

                    raise HTTPException(
                        status_code=500, detail=f"Video generation service error: {error_detail}"
                    )

            except httpx.TimeoutException:
                print(f"⏱️ REPLICATE TIMEOUT: Request to {model} timed out after 10s")
                raise HTTPException(
                    status_code=500, detail="Video generation service timeout - please try again"
                )
            except httpx.RequestError as e:
                print(f"🌐 REPLICATE CONNECTION ERROR: {str(e)}")
                raise HTTPException(
                    status_code=500, detail="Unable to connect to video generation service"
                )

            prediction = response.json()
            prediction_id = prediction["id"]
            print(f"✅ REPLICATE PREDICTION STARTED: {prediction_id}")

        # Poll for completion (extended for generations that can take 10+ minutes)
        video_url = await self._poll_for_completion(prediction_id, model, max_wait_time=600)

        # Determine generation approach based on model and input
        if source_image_url:
            generation_approach = f"{model.split('/')[-1]}_image_to_video"
        else:
            generation_approach = f"{model.split('/')[-1]}_text_to_video"

        metadata = {
            "model_used": model,
            "api_provider": "replicate",
            "enhanced_prompt": prompt,
            "prediction_id": prediction_id,
            "generation_approach": generation_approach,
            "api_request_time": api_request_time,
            "duration_seconds": duration_seconds,
            "resolution": seedance_resolution,
            "aspect_ratio": aspect_ratio.value,
        }

        return video_url, metadata

    async def _poll_for_completion(
        self, prediction_id: str, model: str, max_wait_time: int = 600
    ) -> str:
        """Poll Replicate API for video generation completion"""

        headers = {
            "Authorization": f"Token {self.replicate_api_token}",
        }

        elapsed_time = 0
        poll_start_time = time.time()
        poll_count = 0

        # Dynamic polling intervals for video (longer than images)
        poll_intervals = [2, 3, 5, 8, 10, 15, 20]  # seconds
        poll_index = 0

        print(f"⏱️ POLLING_TIMING: Starting to poll video prediction {prediction_id}")

        async with httpx.AsyncClient() as client:
            while elapsed_time < max_wait_time:
                # Use dynamic interval
                current_interval = poll_intervals[min(poll_index, len(poll_intervals) - 1)]
                await asyncio.sleep(current_interval)
                elapsed_time += current_interval
                poll_index += 1
                poll_count += 1

                poll_request_start = time.time()
                poll_response = await client.get(
                    f"https://api.replicate.com/v1/predictions/{prediction_id}", headers=headers
                )
                poll_request_time = time.time() - poll_request_start

                if poll_response.status_code != 200:
                    raise HTTPException(status_code=500, detail="Failed to check prediction status")

                result = poll_response.json()
                status = result["status"]

                print(
                    f"⏱️ POLLING_TIMING: Poll #{poll_count} after {elapsed_time}s - Status: {status} (poll took {poll_request_time:.3f}s)"
                )

                if status == "succeeded":
                    total_poll_time = time.time() - poll_start_time
                    print(
                        f"✅ POLLING_TIMING: Video prediction completed! Total polling time: {total_poll_time:.2f}s over {poll_count} polls"
                    )

                    video_url = (
                        result["output"][0]
                        if isinstance(result["output"], list)
                        else result["output"]
                    )

                    return video_url

                elif status == "failed":
                    error_msg = result.get("error", "Unknown generation error")
                    logs = result.get("logs", "")

                    print(f"❌ REPLICATE PREDICTION FAILED: {prediction_id}")
                    print(f"   Model: {model}")
                    print(f"   Error Message: {error_msg}")
                    print(f"   Logs: {logs}")
                    print(f"   Full Result: {result}")

                    # Build detailed error message
                    detailed_error = error_msg
                    if not error_msg or error_msg.strip() == "":
                        detailed_error = "Video generation failed (no error message from service)"
                        if logs:
                            detailed_error += f". Logs: {logs[-500:]}"  # Last 500 chars

                    # Add model-specific context for common issues
                    if model == "minimax/video-01":
                        detailed_error += ". Note: This was a text-to-video generation with character reference using MiniMax model."

                    raise HTTPException(
                        status_code=500, detail=f"Video generation failed: {detailed_error}"
                    )

        # Timeout
        print(f"⏱️ REPLICATE PREDICTION TIMEOUT: {prediction_id}")
        print(f"   Model: {model}")
        print(f"   Max Wait Time: {max_wait_time}s")
        print(f"   Total Elapsed: {elapsed_time}s")

        raise HTTPException(status_code=500, detail="Video generation timed out")


# Global instance
video_generation_service = VideoGenerationService()
