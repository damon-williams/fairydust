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
        
        # Extract key visual elements and actions
        visual_description = self._analyze_scene_for_visuals(scene_description, characters)
        
        # If scene is too short, make it more descriptive
        if len(visual_description) < 50:
            visual_description = f"A scene from a children's story: {visual_description}"
        
        return visual_description.strip()[:300]  # Limit length for prompt
    
    def _identify_characters_in_scene(self, scene_text: str, characters: List[StoryCharacter]) -> List[StoryCharacter]:
        """Identify which characters are mentioned in this specific scene"""
        mentioned_characters = []
        scene_lower = scene_text.lower()
        
        for character in characters:
            if character.name.lower() in scene_lower:
                mentioned_characters.append(character)
        
        return mentioned_characters
    
    def _analyze_scene_for_visuals(self, scene_text: str, characters: List[StoryCharacter]) -> str:
        """Analyze scene text to extract meaningful visual elements and compose a focused description"""
        
        # Extract key visual elements
        locations = self._extract_locations(scene_text)
        actions = self._extract_actions(scene_text)
        emotions = self._extract_emotions(scene_text)
        objects = self._extract_objects(scene_text)
        time_of_day = self._extract_time_context(scene_text)
        weather = self._extract_weather(scene_text)
        
        # Build focused visual description
        description_parts = []
        
        # Start with main action or setting
        if actions:
            main_action = actions[0]  # Use most prominent action
            description_parts.append(main_action)
        elif locations:
            description_parts.append(f"A scene in {locations[0]}")
        else:
            description_parts.append("A children's story scene")
        
        # Add location context if not already included
        if locations and not any(loc.lower() in description_parts[0].lower() for loc in locations):
            description_parts.append(f"in {locations[0]}")
        
        # Add emotional context
        if emotions:
            description_parts.append(f"with {emotions[0]} mood")
        
        # Add environmental details
        environmental_details = []
        if time_of_day:
            environmental_details.append(time_of_day)
        if weather:
            environmental_details.append(weather)
        if objects:
            environmental_details.extend(objects[:2])  # Limit to 2 key objects
        
        if environmental_details:
            description_parts.append(f"featuring {', '.join(environmental_details)}")
        
        return ', '.join(description_parts)
    
    def _extract_locations(self, text: str) -> List[str]:
        """Extract location/setting information from text"""
        location_patterns = [
            r'\b(?:in|at|near|inside|outside|through|across|around)\s+(the\s+)?([a-zA-Z\s]{2,20}?)\b(?=\s|[,.])',
            r'\b(kitchen|bedroom|garden|park|forest|beach|school|playground|house|home|room|yard|field|mountain|lake|river|castle|cave|library|store|shop)\b',
            r'\b(outdoors?|indoors?|outside|inside)\b'
        ]
        
        locations = []
        text_lower = text.lower()
        
        for pattern in location_patterns:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    location = ' '.join([part for part in match if part and part != 'the']).strip()
                else:
                    location = match.strip()
                
                if location and len(location) > 2 and location not in locations:
                    locations.append(location)
        
        return locations[:3]  # Return top 3 locations
    
    def _extract_actions(self, text: str) -> List[str]:
        """Extract key actions and activities from text"""
        # Look for action verbs and activities
        action_patterns = [
            r'\b(walking|running|playing|dancing|singing|cooking|reading|writing|drawing|painting|building|climbing|jumping|swimming|flying|riding|driving|exploring|discovering|creating|making|finding|searching|looking|watching|laughing|smiling|hugging|celebrating)\b',
            r'\b(opened|closed|picked|grabbed|held|carried|threw|caught|pushed|pulled|lifted)\b',
            r'\b(?:was|were|is|are|began|started|continued)\s+(\w+ing)\b'
        ]
        
        actions = []
        text_lower = text.lower()
        
        for pattern in action_patterns:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            for match in matches:
                action = match if isinstance(match, str) else match[0] if match else ''
                if action and action not in actions:
                    actions.append(action)
        
        return actions[:3]  # Return top 3 actions
    
    def _extract_emotions(self, text: str) -> List[str]:
        """Extract emotional context from text"""
        emotion_patterns = [
            r'\b(happy|excited|joyful|cheerful|delighted|pleased|content|peaceful|calm|relaxed)\b',
            r'\b(curious|wonder|amazed|surprised|fascinated|intrigued)\b',
            r'\b(proud|confident|brave|determined|hopeful|optimistic)\b',
            r'\b(thoughtful|contemplative|focused|concentrated)\b',
            r'\b(playful|mischievous|adventurous|energetic)\b'
        ]
        
        emotions = []
        text_lower = text.lower()
        
        for pattern in emotion_patterns:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            for match in matches:
                if match not in emotions:
                    emotions.append(match)
        
        return emotions[:2]  # Return top 2 emotions
    
    def _extract_objects(self, text: str) -> List[str]:
        """Extract key objects and items from text"""
        object_patterns = [
            r'\b(book|toy|ball|flower|tree|cake|gift|present|bicycle|car|boat|airplane|castle|bridge|table|chair|bed|window|door|box|bag|hat|shoes|dress|shirt)s?\b',
            r'\b(magical?\s+\w+|special\s+\w+|beautiful\s+\w+|colorful\s+\w+|shiny\s+\w+|big\s+\w+|small\s+\w+|old\s+\w+|new\s+\w+)\b'
        ]
        
        objects = []
        text_lower = text.lower()
        
        for pattern in object_patterns:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            for match in matches:
                if match and len(match) > 2 and match not in objects:
                    objects.append(match)
        
        return objects[:4]  # Return top 4 objects
    
    def _extract_time_context(self, text: str) -> str:
        """Extract time of day context"""
        time_patterns = [
            r'\b(morning|afternoon|evening|night|dawn|dusk|sunset|sunrise|noon|midnight)\b',
            r'\b(early|late)\s+(morning|afternoon|evening|night)\b',
            r'\b(sunny|bright)\s+(day|morning|afternoon)\b'
        ]
        
        text_lower = text.lower()
        
        for pattern in time_patterns:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                return match.group(0)
        
        return ''
    
    def _extract_weather(self, text: str) -> str:
        """Extract weather context"""
        weather_patterns = [
            r'\b(sunny|cloudy|rainy|snowy|windy|stormy|foggy|misty|clear|bright)\b',
            r'\b(warm|hot|cold|cool|chilly)\b(?:\s+(?:day|weather|air))?',
            r'\b(rainbow|sunshine|clouds|rain|snow|wind|storm)\b'
        ]
        
        text_lower = text.lower()
        
        for pattern in weather_patterns:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                return match.group(0)
        
        return ''
    
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
        
        # Start with enhanced scene description
        prompt_parts = [scene_description]
        
        # Add character details with more descriptive context
        if characters_in_scene:
            character_details = []
            for char in characters_in_scene:
                char_desc = char.name
                if char.entry_type == "pet" and char.species:
                    char_desc += f" the {char.species}"
                elif char.relationship:
                    char_desc += f" ({char.relationship})"
                
                # Add character traits for visual context
                if char.traits:
                    relevant_traits = [trait for trait in char.traits[:2] if any(keyword in trait.lower() 
                                     for keyword in ['tall', 'short', 'curly', 'straight', 'blonde', 'brown', 'black', 'red', 'blue', 'green', 'happy', 'cheerful', 'kind', 'gentle'])]
                    if relevant_traits:
                        char_desc += f" ({', '.join(relevant_traits)})"
                
                character_details.append(char_desc)
            
            if len(character_details) == 1:
                prompt_parts.append(f"featuring {character_details[0]}")
            elif len(character_details) == 2:
                prompt_parts.append(f"featuring {character_details[0]} and {character_details[1]}")
            else:
                prompt_parts.append(f"featuring {', '.join(character_details[:-1])}, and {character_details[-1]}")
        
        # Combine parts
        prompt = ', '.join(prompt_parts)
        
        # Add audience-appropriate style context with more specific descriptors
        style_descriptors = []
        
        if target_audience in [TargetAudience.TODDLER, TargetAudience.PRESCHOOL]:
            style_descriptors.extend([
                "children's picture book illustration",
                "very colorful and bright", 
                "simple and clear",
                "friendly and welcoming",
                "safe for toddlers"
            ])
        elif target_audience in [TargetAudience.EARLY_ELEMENTARY, TargetAudience.LATE_ELEMENTARY]:
            style_descriptors.extend([
                "children's book illustration",
                "colorful and engaging",
                "detailed but age-appropriate",
                "adventurous and fun",
                "family-friendly"
            ])
        elif target_audience == TargetAudience.TEEN:
            style_descriptors.extend([
                "young adult book illustration",
                "dynamic and modern",
                "sophisticated but relatable",
                "contemporary art style",
                "teen-appropriate"
            ])
        
        # Add technical quality enhancers
        style_descriptors.extend([
            "high quality digital art",
            "professional illustration",
            "storybook style",
            "detailed and expressive",
            "warm and inviting lighting"
        ])
        
        # Combine with scene prompt
        final_prompt = f"{prompt}, {', '.join(style_descriptors)}"
        
        return final_prompt
    
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