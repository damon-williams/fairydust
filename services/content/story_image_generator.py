"""Background image generation for stories"""

import asyncio
import json
import logging
import traceback
from typing import List, Optional
from uuid import UUID

from image_generation_service import image_generation_service
from image_storage_service import image_storage_service
from models import StoryCharacter, TargetAudience, ImageStyle, ImageSize
from shared.database import Database, get_db
from story_image_service import story_image_service

logger = logging.getLogger(__name__)


class StoryImageGenerator:
    """Handles background generation of images for stories"""
    
    def __init__(self):
        pass
    
    async def generate_story_images_background(
        self,
        story_id: str,
        user_id: str,
        scenes: List[dict],
        characters: List[StoryCharacter],
        target_audience: TargetAudience,
        db: Database
    ):
        """Background task to generate all images for a story"""
        
        try:
            logger.info(f"🎨 Starting background image generation for story {story_id}")
            logger.info(f"   Scenes to generate: {len(scenes)}")
            logger.info(f"   Characters available: {len(characters)}")
            
            # Insert initial records for all images
            for scene in scenes:
                await self._create_story_image_record(
                    db, story_id, user_id, scene
                )
            
            # Generate images one by one
            completed_count = 0
            for scene in scenes:
                try:
                    await self._generate_single_image(
                        db, story_id, user_id, scene, characters, target_audience
                    )
                    completed_count += 1
                    logger.info(f"✅ Generated image {completed_count}/{len(scenes)} for story {story_id}")
                    
                except Exception as e:
                    logger.error(f"❌ Failed to generate image {scene['image_id']} for story {story_id}: {e}")
                    logger.error(f"   Exception traceback: {traceback.format_exc()}")
                    
                    # Mark image as failed
                    await self._mark_image_failed(db, story_id, scene['image_id'], str(e))
            
            # Update story completion status
            images_complete = completed_count == len(scenes)
            await self._update_story_completion_status(db, story_id, images_complete)
            
            logger.info(f"🎯 Completed background image generation for story {story_id}")
            logger.info(f"   Success rate: {completed_count}/{len(scenes)} images")
            
        except Exception as e:
            logger.error(f"💥 Critical error in background image generation for story {story_id}: {e}")
            logger.error(f"   Exception traceback: {traceback.format_exc()}")
            
            # Mark story as having incomplete images
            try:
                await self._update_story_completion_status(db, story_id, False)
            except Exception as cleanup_error:
                logger.error(f"Failed to update story completion status: {cleanup_error}")
    
    async def _create_story_image_record(
        self, 
        db: Database, 
        story_id: str, 
        user_id: str, 
        scene: dict
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
            scene['image_id'],
            scene['scene_description'],  # Initial prompt
            scene['scene_description'],
            'pending'
        )
        
        logger.debug(f"📝 Created story image record: {scene['image_id']}")
    
    async def _generate_single_image(
        self,
        db: Database,
        story_id: str,
        user_id: str,
        scene: dict,
        characters: List[StoryCharacter],
        target_audience: TargetAudience
    ):
        """Generate a single image for a story scene"""
        
        image_id = scene['image_id']
        
        try:
            # Update status to generating
            await db.execute(
                "UPDATE story_images SET status = $1, updated_at = CURRENT_TIMESTAMP WHERE story_id = $2 AND image_id = $3",
                'generating', story_id, image_id
            )
            
            # Determine characters in this scene
            characters_in_scene = scene.get('characters_mentioned', [])
            
            # Generate optimized prompt
            enhanced_prompt = story_image_service.generate_image_prompt(
                scene['scene_description'],
                characters_in_scene,
                target_audience
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
                        char_descriptions = [f"{char.name} ({char.relationship})" for char in remaining_characters]
                        enhanced_prompt += f", also featuring {', '.join(char_descriptions)}"
            
            # Update prompt in database
            await db.execute(
                "UPDATE story_images SET prompt = $1 WHERE story_id = $2 AND image_id = $3",
                enhanced_prompt, story_id, image_id
            )
            
            logger.info(f"🎨 Generating image {image_id}")
            logger.info(f"   Prompt: {enhanced_prompt[:100]}...")
            logger.info(f"   Reference people: {len(reference_people)}")
            
            # Generate image using existing service
            image_url, generation_metadata = await image_generation_service.generate_image(
                enhanced_prompt,
                ImageStyle.CARTOON,  # Default to cartoon for stories
                ImageSize.STANDARD,
                reference_people
            )
            
            # Store image in R2
            stored_url, file_size, dimensions = await image_storage_service.store_generated_image(
                image_url,
                user_id,
                image_id
            )
            
            # Prepare full metadata
            full_metadata = {
                **generation_metadata,
                "file_size_bytes": file_size,
                "dimensions": dimensions,
                "characters_in_scene": [char.name for char in characters_in_scene],
                "reference_people_count": len(reference_people)
            }
            
            # Update database with completed image
            await db.execute(
                """
                UPDATE story_images 
                SET url = $1, status = $2, generation_metadata = $3, updated_at = CURRENT_TIMESTAMP
                WHERE story_id = $4 AND image_id = $5
                """,
                stored_url,
                'completed',
                json.dumps(full_metadata),
                story_id,
                image_id
            )
            
            logger.info(f"✅ Successfully generated and stored image {image_id}")
            
        except Exception as e:
            logger.error(f"❌ Failed to generate image {image_id}: {e}")
            logger.error(f"   Exception traceback: {traceback.format_exc()}")
            raise  # Re-raise to be caught by caller
    
    async def _mark_image_failed(self, db: Database, story_id: str, image_id: str, error_message: str):
        """Mark an image as failed in the database"""
        
        try:
            error_metadata = {
                "error": error_message,
                "failed_at": "background_generation"
            }
            
            await db.execute(
                """
                UPDATE story_images 
                SET status = $1, generation_metadata = $2, updated_at = CURRENT_TIMESTAMP
                WHERE story_id = $3 AND image_id = $4
                """,
                'failed',
                json.dumps(error_metadata),
                story_id,
                image_id
            )
            
        except Exception as e:
            logger.error(f"Failed to mark image {image_id} as failed: {e}")
    
    async def _update_story_completion_status(self, db: Database, story_id: str, images_complete: bool):
        """Update the story's image completion status"""
        
        try:
            await db.execute(
                "UPDATE user_stories SET images_complete = $1 WHERE id = $2",
                images_complete,
                story_id
            )
            
            logger.info(f"📊 Updated story {story_id} images_complete = {images_complete}")
            
        except Exception as e:
            logger.error(f"Failed to update story completion status: {e}")


# Global instance
story_image_generator = StoryImageGenerator()