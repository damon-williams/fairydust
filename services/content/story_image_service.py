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
        """Extract key scenes from story for image generation with proper image count"""
        
        image_count = IMAGE_COUNTS[story_length]
        print(f"🎨 IMAGE_EXTRACTION: Expected {image_count} images for {story_length.value} story", flush=True)
        
        # Split story into paragraphs/sections
        paragraphs = [p.strip() for p in story_content.split('\n\n') if p.strip()]
        print(f"🎨 IMAGE_EXTRACTION: Found {len(paragraphs)} paragraphs in story", flush=True)
        
        if len(paragraphs) < image_count:
            # If story has fewer paragraphs than needed images, use what we have
            placement_points = list(range(len(paragraphs)))
            print(f"⚠️ IMAGE_EXTRACTION: Only {len(paragraphs)} paragraphs available, using all of them", flush=True)
        else:
            # Distribute images evenly throughout story
            placement_points = self._distribute_evenly(len(paragraphs), image_count)
            print(f"✅ IMAGE_EXTRACTION: Distributing {image_count} images at positions: {placement_points}", flush=True)
        
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
            
            print(f"🎨 IMAGE_EXTRACTION: Created scene {i+1}/{len(placement_points)} at position {point} with ID {image_id}", flush=True)
        
        print(f"✅ IMAGE_EXTRACTION: Generated {len(scenes)} image scenes total", flush=True)
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
        """Extract visual elements from scene text while preserving actual story content"""
        
        # Start with the actual scene content
        scene_description = scene_text.strip()
        
        # Clean up dialogue but preserve the story narrative
        # Replace dialogue with narrative markers to maintain story flow
        scene_description = re.sub(r'"([^"]+)"', r'speaking', scene_description)
        scene_description = re.sub(r'\s+', ' ', scene_description)  # Normalize whitespace
        
        # Instead of replacing the story content, enhance it with visual details
        visual_elements = self._analyze_scene_for_visuals(scene_description, characters)
        
        # Combine the actual story content with visual enhancements
        if len(scene_description) > 250:
            # For longer scenes, use the story content directly but add visual enhancements
            story_content = scene_description[:250].rsplit(' ', 1)[0]  # Cut at word boundary
            enhanced_description = f"{story_content}, {visual_elements}"
        else:
            # For shorter scenes, use full content plus visual elements
            enhanced_description = f"{scene_description}, {visual_elements}"
        
        # Remove redundant phrases to avoid repetition
        enhanced_description = self._clean_redundant_phrases(enhanced_description)
        
        return enhanced_description.strip()[:450]  # Increased limit to include more story content
    
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
    
    def _clean_redundant_phrases(self, text: str) -> str:
        """Remove redundant or repeated phrases from the enhanced description"""
        
        # Split into parts and remove duplicates while preserving order
        parts = [part.strip() for part in text.split(',')]
        unique_parts = []
        seen_concepts = set()
        
        for part in parts:
            # Check if this concept has already been mentioned
            part_lower = part.lower()
            is_duplicate = False
            
            for seen in seen_concepts:
                # Check for substantial overlap (more than just common words)
                common_words = set(part_lower.split()) & set(seen.split())
                significant_words = {word for word in common_words if len(word) > 3}
                
                if len(significant_words) >= 2:  # At least 2 significant words in common
                    is_duplicate = True
                    break
            
            if not is_duplicate and part.strip():
                unique_parts.append(part)
                seen_concepts.add(part_lower)
        
        return ', '.join(unique_parts)
    
    def insert_image_markers(self, story_content: str, scenes: List[dict]) -> str:
        """Insert image markers into story content at appropriate positions"""
        
        paragraphs = story_content.split('\n\n')
        print(f"🖼️ IMAGE_MARKERS: Inserting {len(scenes)} image markers into {len(paragraphs)} paragraphs", flush=True)
        
        # Sort scenes by position (reverse order to maintain indices)
        sorted_scenes = sorted(scenes, key=lambda x: x['position'], reverse=True)
        
        for scene in sorted_scenes:
            position = scene['position']
            image_marker = f"\n\n[IMAGE:{scene['image_id']}]\n\n"
            
            # Insert marker after the paragraph at this position
            if position < len(paragraphs):
                print(f"🖼️ IMAGE_MARKERS: Inserting {scene['image_id']} after paragraph {position}", flush=True)
                paragraphs[position] += image_marker
            else:
                print(f"⚠️ IMAGE_MARKERS: Position {position} is out of range for {len(paragraphs)} paragraphs", flush=True)
        
        result = '\n\n'.join(paragraphs)
        marker_count = result.count('[IMAGE:')
        print(f"✅ IMAGE_MARKERS: Final content has {marker_count} image markers", flush=True)
        
        return result
    
    def generate_image_prompt(
        self, 
        scene_description: str, 
        characters_in_scene: List[StoryCharacter], 
        target_audience: TargetAudience
    ) -> str:
        """Generate Replicate-optimized prompt from scene description with actual story content"""
        
        # The scene_description now contains actual story content - use it as the primary prompt
        prompt_parts = []
        
        # Clean and optimize the story content for image generation
        cleaned_scene = self._prepare_scene_for_image_prompt(scene_description)
        prompt_parts.append(cleaned_scene)
        
        # Add character details - essential for proper character rendering
        if characters_in_scene:
            character_details = []
            for char in characters_in_scene:
                # Build comprehensive character description for image generation
                char_desc_parts = [char.name]
                
                # Always include species/type information for non-human characters
                if char.entry_type == "pet" and char.species:
                    char_desc_parts.append(f"the {char.species}")
                elif char.entry_type == "pet" or self._is_animal_character(char):
                    # Try to determine animal type from relationship or traits
                    animal_type = self._extract_animal_type(char)
                    if animal_type:
                        char_desc_parts.append(f"the {animal_type}")
                    else:
                        char_desc_parts.append("the animal")
                
                # Add relationship context if it provides important character info
                if char.relationship:
                    relationship_lower = char.relationship.lower()
                    # For custom characters, the relationship might contain the full description
                    if char.entry_type != "pet" and relationship_lower not in ['person', 'character', 'friend']:
                        # Check if relationship contains a character description
                        if any(desc_word in relationship_lower for desc_word in ['helps', 'magical', 'special', 'who', 'that']):
                            # This looks like a character description, include it
                            char_desc_parts.append(f"({char.relationship})")
                        elif len(char.relationship.split()) <= 2:
                            # Short relationship, likely a title
                            char_desc_parts.append(f"({char.relationship})")
                    elif char.entry_type == "pet" and not char.species:
                        # For pets without species, check if relationship has type info
                        animal_type = self._extract_animal_type(char)
                        if not animal_type and len(char.relationship.split()) > 1:
                            # Relationship might contain the full description
                            char_desc_parts.append(f"({char.relationship})")
                
                # Always include relevant traits/descriptions for visual context
                if char.traits:
                    # Separate physical traits from personality traits
                    physical_traits = []
                    character_traits = []
                    
                    for trait in char.traits[:5]:  # Use more traits for better descriptions
                        trait_lower = trait.lower()
                        # Physical appearance traits
                        if any(keyword in trait_lower for keyword in 
                              ['tall', 'short', 'curly', 'straight', 'blonde', 'brown', 'black', 'red', 'blue', 'green', 
                               'long', 'fluffy', 'striped', 'spotted', 'white', 'gray', 'orange', 'golden', 'dark']):
                            physical_traits.append(trait)
                        # Important character-defining traits (especially for fantasy characters)
                        elif any(keyword in trait_lower for keyword in 
                                ['magical', 'mystical', 'wise', 'ancient', 'enchanted', 'flying', 'glowing', 
                                 'dream', 'helps', 'heals', 'protects', 'guides', 'special', 'powerful', 'spirit']):
                            character_traits.append(trait)
                        # Behavioral traits that affect appearance
                        elif any(keyword in trait_lower for keyword in 
                                ['gentle', 'fierce', 'calm', 'energetic', 'mysterious', 'bright', 'sleepy', 'kind']):
                            character_traits.append(trait)
                        # Include any trait that contains descriptive phrases (like full descriptions)
                        elif len(trait.split()) > 2:  # Multi-word descriptions
                            character_traits.append(trait)
                    
                    # Add the most important traits to the description
                    important_traits = physical_traits[:2] + character_traits[:2]
                    if important_traits:
                        char_desc_parts.append(f"({', '.join(important_traits)})")
                
                # Combine into full character description
                full_char_desc = ' '.join(char_desc_parts)
                character_details.append(full_char_desc)
            
            # Always add character details for proper image generation
            if character_details:
                if len(character_details) == 1:
                    prompt_parts.append(f"featuring {character_details[0]}")
                elif len(character_details) == 2:
                    prompt_parts.append(f"featuring {character_details[0]} and {character_details[1]}")
                else:
                    prompt_parts.append(f"featuring {', '.join(character_details[:-1])}, and {character_details[-1]}")
        
        # Combine the story content with any enhancements
        story_prompt = ', '.join(prompt_parts)
        
        # Add concise, audience-appropriate style context
        style_descriptors = []
        
        if target_audience in [TargetAudience.TODDLER, TargetAudience.PRESCHOOL]:
            style_descriptors.extend([
                "children's picture book illustration",
                "bright and colorful", 
                "simple and friendly",
                "safe for toddlers"
            ])
        elif target_audience in [TargetAudience.EARLY_ELEMENTARY, TargetAudience.LATE_ELEMENTARY]:
            style_descriptors.extend([
                "children's book illustration",
                "colorful and engaging",
                "age-appropriate detail",
                "family-friendly"
            ])
        elif target_audience == TargetAudience.TEEN:
            style_descriptors.extend([
                "young adult illustration",
                "dynamic and modern",
                "teen-appropriate style"
            ])
        
        # Essential quality descriptors (keep minimal to preserve story content)
        style_descriptors.extend([
            "high quality illustration",
            "professional storybook art",
            "warm lighting"
        ])
        
        # Combine story content with style (prioritizing story content)
        final_prompt = f"{story_prompt}, {', '.join(style_descriptors)}"
        
        # Ensure we don't exceed prompt limits while preserving story content
        if len(final_prompt) > 500:
            # Reduce style descriptors before reducing story content
            reduced_styles = style_descriptors[:4]
            final_prompt = f"{story_prompt}, {', '.join(reduced_styles)}"
        
        return final_prompt
    
    def _prepare_scene_for_image_prompt(self, scene_text: str) -> str:
        """Prepare scene text specifically for image generation prompts"""
        
        # Clean up text for image generation while preserving story content
        cleaned = scene_text.strip()
        
        # Convert first-person narrative to third-person for better image generation
        cleaned = re.sub(r'\bI\b', 'the main character', cleaned)
        cleaned = re.sub(r'\bmy\b', 'their', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\bme\b', 'them', cleaned)
        
        # Remove internal thoughts that don't translate to visuals
        cleaned = re.sub(r'\bthought about\b.*?[.,]', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\bwondered if\b.*?[.,]', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\bremembered that\b.*?[.,]', '', cleaned, flags=re.IGNORECASE)
        
        # Clean up excessive modifiers
        cleaned = re.sub(r'\bvery\s+very\b', 'very', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\breally\s+really\b', 'really', cleaned, flags=re.IGNORECASE)
        
        # Clean up whitespace and punctuation
        cleaned = re.sub(r'\s+', ' ', cleaned)
        cleaned = re.sub(r'[,.]?\s*,', ',', cleaned)  # Remove double commas
        cleaned = re.sub(r'^\s*,\s*', '', cleaned)  # Remove leading comma
        
        return cleaned.strip()
    
    def _is_animal_character(self, char: StoryCharacter) -> bool:
        """Determine if a character is an animal based on relationship or traits"""
        if not char.relationship and not char.traits:
            return False
        
        # Check relationship field for animal indicators
        relationship_lower = char.relationship.lower() if char.relationship else ""
        animal_indicators = ['cat', 'dog', 'bird', 'fish', 'rabbit', 'hamster', 'horse', 'dragon', 'unicorn', 'phoenix', 'wolf', 'bear', 'fox', 'owl', 'eagle', 'turtle', 'frog', 'lion', 'tiger', 'elephant', 'magical creature', 'mythical']
        
        if any(animal in relationship_lower for animal in animal_indicators):
            return True
        
        # Check traits for animal/magical creature indicators
        traits_text = ' '.join(char.traits).lower() if char.traits else ""
        animal_trait_indicators = ['fur', 'feathers', 'scales', 'paws', 'claws', 'tail', 'wings', 'flies', 'purrs', 'barks', 'chirps', 'roars', 'magical', 'enchanted', 'spirit animal', 'creature']
        
        return any(indicator in traits_text for indicator in animal_trait_indicators)
    
    def _extract_animal_type(self, char: StoryCharacter) -> Optional[str]:
        """Extract animal type from character relationship or traits"""
        # Common animals to look for
        animals = ['cat', 'dog', 'bird', 'fish', 'rabbit', 'hamster', 'horse', 'dragon', 'unicorn', 'phoenix', 'wolf', 'bear', 'fox', 'owl', 'eagle', 'turtle', 'frog', 'lion', 'tiger', 'elephant']
        
        # Check relationship field first
        if char.relationship:
            relationship_lower = char.relationship.lower()
            for animal in animals:
                if animal in relationship_lower:
                    return animal
        
        # Check traits
        if char.traits:
            traits_text = ' '.join(char.traits).lower()
            for animal in animals:
                if animal in traits_text:
                    return animal
            
            # Check for specific animal breed patterns
            if 'golden retriever' in traits_text:
                return 'golden retriever dog'
            elif 'tabby' in traits_text:
                return 'tabby cat'
            elif 'siamese' in traits_text:
                return 'siamese cat'
            elif 'persian' in traits_text:
                return 'persian cat'
            elif 'husky' in traits_text:
                return 'husky dog'
            elif 'beagle' in traits_text:
                return 'beagle dog'
        
        return None
    
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