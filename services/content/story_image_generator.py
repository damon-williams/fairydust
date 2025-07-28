"""Background image generation for stories"""

import asyncio
import json
import logging
import traceback

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

        try:
            logger.info(f"🚀 Starting PARALLEL background image generation for story {story_id}")
            logger.info(f"   Scenes to generate: {len(scenes)}")
            logger.info(f"   Characters available: {len(characters)}")

            # Insert initial records for all images
            for scene in scenes:
                await self._create_story_image_record(db, story_id, user_id, scene)

            # Generate all images in parallel
            logger.info(f"⚡ Starting parallel generation of {len(scenes)} images...")
            
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
                    name=f"generate_image_{scene['image_id']}"
                )
                generation_tasks.append(task)

            # Wait for all images to complete (or fail)
            results = await asyncio.gather(*generation_tasks, return_exceptions=True)
            
            # Count successful generations
            completed_count = 0
            failed_count = 0
            
            for i, result in enumerate(results):
                scene = scenes[i]
                if isinstance(result, Exception):
                    failed_count += 1
                    logger.error(
                        f"❌ Failed to generate image {scene['image_id']} for story {story_id}: {result}"
                    )
                elif result is True:  # Success
                    completed_count += 1
                    logger.info(f"✅ Successfully generated image {scene['image_id']} for story {story_id}")
                else:
                    # result is False (handled failure)
                    failed_count += 1

            # Update story completion status
            images_complete = completed_count == len(scenes)
            await self._update_story_completion_status(db, story_id, images_complete)

            total_time_saved = f"Parallel generation completed!"
            logger.info(f"🎯 {total_time_saved}")
            logger.info(f"   Success rate: {completed_count}/{len(scenes)} images")
            logger.info(f"   Failed: {failed_count} images")
            
            if completed_count > 0:
                logger.info(f"⚡ PERFORMANCE: Generated {completed_count} images simultaneously instead of sequentially")

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
        
        image_id = scene["image_id"]
        
        try:
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
            return True  # Success
            
        except Exception as e:
            logger.error(f"❌ Failed to generate image {image_id} for story {story_id}: {e}")
            logger.error(f"   Exception traceback: {traceback.format_exc()}")

            # Mark image as failed
            try:
                await self._mark_image_failed(db, story_id, image_id, str(e))
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

        image_id = scene["image_id"]

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
            image_url, generation_metadata = await self._generate_image_with_retry(
                enhanced_prompt, scene, characters_in_scene, target_audience, reference_people
            )

            # Store image in R2
            stored_url, file_size, dimensions = await image_storage_service.store_generated_image(
                image_url, user_id, image_id
            )

            # Prepare full metadata
            full_metadata = {
                **generation_metadata,
                "file_size_bytes": file_size,
                "dimensions": dimensions,
                "characters_in_scene": [char.name for char in characters_in_scene],
                "reference_people_count": len(reference_people),
            }

            # Update database with completed image
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

            logger.info(f"✅ Successfully generated and stored image {image_id}")

        except Exception as e:
            logger.error(f"❌ Failed to generate image {image_id}: {e}")
            logger.error(f"   Exception traceback: {traceback.format_exc()}")
            raise  # Re-raise to be caught by caller

    async def _mark_image_failed(
        self, db: Database, story_id: str, image_id: str, error_message: str
    ):
        """Mark an image as failed in the database"""

        try:
            error_metadata = {"error": error_message, "failed_at": "background_generation"}

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

        nsfw_failure_detected = False

        for attempt in range(max_retries):
            try:
                prompt_to_use = original_prompt

                if attempt > 0 and nsfw_failure_detected:
                    # Only sanitize prompt if previous failure was NSFW-related
                    prompt_to_use = self._sanitize_prompt_for_retry(
                        original_prompt, scene, characters_in_scene, target_audience, attempt
                    )
                    logger.info(f"🔄 RETRY {attempt}: Using sanitized prompt:")
                    logger.info(f"   FULL SANITIZED PROMPT: {prompt_to_use}")
                else:
                    logger.info(f"🎯 ATTEMPT {attempt + 1}: Using original prompt:")
                    logger.info(f"   FULL ORIGINAL PROMPT: {prompt_to_use}")

                # Try to generate with current prompt
                image_url, generation_metadata = await image_generation_service.generate_image(
                    prompt_to_use,
                    ImageStyle.CARTOON,  # Default to cartoon for stories
                    ImageSize.STANDARD,
                    reference_people,
                )

                # Success!
                if attempt > 0:
                    logger.info(f"✅ RETRY SUCCESS: Generated image after {attempt + 1} attempts")

                return image_url, generation_metadata

            except Exception as e:
                error_msg = str(e).lower()

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
                            f"⚠️ NSFW detected on attempt {attempt + 1}, retrying with sanitized prompt..."
                        )
                        logger.warning(f"   Original prompt that triggered flag: {prompt_to_use}")
                        logger.warning(f"   Full error message: {str(e)}")
                        continue
                    else:
                        logger.error(f"❌ All {max_retries} attempts failed due to NSFW detection")
                        raise Exception(
                            f"Image generation failed after {max_retries} attempts: NSFW content detected"
                        )

                # Check for transient Replicate errors (these can be retried without changing prompt)
                elif (
                    "internal.bad_output" in error_msg
                    or "unexpected error occurred" in error_msg
                    or "timeout" in error_msg
                    or "service unavailable" in error_msg
                    or "temporarily unavailable" in error_msg
                    or "rate limit" in error_msg
                    or "queue full" in error_msg
                ):
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"⚠️ Transient Replicate error on attempt {attempt + 1}, retrying without prompt changes..."
                        )
                        logger.warning(f"   Error: {error_msg}")
                        # Add a small delay for transient errors to avoid rate limits
                        await asyncio.sleep(2**attempt)  # Exponential backoff: 1s, 2s, 4s
                        continue
                    else:
                        logger.error(f"❌ All {max_retries} attempts failed due to transient errors")
                        raise Exception(
                            f"Image generation failed after {max_retries} attempts: {error_msg}"
                        )
                else:
                    # Other errors (likely permanent), don't retry
                    logger.error(f"❌ Non-retryable error: {e}")
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


# Global instance
story_image_generator = StoryImageGenerator()
