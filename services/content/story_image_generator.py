"""Background image generation for stories"""

import asyncio
import json
import logging
import time
import traceback
from datetime import datetime

from fastapi import HTTPException
from image_generation_service import image_generation_service
from image_storage_service import image_storage_service
from models import ImageSize, ImageStyle, StoryCharacter, TargetAudience
from story_image_service import story_image_service

from shared.database import Database

logger = logging.getLogger(__name__)


class StoryImageGenerator:
    """Handles background generation of images for stories"""

    def __init__(self):
        pass

    async def generate_story_images_background(
        self,
        story_id: str,
        user_id: str,
        scenes: list[dict],
        characters: list[StoryCharacter],
        target_audience: TargetAudience,
        db: Database,
        full_story_content: str = None,
        story_theme: str = None,
        story_genre: str = None,
        story_context: str = None,
    ):
        """Background task to generate all images for a story using parallel processing"""

        import time

        start_time = time.time()

        try:
            logger.info(f"🚀 Starting PARALLEL background image generation for story {story_id}")
            logger.info(f"   Scenes to generate: {len(scenes)}")
            logger.info(f"   Characters available: {len(characters)}")
            logger.info(
                f"⏱️ TIMING: Parallel generation started at {time.strftime('%H:%M:%S', time.localtime(start_time))}"
            )

            # Insert initial records for all images
            for scene in scenes:
                await self._create_story_image_record(db, story_id, user_id, scene)

            # Generate all images in parallel
            logger.info(f"⚡ Starting parallel generation of {len(scenes)} images...")
            generation_start_time = time.time()

            # Create tasks for parallel execution
            generation_tasks = []
            for scene in scenes:
                task = asyncio.create_task(
                    self._generate_single_image_with_error_handling(
                        db,
                        story_id,
                        user_id,
                        scene,
                        characters,
                        target_audience,
                        full_story_content,
                        story_theme,
                        story_genre,
                        story_context,
                    ),
                    name=f"generate_image_{scene['image_id']}",
                )
                generation_tasks.append(task)

            # Wait for all images to complete (or fail)
            results = await asyncio.gather(*generation_tasks, return_exceptions=True)
            generation_end_time = time.time()
            generation_duration = generation_end_time - generation_start_time

            # Count successful generations and track retry stats
            completed_count = 0
            failed_count = 0
            retry_success_count = 0
            first_attempt_success_count = 0

            for i, result in enumerate(results):
                scene = scenes[i]
                if isinstance(result, Exception):
                    failed_count += 1
                    logger.error(
                        f"❌ Failed to generate image {scene['image_id']} for story {story_id}: {result}"
                    )
                elif result is True:  # Success
                    completed_count += 1
                    logger.info(
                        f"✅ Successfully generated image {scene['image_id']} for story {story_id}"
                    )
                else:
                    # result is False (handled failure)
                    failed_count += 1

            # Get comprehensive retry statistics from database
            retry_stats = await self._get_retry_statistics(db, story_id)

            # Update story completion status
            images_complete = completed_count == len(scenes)
            await self._update_story_completion_status(db, story_id, images_complete)

            # Calculate timing metrics
            total_time = time.time() - start_time
            avg_time_per_image = generation_duration / len(scenes) if len(scenes) > 0 else 0

            logger.info("🎯 PARALLEL_GENERATION_COMPLETE!")
            logger.info(
                f"   Success rate: {completed_count}/{len(scenes)} images ({completed_count/len(scenes)*100:.1f}%)"
            )
            logger.info(f"   Failed: {failed_count} images")
            logger.info("📊 RETRY_STATISTICS:")
            logger.info(f"   First attempt successes: {retry_stats.get('first_attempt_successes', 0)}")
            logger.info(f"   First attempt failures: {retry_stats.get('first_attempt_failures', 0)}")
            logger.info(f"   Total retry attempts: {retry_stats.get('total_retry_attempts', 0)}")
            logger.info(f"   Retry successes: {retry_stats.get('retry_successes', 0)}")
            logger.info(f"   Retry failures: {retry_stats.get('retry_failures', 0)}")
            
            # Calculate retry success rate if there were any retries
            total_retries = retry_stats.get('total_retry_attempts', 0)
            retry_successes = retry_stats.get('retry_successes', 0)
            if total_retries > 0:
                retry_success_rate = (retry_successes / total_retries) * 100
                logger.info(f"   Retry success rate: {retry_success_rate:.1f}% ({retry_successes}/{total_retries} retry attempts)")
            else:
                logger.info("   Retry success rate: N/A (no retries attempted)")
            logger.info("⏱️ TIMING_METRICS:")
            logger.info(f"   Total elapsed time: {total_time:.2f}s")
            logger.info(f"   Pure generation time: {generation_duration:.2f}s")
            logger.info(f"   Average time per image: {avg_time_per_image:.2f}s")
            logger.info(f"   Setup/cleanup overhead: {(total_time - generation_duration):.2f}s")

            if completed_count > 0:
                logger.info(
                    f"⚡ PERFORMANCE: Generated {completed_count} images simultaneously instead of sequentially"
                )
                # Estimate sequential time savings (assume 30s average per image if done sequentially)
                estimated_sequential_time = len(scenes) * 30
                time_saved = max(0, estimated_sequential_time - generation_duration)
                logger.info(f"   Estimated time saved vs sequential: {time_saved:.1f}s")

        except Exception as e:
            logger.error(
                f"💥 Critical error in parallel background image generation for story {story_id}: {e}"
            )
            logger.error(f"   Exception traceback: {traceback.format_exc()}")

            # Mark story as having incomplete images
            try:
                await self._update_story_completion_status(db, story_id, False)
            except Exception as cleanup_error:
                logger.error(f"Failed to update story completion status: {cleanup_error}")

    async def _generate_single_image_with_error_handling(
        self,
        db: Database,
        story_id: str,
        user_id: str,
        scene: dict,
        characters: list[StoryCharacter],
        target_audience: TargetAudience,
        full_story_content: str = None,
        story_theme: str = None,
        story_genre: str = None,
        story_context: str = None,
    ) -> bool:
        """Wrapper for _generate_single_image with proper error handling for parallel execution"""

        import time

        image_id = scene["image_id"]
        start_time = time.time()

        try:
            logger.info(
                f"⏱️ INDIVIDUAL_TIMING: Starting image {image_id} at {time.strftime('%H:%M:%S')}"
            )

            await self._generate_single_image(
                db,
                story_id,
                user_id,
                scene,
                characters,
                target_audience,
                full_story_content,
                story_theme,
                story_genre,
                story_context,
            )

            total_time = time.time() - start_time
            logger.info(f"✅ INDIVIDUAL_TIMING: Image {image_id} completed in {total_time:.2f}s")
            return True  # Success

        except Exception as e:
            total_time = time.time() - start_time
            logger.error(f"❌ INDIVIDUAL_TIMING: Image {image_id} FAILED after {total_time:.2f}s")
            
            # Check if this is a known Replicate error that we handle gracefully
            error_msg = str(e).lower()
            is_known_replicate_error = (
                "replicate internal.bad_output" in error_msg 
                or "replicate_bad_output" in getattr(e, "retry_type", "")
                or "nsfw" in getattr(e, "retry_type", "")
                or "transient" in getattr(e, "retry_type", "")
            )
            
            if is_known_replicate_error:
                # Clean logging for known errors - no stack trace needed
                logger.error(f"❌ Known service error for image {image_id}: {str(e)}")
                if hasattr(e, "retry_type"):
                    logger.error(f"   Error category: {e.retry_type}")
                if hasattr(e, "prompt_used"):
                    logger.error(f"   Prompt that failed: {e.prompt_used[:200]}...")
            else:
                # Unknown errors get full details including stack trace
                logger.error(f"❌ Unexpected error for image {image_id}: {str(e)}")
                logger.error(f"   Exception type: {type(e).__name__}")
                logger.error(f"   Exception traceback: {traceback.format_exc()}")

            # Mark image as failed
            try:
                # Extract retry information if available
                retry_count = getattr(e, "retry_count", 0)
                await self._mark_image_failed(db, story_id, image_id, str(e), retry_count)
            except Exception as mark_error:
                logger.error(f"Failed to mark image {image_id} as failed: {mark_error}")

            return False  # Handled failure

    async def _create_story_image_record(
        self, db: Database, story_id: str, user_id: str, scene: dict
    ):
        """Create initial database record for story image"""

        await db.execute(
            """
            INSERT INTO story_images (
                story_id, user_id, image_id, prompt, scene_description, status
            ) VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (story_id, image_id) DO NOTHING
            """,
            story_id,
            user_id,
            scene["image_id"],
            scene["scene_description"],  # Initial prompt
            scene["scene_description"],
            "pending",
        )

        logger.debug(f"📝 Created story image record: {scene['image_id']}")

    async def _generate_single_image(
        self,
        db: Database,
        story_id: str,
        user_id: str,
        scene: dict,
        characters: list[StoryCharacter],
        target_audience: TargetAudience,
        full_story_content: str = None,
        story_theme: str = None,
        story_genre: str = None,
        story_context: str = None,
    ):
        """Generate a single image for a story scene"""

        import time

        image_id = scene["image_id"]
        phase_times = {}

        try:
            # Update status to generating
            await db.execute(
                "UPDATE story_images SET status = $1, updated_at = CURRENT_TIMESTAMP WHERE story_id = $2 AND image_id = $3",
                "generating",
                story_id,
                image_id,
            )

            # Determine characters in this scene
            characters_in_scene = scene.get("characters_mentioned", [])

            # Generate optimized prompt using multi-agent AI system
            prompt_start_time = time.time()
            enhanced_prompt = await story_image_service.generate_image_prompt(
                scene["scene_description"],
                characters_in_scene,
                target_audience,
                user_id,  # Pass user_id for proper LLM usage logging
                story_context,
                story_theme,
                story_genre,
                full_story_content,
            )
            phase_times["prompt_generation"] = time.time() - prompt_start_time

            logger.info("📝 STORY IMAGE PROMPT GENERATION:")
            logger.info(
                f"   Scene position: {scene.get('position', 'unknown')} (importance: {scene.get('narrative_importance', 'unknown')})"
            )
            logger.info(f"   Scene type: {scene.get('scene_type', 'general')}")
            logger.info(f"   Story content length: {len(scene['scene_description'])} characters")
            logger.info(
                f"   Scene description (first 150 chars): {scene['scene_description'][:150]}..."
            )
            logger.info(f"   Characters in scene: {[char.name for char in characters_in_scene]}")
            # Log detailed character information
            for char in characters_in_scene:
                char_info = f"      {char.name}: type={char.entry_type or 'person'}"
                if char.species:
                    char_info += f", species={char.species}"
                if char.relationship:
                    char_info += f", relationship='{char.relationship}'"
                if char.traits:
                    char_info += f", traits={char.traits[:3]}"  # Show first 3 traits
                logger.info(char_info)
            logger.info(f"   Target audience: {target_audience.value}")
            logger.info(f"   STRUCTURED PROMPT: {enhanced_prompt}")
            logger.info(f"   Prompt length: {len(enhanced_prompt)} characters")

            # Log prompt structure breakdown
            if " and " in enhanced_prompt or " in " in enhanced_prompt:
                logger.info(
                    "   ✅ Prompt appears well-structured with clear subjects and scene context"
                )

            # Prepare reference people (smart character selection)
            reference_people = []
            if characters_in_scene:
                if len(characters_in_scene) <= 3:
                    # Use all characters as references (if they have photos)
                    reference_people = story_image_service.prepare_reference_people(
                        characters_in_scene, user_id
                    )
                else:
                    # Select top 3 most important characters
                    important_characters = story_image_service.select_most_important_characters(
                        characters_in_scene, 3
                    )
                    reference_people = story_image_service.prepare_reference_people(
                        important_characters, user_id
                    )

                    # Add remaining characters to prompt description
                    remaining_characters = characters_in_scene[3:]
                    if remaining_characters:
                        char_descriptions = [
                            f"{char.name} ({char.relationship})" for char in remaining_characters
                        ]
                        enhanced_prompt += f", also featuring {', '.join(char_descriptions)}"

            # Update prompt in database
            await db.execute(
                "UPDATE story_images SET prompt = $1 WHERE story_id = $2 AND image_id = $3",
                enhanced_prompt,
                story_id,
                image_id,
            )

            logger.info(f"🎨 Generating image {image_id}")
            logger.info(f"   Prompt: {enhanced_prompt[:100]}...")
            logger.info(f"   Reference people: {len(reference_people)}")

            # Generate image with retry logic for NSFW false positives
            generation_start_time = time.time()
            image_url, generation_metadata = await self._generate_image_with_retry(
                enhanced_prompt, scene, characters_in_scene, target_audience, reference_people
            )
            phase_times["image_generation"] = time.time() - generation_start_time

            # Store image in R2
            storage_start_time = time.time()
            stored_url, file_size, dimensions = await image_storage_service.store_generated_image(
                image_url, user_id, image_id
            )
            phase_times["image_storage"] = time.time() - storage_start_time

            # Prepare full metadata
            full_metadata = {
                **generation_metadata,
                "file_size_bytes": file_size,
                "dimensions": dimensions,
                "characters_in_scene": [char.name for char in characters_in_scene],
                "reference_people_count": len(reference_people),
                "phase_timings": phase_times,  # Include timing breakdown
            }

            # Update database with completed image
            db_start_time = time.time()
            await db.execute(
                """
                UPDATE story_images
                SET url = $1, status = $2, generation_metadata = $3, updated_at = CURRENT_TIMESTAMP
                WHERE story_id = $4 AND image_id = $5
                """,
                stored_url,
                "completed",
                json.dumps(full_metadata),
                story_id,
                image_id,
            )
            phase_times["database_update"] = time.time() - db_start_time

            # Log detailed timing breakdown
            total_phases_time = sum(phase_times.values())
            logger.info(f"✅ Successfully generated and stored image {image_id}")
            logger.info(f"⏱️ PHASE_TIMING_BREAKDOWN for {image_id}:")
            logger.info(f"   Prompt generation: {phase_times.get('prompt_generation', 0):.2f}s")
            logger.info(f"   Image generation: {phase_times.get('image_generation', 0):.2f}s")
            logger.info(f"   Image storage: {phase_times.get('image_storage', 0):.2f}s")
            logger.info(f"   Database update: {phase_times.get('database_update', 0):.2f}s")
            logger.info(f"   Total phases: {total_phases_time:.2f}s")

        except Exception as e:
            # Extract error details for better debugging
            error_msg = str(e)
            if isinstance(e, HTTPException):
                error_msg = f"HTTP {e.status_code}: {e.detail}"

            logger.error(f"❌ Failed to generate image {image_id}: {error_msg}")
            logger.error(f"   Error type: {type(e).__name__}")
            logger.error(f"   Scene description: {scene.get('scene_description', 'N/A')[:100]}...")
            logger.error(f"   Characters in scene: {len(characters_in_scene)}")
            logger.error(f"   Target audience: {target_audience.value}")
            logger.error(f"   Exception traceback: {traceback.format_exc()}")
            raise  # Re-raise to be caught by caller

    async def _mark_image_failed(
        self, db: Database, story_id: str, image_id: str, error_message: str, retry_count: int = 0
    ):
        """Mark an image as failed in the database with detailed error info"""

        try:
            # Extract more detailed error information
            error_type = "unknown"
            error_detail = error_message

            # Classify the error type
            if (
                "HTTP 400" in error_message
                or "NSFW" in error_message.lower()
                or "content not allowed" in error_message.lower()
            ):
                error_type = "content_policy"
            elif "timeout" in error_message.lower():
                error_type = "timeout"
            elif "HTTP 5" in error_message:
                error_type = "server_error"
            elif "rate limit" in error_message.lower():
                error_type = "rate_limit"
            elif "internal.bad_output" in error_message.lower():
                error_type = "replicate_error"

            error_metadata = {
                "error": error_message,
                "error_type": error_type,
                "failed_at": "background_generation",
                "timestamp": datetime.utcnow().isoformat(),
                "retry_count": retry_count,
                "total_attempts": retry_count + 1,
                "retry_success": False,
            }

            await db.execute(
                """
                UPDATE story_images
                SET status = $1, generation_metadata = $2, updated_at = CURRENT_TIMESTAMP
                WHERE story_id = $3 AND image_id = $4
                """,
                "failed",
                json.dumps(error_metadata),
                story_id,
                image_id,
            )

            logger.error(
                f"❌ FINAL_FAILURE: Image {image_id} marked as failed (type: {error_type}, attempts: {retry_count + 1})"
            )

        except Exception as e:
            logger.error(f"Failed to mark image {image_id} as failed: {e}")

    async def _update_story_completion_status(
        self, db: Database, story_id: str, images_complete: bool
    ):
        """Update the story's image completion status"""

        try:
            await db.execute(
                "UPDATE user_stories SET images_complete = $1 WHERE id = $2",
                images_complete,
                story_id,
            )

            logger.info(f"📊 Updated story {story_id} images_complete = {images_complete}")

        except Exception as e:
            logger.error(f"Failed to update story completion status: {e}")

    async def _get_retry_statistics(self, db: Database, story_id: str) -> dict:
        """Get comprehensive retry statistics for images in this story"""
        try:
            # Query generation metadata from ALL images (completed AND failed) to count retries
            query = """
                SELECT generation_metadata, status
                FROM story_images
                WHERE story_id = $1 AND status IN ('completed', 'failed')
            """
            rows = await db.fetch_all(query, story_id)

            retry_successes = 0
            retry_failures = 0
            total_retry_attempts = 0
            first_attempt_successes = 0
            first_attempt_failures = 0

            for row in rows:
                try:
                    metadata = (
                        json.loads(row["generation_metadata"]) if row["generation_metadata"] else {}
                    )
                    
                    total_attempts = metadata.get("total_attempts", 1)
                    retry_success = metadata.get("retry_success", False)
                    
                    if total_attempts > 1:
                        # This image had retries
                        total_retry_attempts += (total_attempts - 1)  # Don't count first attempt
                        if row["status"] == "completed" and retry_success:
                            retry_successes += 1
                        elif row["status"] == "failed":
                            retry_failures += 1
                    else:
                        # First attempt only
                        if row["status"] == "completed":
                            first_attempt_successes += 1
                        elif row["status"] == "failed":
                            first_attempt_failures += 1
                            
                except (json.JSONDecodeError, TypeError):
                    # Default to first attempt failure if we can't parse metadata
                    if row["status"] == "failed":
                        first_attempt_failures += 1
                    elif row["status"] == "completed":
                        first_attempt_successes += 1
                    continue

            return {
                "retry_successes": retry_successes,
                "retry_failures": retry_failures,
                "total_retry_attempts": total_retry_attempts,
                "first_attempt_successes": first_attempt_successes,
                "first_attempt_failures": first_attempt_failures,
            }
        except Exception as e:
            logger.error(f"Failed to get retry statistics: {e}")
            return {
                "retry_successes": 0, 
                "retry_failures": 0, 
                "total_retry_attempts": 0,
                "first_attempt_successes": 0,
                "first_attempt_failures": 0
            }

    async def _generate_image_with_retry(
        self,
        original_prompt: str,
        scene: dict,
        characters_in_scene: list,
        target_audience,
        reference_people: list,
        max_retries: int = 3,
    ):
        """Generate image with retry logic for NSFW false positives and transient Replicate errors"""

        image_id = scene.get("image_id", "unknown")
        nsfw_failure_detected = False
        retry_start_time = None

        logger.info(
            f"🎯 IMAGE_RETRY_START: Beginning generation for image {image_id} (max {max_retries} attempts)"
        )

        for attempt in range(max_retries):
            try:
                # Log timing between attempts
                if attempt > 0:
                    if retry_start_time:
                        retry_delay = time.time() - retry_start_time
                        logger.info(
                            f"⏱️ IMAGE_RETRY_TIMING: Attempt {attempt + 1} for image {image_id} starting after {retry_delay:.2f}s delay"
                        )

                prompt_to_use = original_prompt

                if attempt > 0 and nsfw_failure_detected:
                    # Only sanitize prompt if previous failure was NSFW-related
                    logger.warning(
                        f"🚨 NSFW_RETRY: Image {image_id} attempt {attempt + 1} - Sanitizing prompt due to content policy violation"
                    )

                    old_prompt = prompt_to_use
                    prompt_to_use = self._sanitize_prompt_for_retry(
                        original_prompt, scene, characters_in_scene, target_audience, attempt
                    )

                    # Show prompt changes for debugging
                    logger.info(f"🔄 PROMPT_SANITIZATION for image {image_id}:")
                    logger.info(f"   ORIGINAL: {old_prompt}")
                    logger.info(f"   SANITIZED: {prompt_to_use}")

                    # Highlight what changed
                    changes_made = self._analyze_prompt_changes(old_prompt, prompt_to_use)
                    if changes_made:
                        logger.info(f"   CHANGES_MADE: {', '.join(changes_made)}")
                else:
                    logger.info(
                        f"🎯 ATTEMPT {attempt + 1} for image {image_id}: Using {'original' if attempt == 0 else 'retry'} prompt"
                    )
                    logger.debug(f"   FULL_PROMPT: {prompt_to_use}")

                # Try to generate with current prompt
                attempt_start_time = time.time()
                image_url, generation_metadata = await image_generation_service.generate_image(
                    prompt_to_use,
                    ImageStyle.CARTOON,  # Default to cartoon for stories
                    ImageSize.STANDARD,
                    reference_people,
                )

                # Success!
                attempt_duration = time.time() - attempt_start_time
                if attempt > 0:
                    logger.info(
                        f"✅ RETRY_SUCCESS: Image {image_id} generated successfully after {attempt + 1} attempts in {attempt_duration:.2f}s"
                    )
                    # Add retry metadata to generation_metadata
                    generation_metadata["retry_count"] = attempt
                    generation_metadata["retry_success"] = True
                    generation_metadata["total_attempts"] = attempt + 1
                else:
                    logger.info(
                        f"✅ FIRST_ATTEMPT_SUCCESS: Image {image_id} generated on first attempt in {attempt_duration:.2f}s"
                    )
                    generation_metadata["retry_count"] = 0
                    generation_metadata["retry_success"] = False
                    generation_metadata["total_attempts"] = 1

                return image_url, generation_metadata

            except Exception as e:
                error_msg = str(e).lower()
                retry_start_time = time.time()  # Track when retry delay starts

                # Check for NSFW-related errors (these need prompt sanitization)
                if (
                    "nsfw" in error_msg
                    or "inappropriate" in error_msg
                    or "content not allowed" in error_msg
                    or "flagged as sensitive" in error_msg
                    or "sensitive content" in error_msg
                    or "(e005)" in error_msg
                    or "content safety" in error_msg
                ):
                    nsfw_failure_detected = True
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"🚨 NSFW_FAILURE: Image {image_id} attempt {attempt + 1} failed - content policy violation"
                        )
                        logger.warning(f"   Prompt that triggered NSFW: {prompt_to_use[:100]}...")
                        logger.warning(f"   Full error message: {str(e)}")
                        logger.info(
                            f"🔄 NSFW_RETRY_QUEUED: Will retry image {image_id} with sanitized prompt (attempt {attempt + 2}/{max_retries})"
                        )
                        continue
                    else:
                        logger.error(
                            f"❌ NSFW_FINAL_FAILURE: Image {image_id} failed all {max_retries} attempts due to persistent NSFW detection"
                        )
                        logger.error(f"   Last prompt attempted: {prompt_to_use}")
                        # Store retry count in the exception for later use
                        final_error = f"Image generation failed after {max_retries} attempts: NSFW content detected"
                        error_with_retry_info = Exception(final_error)
                        error_with_retry_info.retry_count = attempt
                        error_with_retry_info.retry_type = "nsfw"
                        raise error_with_retry_info

                # Check for specific Replicate INTERNAL.BAD_OUTPUT errors (special handling)
                elif "internal.bad_output" in error_msg:
                    # Special logging for INTERNAL.BAD_OUTPUT errors with prompt details
                    logger.warning(f"🔧 REPLICATE_BAD_OUTPUT: Image {image_id} attempt {attempt + 1} failed with Replicate internal error")
                    logger.warning(f"   Error code: INTERNAL.BAD_OUTPUT (Replicate model failure)")
                    logger.warning(f"   Original prompt: {original_prompt}")
                    logger.warning(f"   Current prompt: {prompt_to_use}")
                    logger.warning(f"   Prompt length: {len(prompt_to_use)} characters")
                    logger.warning(f"   Reference people: {len(reference_people)} images")
                    
                    if attempt < max_retries - 1:
                        backoff_delay = 2**attempt  # Exponential backoff: 1s, 2s, 4s
                        logger.info(f"🔄 REPLICATE_RETRY: Will retry image {image_id} in {backoff_delay}s (attempt {attempt + 2}/{max_retries})")
                        await asyncio.sleep(backoff_delay)
                        continue
                    else:
                        logger.error(f"❌ REPLICATE_FINAL_FAILURE: Image {image_id} failed all {max_retries} attempts with INTERNAL.BAD_OUTPUT")
                        logger.error(f"   This suggests a persistent issue with the prompt or Replicate service")
                        logger.error(f"   Final prompt attempted: {prompt_to_use}")
                        final_error = f"Replicate INTERNAL.BAD_OUTPUT error after {max_retries} attempts"
                        error_with_retry_info = Exception(final_error)
                        error_with_retry_info.retry_count = attempt
                        error_with_retry_info.retry_type = "replicate_bad_output"
                        error_with_retry_info.prompt_used = prompt_to_use
                        raise error_with_retry_info
                
                # Check for other transient Replicate errors (general handling)
                elif (
                    "unexpected error occurred" in error_msg
                    or "timeout" in error_msg
                    or "service unavailable" in error_msg
                    or "temporarily unavailable" in error_msg
                    or "rate limit" in error_msg
                    or "queue full" in error_msg
                ):
                    if attempt < max_retries - 1:
                        backoff_delay = 2**attempt  # Exponential backoff: 1s, 2s, 4s
                        logger.warning(
                            f"⚠️ TRANSIENT_ERROR: Image {image_id} attempt {attempt + 1} failed with retryable error"
                        )
                        logger.warning(f"   Error type: {error_msg}")
                        logger.info(
                            f"⏱️ RETRY_BACKOFF: Waiting {backoff_delay}s before retry attempt {attempt + 2}/{max_retries} for image {image_id}"
                        )
                        # Add a small delay for transient errors to avoid rate limits
                        await asyncio.sleep(backoff_delay)
                        continue
                    else:
                        logger.error(
                            f"❌ TRANSIENT_FINAL_FAILURE: Image {image_id} failed all {max_retries} attempts due to persistent transient errors"
                        )
                        logger.error(f"   Last error: {error_msg}")
                        final_error = (
                            f"Image generation failed after {max_retries} attempts: {error_msg}"
                        )
                        error_with_retry_info = Exception(final_error)
                        error_with_retry_info.retry_count = attempt
                        error_with_retry_info.retry_type = "transient"
                        raise error_with_retry_info
                else:
                    # Extract detailed error information for better debugging
                    if isinstance(e, HTTPException):
                        error_detail = f"HTTP {e.status_code}: {e.detail}"
                        logger.error(f"❌ Non-retryable HTTP error: {error_detail}")
                        logger.error(f"   Status Code: {e.status_code}")
                        logger.error(f"   Error Detail: {e.detail}")
                        logger.error(f"   Full exception type: {type(e).__name__}")
                        # Re-raise with more context
                        raise Exception(f"Image generation failed with {error_detail}")
                    else:
                        logger.error(f"❌ Non-retryable error ({type(e).__name__}): {str(e)}")
                        raise

        # Should never reach here
        raise Exception("Image generation failed: Maximum retries exceeded")

    def _sanitize_prompt_for_retry(
        self,
        original_prompt: str,
        scene: dict,
        characters_in_scene: list,
        target_audience,
        attempt: int,
    ) -> str:
        """Create progressively more sanitized prompts for retry attempts"""

        # Common words that might trigger false NSFW detection in children's stories
        sanitization_words = {
            # Words that might be misinterpreted
            "discovered": "found",
            "exploring": "walking through",
            "dark": "shadowy",
            "mysterious": "curious",
            "secret": "hidden",
            "whispered": "said quietly",
            "breathed": "spoke softly",
            "trembling": "nervous",
            "shivering": "cold",
            "passion": "excitement",
            "desire": "wish",
            "touched": "reached for",
            "embrace": "hug",
            "intimate": "close",
            "seductive": "appealing",
            "naked": "without clothes",
            "bare": "empty",
            "exposed": "visible",
            "flesh": "skin",
            "breast": "chest",
            "thigh": "leg",
            "sensual": "gentle",
            "erotic": "artistic",
            "climax": "peak",
            "penetrated": "entered",
            "thrust": "pushed",
            "moist": "damp",
            "wet": "damp",
            "hard": "firm",
            "soft": "gentle",
            "hot": "warm",
            "burning": "glowing",
            "fire": "light",
            "flame": "glow",
            # Additional words that might trigger false positives
            "tight": "snug",
            "loose": "flowing",
            "strip": "remove",
            "stripped": "removed",
            "bare": "plain",
            "exposed": "visible",
            "revealing": "showing",
            "body": "figure",
            "chest": "torso",
            "curves": "shape",
            "attractive": "pretty",
            "seductive": "charming",
            "tempting": "appealing",
            "lust": "admiration",
            "arousing": "exciting",
            "stimulating": "interesting",
        }

        # Start with original prompt
        sanitized = original_prompt

        if attempt == 1:
            # First retry: Replace potentially problematic words
            for problematic, safe in sanitization_words.items():
                sanitized = sanitized.replace(problematic, safe)

            # Add extra safety words
            sanitized += ", family-friendly, safe for children, innocent, wholesome"

        elif attempt == 2:
            # Second retry: More aggressive sanitization
            # Focus on just the core scene description
            base_description = scene.get("scene_description", "")

            # Create a very simple, clean prompt
            if characters_in_scene:
                char_names = [char.name for char in characters_in_scene]
                sanitized = f"A cheerful children's book illustration showing {', '.join(char_names)} in a happy scene"
            else:
                sanitized = "A cheerful children's book illustration with happy characters"

            # Add safe style descriptors
            sanitized += ", cartoon style, colorful, friendly, safe for children, wholesome family content, bright and cheerful"

        return sanitized

    def _analyze_prompt_changes(self, original_prompt: str, sanitized_prompt: str) -> list[str]:
        """Analyze what changes were made during prompt sanitization"""
        changes = []

        # Check for word replacements
        sanitization_words = {
            "discovered": "found",
            "exploring": "walking through",
            "dark": "shadowy",
            "mysterious": "curious",
            "secret": "hidden",
            "whispered": "said quietly",
            "breathed": "spoke softly",
            "trembling": "nervous",
            "shivering": "cold",
            "passion": "excitement",
            "desire": "wish",
            "touched": "reached for",
            "embrace": "hug",
            "intimate": "close",
            "seductive": "appealing",
            "naked": "without clothes",
            "bare": "empty",
            "exposed": "visible",
            "flesh": "skin",
            "breast": "chest",
            "thigh": "leg",
            "sensual": "gentle",
            "erotic": "artistic",
            "climax": "peak",
            "penetrated": "entered",
            "thrust": "pushed",
            "moist": "damp",
            "wet": "damp",
            "hard": "firm",
            "soft": "gentle",
            "hot": "warm",
            "burning": "glowing",
            "fire": "light",
            "flame": "glow",
            "tight": "snug",
            "loose": "flowing",
            "strip": "remove",
            "stripped": "removed",
            "revealing": "showing",
            "body": "figure",
            "chest": "torso",
            "curves": "shape",
            "attractive": "pretty",
            "tempting": "appealing",
            "lust": "admiration",
            "arousing": "exciting",
            "stimulating": "interesting",
        }

        words_replaced = []
        for original_word, replacement in sanitization_words.items():
            if original_word in original_prompt.lower() and replacement in sanitized_prompt.lower():
                words_replaced.append(f"'{original_word}' → '{replacement}'")

        if words_replaced:
            changes.append(
                f"Word replacements: {', '.join(words_replaced[:3])}"
            )  # Limit to first 3

        # Check for safety additions
        safety_phrases = ["family-friendly", "safe for children", "innocent", "wholesome"]
        added_safety = [
            phrase
            for phrase in safety_phrases
            if phrase in sanitized_prompt and phrase not in original_prompt
        ]
        if added_safety:
            changes.append(f"Added safety terms: {', '.join(added_safety)}")

        # Check if prompt was completely rebuilt (attempt 2)
        if len(sanitized_prompt) < len(original_prompt) * 0.7:
            changes.append("Prompt completely rebuilt for safety")

        return changes


# Global instance
story_image_generator = StoryImageGenerator()
