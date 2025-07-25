"""Story image extraction and scene identification service"""

import asyncio
import json
import re
import uuid
from typing import List, Optional, Tuple

from models import StoryCharacter, StoryLength, TargetAudience, ImageReferencePerson, ImageStyle, ImageSize

# Image counts by story length
IMAGE_COUNTS = {
    StoryLength.QUICK: 2,
    StoryLength.MEDIUM: 3,
    StoryLength.LONG: 4
}


class StoryImageService:
    """Service for extracting scenes and generating images for stories"""
    
    def __init__(self):
        pass
    
    def extract_image_scenes(
        self, 
        story_content: str, 
        story_length: StoryLength, 
        characters: List[StoryCharacter]
    ) -> List[dict]:
        """Extract key scenes from story for image generation"""
        
        image_count = IMAGE_COUNTS[story_length]
        
        # Split story into paragraphs/sections
        paragraphs = [p.strip() for p in story_content.split('\n\n') if p.strip()]
        
        if len(paragraphs) < image_count:
            # If story has fewer paragraphs than needed images, use what we have
            placement_points = list(range(len(paragraphs)))
        else:
            # Distribute images evenly throughout story
            placement_points = self._distribute_evenly(len(paragraphs), image_count)
        
        scenes = []
        for i, point in enumerate(placement_points):
            # Extract context around placement point for better scene understanding
            context_start = max(0, point - 1)
            context_end = min(len(paragraphs), point + 2)
            scene_context = ' '.join(paragraphs[context_start:context_end])
            
            # Generate scene description and prompt
            scene_description = self._extract_visual_elements(scene_context, characters)
            image_id = f"img_{uuid.uuid4().hex[:8]}"
            
            scenes.append({
                "image_id": image_id,
                "position": point,
                "scene_description": scene_description,
                "context": scene_context[:500],  # Keep context for debugging
                "characters_mentioned": self._identify_characters_in_scene(scene_context, characters)
            })
        
        return scenes
    
    def _distribute_evenly(self, total_paragraphs: int, image_count: int) -> List[int]:
        """Distribute image placement points evenly throughout the story"""
        if image_count == 1:
            return [total_paragraphs // 2]
        
        # Calculate spacing between images
        spacing = total_paragraphs / (image_count + 1)
        
        placement_points = []
        for i in range(1, image_count + 1):
            point = int(spacing * i)
            # Ensure we don't exceed bounds
            point = min(point, total_paragraphs - 1)
            placement_points.append(point)
        
        return placement_points
    
    def _extract_visual_elements(self, scene_text: str, characters: List[StoryCharacter]) -> str:
        """Extract visual elements from scene text to create image description"""
        
        # Start with the scene content, cleaned up
        scene_description = scene_text.strip()
        
        # Remove dialogue markers and clean up
        scene_description = re.sub(r'"[^"]*"', '', scene_description)  # Remove dialogue
        scene_description = re.sub(r'\s+', ' ', scene_description)  # Normalize whitespace
        scene_description = scene_description[:300]  # Limit length for prompt
        
        # If scene is too short, make it more descriptive
        if len(scene_description) < 50:
            scene_description = f"A scene from a children's story: {scene_description}"
        
        return scene_description.strip()
    
    def _identify_characters_in_scene(self, scene_text: str, characters: List[StoryCharacter]) -> List[StoryCharacter]:
        """Identify which characters are mentioned in this specific scene"""
        mentioned_characters = []
        scene_lower = scene_text.lower()
        
        for character in characters:
            if character.name.lower() in scene_lower:
                mentioned_characters.append(character)
        
        return mentioned_characters
    
    def insert_image_markers(self, story_content: str, scenes: List[dict]) -> str:
        """Insert image markers into story content at appropriate positions"""
        
        paragraphs = story_content.split('\n\n')
        
        # Sort scenes by position (reverse order to maintain indices)
        sorted_scenes = sorted(scenes, key=lambda x: x['position'], reverse=True)
        
        for scene in sorted_scenes:
            position = scene['position']
            image_marker = f"\n\n[IMAGE:{scene['image_id']}]\n\n"
            
            # Insert marker after the paragraph at this position
            if position < len(paragraphs):
                paragraphs[position] += image_marker
        
        return '\n\n'.join(paragraphs)
    
    def generate_image_prompt(
        self, 
        scene_description: str, 
        characters_in_scene: List[StoryCharacter], 
        target_audience: TargetAudience
    ) -> str:
        """Generate Replicate-optimized prompt from scene description"""
        
        # Base scene description
        prompt = scene_description
        
        # Add character details if present
        if characters_in_scene:
            character_details = []
            for char in characters_in_scene:
                char_description = f"{char.name}"
                if char.relationship:
                    char_description += f" ({char.relationship})"
                character_details.append(char_description)
            
            if len(character_details) == 1:
                prompt += f", featuring {character_details[0]}"
            else:
                prompt += f", featuring {', '.join(character_details[:-1])} and {character_details[-1]}"
        
        # Add audience-appropriate style context
        if target_audience == TargetAudience.KIDS:
            prompt += ", children's book illustration, colorful, friendly, safe for children"
        elif target_audience == TargetAudience.TEEN:
            prompt += ", young adult book illustration, dynamic, modern, teen-appropriate, relatable style"
        else:  # adults
            prompt += ", detailed illustration, sophisticated art style, narrative illustration"
        
        # Add quality enhancers for Replicate
        prompt += ", high quality, detailed illustration, professional artwork, storybook style"
        
        return prompt
    
    def prepare_reference_people(
        self, 
        characters_in_scene: List[StoryCharacter], 
        user_id: str
    ) -> List[ImageReferencePerson]:
        """Prepare character references for image generation (smart 3-person limit)"""
        
        reference_people = []
        
        for character in characters_in_scene[:3]:  # Limit to 3 for Gen-4 model
            # Use photo URL from My People if available
            if character.photo_url:
                print(f"📸 STORY_IMAGE: Using photo reference for {character.name} - {character.photo_url}")
                reference_people.append(ImageReferencePerson(
                    person_id=character.person_id or uuid.uuid4(),  # Use actual person_id if available
                    photo_url=character.photo_url,
                    description=f"{character.name} ({character.relationship})"
                ))
            else:
                print(f"📝 STORY_IMAGE: No photo available for {character.name} - will use text description only")
        
        print(f"📸 STORY_IMAGE: Prepared {len(reference_people)} photo references out of {len(characters_in_scene)} characters")
        return reference_people
    
    def select_most_important_characters(
        self, 
        characters: List[StoryCharacter], 
        limit: int = 3
    ) -> List[StoryCharacter]:
        """Select most important characters for image reference (when > 3 characters)"""
        
        # Priority order: parents, family, friends, others
        priority_relationships = [
            'mother', 'mom', 'father', 'dad', 'parent',
            'sister', 'brother', 'sibling', 'grandmother', 'grandfather', 'grandma', 'grandpa',
            'aunt', 'uncle', 'cousin', 'family',
            'friend', 'best friend'
        ]
        
        prioritized_characters = []
        remaining_characters = characters.copy()
        
        # First, add characters by relationship priority
        for priority_rel in priority_relationships:
            for char in remaining_characters:
                if char.relationship and priority_rel in char.relationship.lower():
                    prioritized_characters.append(char)
                    remaining_characters.remove(char)
                    if len(prioritized_characters) >= limit:
                        break
            if len(prioritized_characters) >= limit:
                break
        
        # Fill remaining slots with other characters
        while len(prioritized_characters) < limit and remaining_characters:
            prioritized_characters.append(remaining_characters.pop(0))
        
        return prioritized_characters[:limit]


# Global instance
story_image_service = StoryImageService()