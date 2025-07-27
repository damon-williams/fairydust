"""Multi-Agent Image Prompt Generation System

This module implements a sophisticated 4-agent system for generating high-quality
image prompts from story content. Each agent specializes in a specific aspect:

1. Scene Intelligence Agent: Deep story context understanding
2. Character Rendering Agent: Detailed character descriptions
3. Visual Composition Agent: Structured image prompt creation
4. Quality Enhancement Agent: Final prompt refinement and validation

The system replaces the previous rule-based approach with AI-powered analysis
for dramatically improved prompt quality and story-image alignment.
"""

import json
import logging
import re
import uuid
from typing import Optional
from uuid import UUID

from langsmith import traceable
from models import StoryCharacter, TargetAudience

from shared.llm_client import llm_client

logger = logging.getLogger(__name__)


class MultiAgentImageService:
    """Multi-agent system for generating contextually rich image prompts from stories"""

    def __init__(self):
        # LLM configuration for different agent types
        self.analysis_config = {
            "provider": "anthropic",
            "model": "claude-3-5-haiku-20241022",
            "parameters": {
                "temperature": 0.3,  # Lower temperature for analytical tasks
                "max_tokens": 400,  # Increased for detailed scene analysis
                "top_p": 0.9,
            },
        }

        self.creative_config = {
            "provider": "anthropic",
            "model": "claude-3-5-haiku-20241022",
            "parameters": {
                "temperature": 0.7,  # Higher temperature for creative tasks
                "max_tokens": 300,  # Increased for detailed creative outputs
                "top_p": 0.9,
            },
        }

    @traceable(run_type="chain", name="4-agent-image-prompt-generation")
    async def generate_image_prompt(
        self,
        scene_description: str,
        characters_in_scene: list[StoryCharacter],
        target_audience: TargetAudience,
        user_id: Optional[UUID] = None,
        story_context: Optional[str] = None,
        story_theme: Optional[str] = None,
        story_genre: Optional[str] = None,
        full_story_content: Optional[str] = None,
    ) -> str:
        """
        Generate a high-quality image prompt using the 4-agent system

        Args:
            scene_description: Raw story content for this scene
            characters_in_scene: Characters detected in this scene
            target_audience: Age group for the story
            user_id: User ID for LLM usage tracking
            story_context: Additional story context if available

        Returns:
            Rich, contextually accurate image prompt
        """

        # Add metadata for LangSmith tracing
        metadata = {
            "scene_length": len(scene_description),
            "character_count": len(characters_in_scene),
            "character_names": [char.name for char in characters_in_scene],
            "character_species": [getattr(char, 'species', 'unknown') for char in characters_in_scene],
            "target_audience": target_audience.value,
            "story_theme": story_theme or "Not provided",
            "story_genre": story_genre or "Not provided",
            "has_full_story": bool(full_story_content),
            "user_id": str(user_id) if user_id else None,
        }

        logger.info("🚀 MULTI_AGENT: Starting 4-agent image prompt generation")
        logger.info(f"📝 MULTI_AGENT: Scene content length: {len(scene_description)} chars")
        logger.info(
            f"👥 MULTI_AGENT: Characters provided: {[char.name for char in characters_in_scene]}"
        )
        logger.info(f"🎯 MULTI_AGENT: Target audience: {target_audience.value}")
        logger.info(f"🎭 MULTI_AGENT: Story theme: {story_theme or 'Not provided'}")
        logger.info(f"📚 MULTI_AGENT: Story genre: {story_genre or 'Not provided'}")

        try:
            # Agent 1: Scene Intelligence - Deep story understanding
            scene_analysis = await self._scene_intelligence_agent(
                scene_description,
                characters_in_scene,
                target_audience,
                user_id,
                story_context,
                story_theme,
                story_genre,
                full_story_content,
            )

            # Agent 2: Character Rendering - Detailed character descriptions
            character_descriptions = await self._character_rendering_agent(
                scene_analysis, characters_in_scene, user_id
            )

            # Agent 3: Visual Composition - Structured prompt creation
            visual_prompt = await self._visual_composition_agent(
                scene_analysis, character_descriptions, target_audience, user_id
            )

            # Agent 4: Quality Enhancement - Final refinement
            final_prompt = await self._quality_enhancement_agent(
                visual_prompt, scene_description, target_audience, user_id
            )

            logger.info(f"✅ MULTI_AGENT: Generated final prompt: {final_prompt}")
            logger.info(f"📊 MULTI_AGENT: Final prompt length: {len(final_prompt)} characters")

            return final_prompt

        except Exception as e:
            logger.error(f"❌ MULTI_AGENT: Error in agent pipeline: {e}")
            # Graceful fallback - create a basic but functional prompt
            fallback_prompt = self._create_fallback_prompt(
                scene_description, characters_in_scene, target_audience
            )
            logger.warning(f"🔄 MULTI_AGENT: Using fallback prompt: {fallback_prompt}")
            return fallback_prompt

    @traceable(run_type="llm", name="scene-intelligence-agent")
    async def _scene_intelligence_agent(
        self,
        scene_description: str,
        characters: list[StoryCharacter],
        target_audience: TargetAudience,
        user_id: Optional[UUID] = None,
        story_context: Optional[str] = None,
        story_theme: Optional[str] = None,
        story_genre: Optional[str] = None,
        full_story_content: Optional[str] = None,
    ) -> str:
        """
        Agent 1: Scene Intelligence

        Analyzes story content to understand:
        - Which characters are actually present in this scene
        - What's happening plot-wise (not just keywords)
        - Emotional tone and dramatic significance
        - Key visual elements that matter for the story
        """

        logger.info("🤖 SCENE_AGENT: Analyzing scene content...")

        # Pre-filter characters likely to be in this scene
        likely_characters = self._detect_characters_in_scene(scene_description, characters)
        logger.info(
            f"🤖 SCENE_AGENT: Detected {len(likely_characters)} characters likely in scene: {[char.name for char in likely_characters]}"
        )

        # Prepare rich character context for likely characters
        character_context = self._build_rich_character_context(likely_characters)

        # Extract story context and themes
        story_info = self._build_story_context(
            story_context, story_theme, story_genre, full_story_content, target_audience
        )

        # Enhance scene description with better context extraction
        enhanced_scene = self._enhance_scene_description(
            scene_description, likely_characters, story_info
        )

        # Build audience-specific analysis prompt
        audience_guidance = self._get_audience_analysis_guidance(target_audience)

        scene_prompt = f"""Analyze this {target_audience.value} story scene with deep contextual understanding for high-quality image generation:

SCENE CONTENT:
{enhanced_scene}

CHARACTER INFORMATION:
{character_context}

STORY CONTEXT:
{story_info}

AUDIENCE GUIDANCE:
{audience_guidance}

REQUIRED: You must provide a complete analysis with ALL 7 sections. Do not stop after the first section.

Analyze this scene for image generation and provide ALL of the following sections:

1. CHARACTERS_PRESENT: Which specific characters are in this scene (use character names, relationships, and visual descriptions from context)
2. CHARACTER_INTERACTIONS: How are the characters positioned/interacting with each other
3. MAIN_ACTION: The primary action or moment being depicted (be specific and visual)
4. SETTING_DETAILS: Detailed environment description (indoor/outdoor, specific location, atmospheric elements)
5. EMOTIONAL_TONE: The mood and emotional energy of the scene
6. VISUAL_FOCUS: The most compelling visual element that captures the story moment
7. STORY_SIGNIFICANCE: Why this moment matters to the narrative

IMPORTANT: You must include ALL 7 sections in your response. Format exactly as shown below:

CHARACTERS_PRESENT: [detailed character list with descriptions]
CHARACTER_INTERACTIONS: [positioning and interaction details]
MAIN_ACTION: [specific visual action]
SETTING_DETAILS: [comprehensive environment description]
EMOTIONAL_TONE: [mood and emotional energy]
VISUAL_FOCUS: [key compelling element]
STORY_SIGNIFICANCE: [narrative importance]

Complete all sections - do not stop early."""

        try:
            # Prepare app config for LLM client
            app_config = {
                "primary_provider": self.analysis_config["provider"],
                "primary_model_id": self.analysis_config["model"],
                "primary_parameters": self.analysis_config["parameters"],
            }

            # Call LLM client with proper method
            content, metadata = await llm_client.generate_completion(
                prompt=scene_prompt,
                app_config=app_config,
                user_id=user_id or uuid.uuid4(),  # Use actual user_id or fallback
                app_id="fairydust-story",
                action="scene_intelligence_analysis",
                request_metadata={"purpose": "scene_intelligence_analysis"},
            )

            scene_analysis = content.strip() if content else ""

            logger.info(f"🤖 SCENE_AGENT INPUT: {scene_description[:150]}...")
            logger.info(f"🤖 SCENE_AGENT OUTPUT: {scene_analysis}")
            
            # Check if response is complete (should have all 7 sections)
            required_sections = [
                "CHARACTERS_PRESENT:", "CHARACTER_INTERACTIONS:", "MAIN_ACTION:",
                "SETTING_DETAILS:", "EMOTIONAL_TONE:", "VISUAL_FOCUS:", "STORY_SIGNIFICANCE:"
            ]
            missing_sections = [section for section in required_sections if section not in scene_analysis]
            
            if missing_sections:
                logger.warning(f"🚨 SCENE_AGENT: Incomplete response - missing sections: {missing_sections}")
                logger.warning(f"🚨 SCENE_AGENT: Response length: {len(scene_analysis)} characters")
                # Add missing sections with placeholder content
                for section in missing_sections:
                    if section not in scene_analysis:
                        section_name = section.replace(":", "").replace("_", " ").title()
                        scene_analysis += f"\n{section} [Analysis needed for {section_name.lower()}]"

            return scene_analysis

        except Exception as e:
            logger.error(f"❌ SCENE_AGENT: Error in analysis: {e}")
            # Fallback analysis with proper character handling
            character_names = [char.name for char in likely_characters[:2]] if likely_characters else ["characters"]
            fallback = f"""CHARACTERS_PRESENT: {', '.join(character_names)}
CHARACTER_INTERACTIONS: Characters interacting in scene
MAIN_ACTION: Story scene with characters
SETTING_DETAILS: Story setting environment
EMOTIONAL_TONE: Engaging and appropriate for audience
VISUAL_FOCUS: Character interaction and story moment
STORY_SIGNIFICANCE: Important narrative moment"""
            logger.warning(f"🔄 SCENE_AGENT: Using fallback: {fallback}")
            return fallback

    @traceable(run_type="llm", name="character-rendering-agent")
    async def _character_rendering_agent(
        self, scene_analysis: str, characters: list[StoryCharacter], user_id: Optional[UUID] = None
    ) -> str:
        """
        Agent 2: Character Rendering

        Builds detailed character descriptions from scene analysis:
        - Integrates photo references for "My People"
        - Adds visual traits and personality markers
        - Ensures age-appropriate descriptions
        """

        logger.info("👤 CHARACTER_AGENT: Rendering character descriptions...")

        # Build character data for the agent
        character_data = []
        for char in characters:
            char_info = {
                "name": char.name,
                "relationship": char.relationship,
                "age": char.age if char.age is not None else "not specified",
                "entry_type": char.entry_type or "person",
                "species": char.species if hasattr(char, "species") else None,
                "traits": char.traits[:5] if char.traits else [],
                "has_photo": bool(char.photo_url),
            }
            character_data.append(char_info)

        character_prompt = f"""Based on this scene analysis, create detailed visual descriptions for the characters present:

SCENE ANALYSIS:
{scene_analysis}

AVAILABLE CHARACTERS:
{json.dumps(character_data, indent=2)}

For each character that appears in the scene (as identified in CHARACTERS_PRESENT), provide a detailed visual description that includes:
- Physical appearance that accurately reflects their specified age (CRITICAL: if age is provided, ensure the character looks that age, not younger)
- Key visual traits that make them recognizable
- Any special characteristics (for pets, fantasy characters, etc.)
- How they should appear in this specific scene

Focus on visual elements that will help an image generator create accurate, recognizable characters.
If a character has a photo reference (has_photo: true), mention that they should match their reference photo.
IMPORTANT: Pay close attention to age information - an 8-year-old should look like an 8-year-old, not a toddler or preschooler.

Format as:
CHARACTER_NAME: [detailed visual description]

Keep descriptions vivid but concise (2-3 sentences each)."""

        try:
            # Prepare app config for LLM client
            app_config = {
                "primary_provider": self.analysis_config["provider"],
                "primary_model_id": self.analysis_config["model"],
                "primary_parameters": self.analysis_config["parameters"],
            }

            # Call LLM client with proper method
            content, metadata = await llm_client.generate_completion(
                prompt=character_prompt,
                app_config=app_config,
                user_id=user_id or uuid.uuid4(),  # Use actual user_id or fallback
                app_id="fairydust-story",
                action="character_rendering",
                request_metadata={"purpose": "character_rendering"},
            )

            character_descriptions = content.strip() if content else ""

            logger.info(f"👤 CHARACTER_AGENT INPUT: Scene analysis + {len(characters)} characters")
            logger.info(f"👤 CHARACTER_AGENT OUTPUT: {character_descriptions}")

            return character_descriptions

        except Exception as e:
            logger.error(f"❌ CHARACTER_AGENT: Error in rendering: {e}")
            # Fallback character descriptions
            fallback = "\n".join(
                [f"{char.name}: A {char.relationship} character" for char in characters[:3]]
            )
            logger.warning(f"🔄 CHARACTER_AGENT: Using fallback: {fallback}")
            return fallback

    @traceable(run_type="llm", name="visual-composition-agent")
    async def _visual_composition_agent(
        self,
        scene_analysis: str,
        character_descriptions: str,
        target_audience: TargetAudience,
        user_id: Optional[UUID] = None,
    ) -> str:
        """
        Agent 3: Visual Composition

        Combines characters + scene + story context into structured prompt:
        - Optimizes for image generation models
        - Maintains story relevance while being visual
        - Balances detail with clarity
        """

        logger.info("🎨 COMPOSITION_AGENT: Creating visual composition...")

        # Get style requirements for target audience
        style_requirements = self._get_style_requirements(target_audience)

        composition_prompt = f"""Create a structured image generation prompt by combining these elements:

SCENE ANALYSIS:
{scene_analysis}

CHARACTER DESCRIPTIONS:
{character_descriptions}

TARGET AUDIENCE: {target_audience.value}
STYLE REQUIREMENTS: {style_requirements}

Combine all elements into a single, well-structured image prompt that:
1. Starts with the main characters and their visual descriptions
2. Includes the setting and main action from the scene
3. Captures the emotional tone
4. Ends with appropriate style requirements

Format as a single prompt (not sections). Make it flow naturally while being specific enough for image generation.
Aim for 150-250 characters. Focus on visual elements that will create a compelling, story-relevant image.

Example format: "[Character descriptions] [doing action] in [setting], [mood/emotion], [style requirements]"

Your prompt:"""

        try:
            # Prepare app config for LLM client
            app_config = {
                "primary_provider": self.creative_config["provider"],
                "primary_model_id": self.creative_config["model"],
                "primary_parameters": self.creative_config["parameters"],
            }

            # Call LLM client with proper method
            content, metadata = await llm_client.generate_completion(
                prompt=composition_prompt,
                app_config=app_config,
                user_id=user_id or uuid.uuid4(),  # Use actual user_id or fallback
                app_id="fairydust-story",
                action="visual_composition",
                request_metadata={"purpose": "visual_composition"},
            )

            visual_prompt = content.strip() if content else ""

            logger.info(f"🎨 COMPOSITION_AGENT INPUT: Scene + characters + {target_audience.value}")
            logger.info(f"🎨 COMPOSITION_AGENT OUTPUT: {visual_prompt}")

            return visual_prompt

        except Exception as e:
            logger.error(f"❌ COMPOSITION_AGENT: Error in composition: {e}")
            # Fallback composition
            fallback = f"Characters in a story scene, {style_requirements}"
            logger.warning(f"🔄 COMPOSITION_AGENT: Using fallback: {fallback}")
            return fallback

    @traceable(run_type="llm", name="quality-enhancement-agent")
    async def _quality_enhancement_agent(
        self,
        visual_prompt: str,
        original_scene: str,
        target_audience: TargetAudience,
        user_id: Optional[UUID] = None,
    ) -> str:
        """
        Agent 4: Quality Enhancement

        Refines and validates final prompt:
        - Ensures completeness and creativity
        - Optimizes prompt structure and length
        - Validates age-appropriateness
        """

        logger.info("✨ QUALITY_AGENT: Enhancing and validating prompt...")

        quality_prompt = f"""CRITICAL: You must enhance the existing prompt while staying TRUE to the story scene. Do NOT create a different scene.

CURRENT PROMPT TO ENHANCE:
{visual_prompt}

ACTUAL STORY SCENE (this is what's happening):
{original_scene[:400]}

TARGET AUDIENCE: {target_audience.value}

Your task:
1. Polish the existing prompt for clarity and visual specificity
2. Keep ALL the original characters and actions from the current prompt
3. Add visual details that enhance but don't change the scene
4. Ensure age-appropriate language for {target_audience.value}
5. Keep it under 300 characters

IMPORTANT: The enhanced prompt must describe the SAME SCENE with the SAME CHARACTERS doing the SAME ACTIONS. Only improve the visual clarity and description quality.

Return ONLY the enhanced prompt text, nothing else:"""

        try:
            # Prepare app config for LLM client
            app_config = {
                "primary_provider": self.creative_config["provider"],
                "primary_model_id": self.creative_config["model"],
                "primary_parameters": self.creative_config["parameters"],
            }

            # Call LLM client with proper method
            content, metadata = await llm_client.generate_completion(
                prompt=quality_prompt,
                app_config=app_config,
                user_id=user_id or uuid.uuid4(),  # Use actual user_id or fallback
                app_id="fairydust-story",
                action="quality_enhancement",
                request_metadata={"purpose": "quality_enhancement"},
            )

            final_prompt = content.strip() if content else ""

            # Clean up any quotation marks or formatting
            final_prompt = final_prompt.strip('"').strip("'").strip()

            logger.info(f"✨ QUALITY_AGENT INPUT: {visual_prompt}")
            logger.info(f"✨ QUALITY_AGENT FINAL: {final_prompt}")

            return final_prompt

        except Exception as e:
            logger.error(f"❌ QUALITY_AGENT: Error in enhancement: {e}")
            # Return the visual prompt as-is if enhancement fails
            logger.warning(f"🔄 QUALITY_AGENT: Using unenhanced prompt: {visual_prompt}")
            return visual_prompt

    def _build_rich_character_context(self, characters: list[StoryCharacter]) -> str:
        """Build comprehensive character context with full details"""

        if not characters:
            return "No specific characters provided"

        character_details = []
        for char in characters:
            char_info = [f"• {char.name}"]

            # Add relationship context
            if char.relationship:
                char_info.append(f"  - Relationship: {char.relationship}")

            # Add age information for accurate rendering
            if char.age is not None:
                char_info.append(f"  - Age: {char.age} years old")

            # Add visual traits
            if char.traits:
                visual_traits = [trait for trait in char.traits[:5]]  # Top 5 traits
                char_info.append(f"  - Traits: {', '.join(visual_traits)}")

            # Add character type information
            if char.entry_type:
                char_info.append(f"  - Type: {char.entry_type}")

            # Add species for pets/creatures
            if hasattr(char, "species") and char.species:
                char_info.append(f"  - Species: {char.species}")

            # Add photo reference indicator
            if char.photo_url:
                char_info.append("  - Has photo reference: Yes")

            character_details.append("\n".join(char_info))

        return "\n\n".join(character_details)

    def _build_story_context(
        self,
        story_context: Optional[str],
        story_theme: Optional[str],
        story_genre: Optional[str],
        full_story_content: Optional[str],
        target_audience: TargetAudience,
    ) -> str:
        """Build comprehensive story context for scene analysis"""

        context_parts = []

        # Add theme information
        if story_theme:
            context_parts.append(f"Theme: {story_theme}")

        # Add genre information
        if story_genre:
            context_parts.append(f"Genre: {story_genre}")
        else:
            # Infer genre from target audience
            genre_hints = {
                TargetAudience.TODDLER: "Simple adventure, family stories",
                TargetAudience.PRESCHOOL: "Educational adventure, friendship tales",
                TargetAudience.EARLY_ELEMENTARY: "Adventure, fantasy, friendship",
                TargetAudience.LATE_ELEMENTARY: "Adventure, mystery, coming-of-age",
                TargetAudience.TEEN: "Young adult themes, self-discovery",
            }
            context_parts.append(
                f"Likely Genre: {genre_hints.get(target_audience, 'Children story')}"
            )

        # Add broader story context
        if story_context:
            context_parts.append(f"Story Context: {story_context}")

        # Extract story essence from full content if available
        if full_story_content:
            story_essence = self._extract_story_essence(full_story_content, target_audience)
            if story_essence:
                context_parts.append(f"Story Essence: {story_essence}")

        # Add target audience context
        audience_context = self._get_audience_context(target_audience)
        context_parts.append(f"Audience Context: {audience_context}")

        return "\n".join(context_parts) if context_parts else "General children's story"

    def _extract_story_essence(self, full_story: str, target_audience: TargetAudience) -> str:
        """Extract key themes and emotional tone from full story"""

        # Clean and analyze the story for key themes
        story_lower = full_story.lower()

        # Identify key themes
        themes = []
        theme_patterns = {
            "friendship": ["friend", "together", "help", "share", "care"],
            "adventure": ["journey", "explore", "discover", "adventure", "quest"],
            "family": ["family", "mother", "father", "parent", "home"],
            "learning": ["learn", "school", "teach", "practice", "grow"],
            "courage": ["brave", "courage", "fear", "overcome", "strong"],
            "creativity": ["create", "imagine", "dream", "art", "build"],
            "kindness": ["kind", "help", "gentle", "love", "care"],
        }

        for theme, keywords in theme_patterns.items():
            if sum(1 for keyword in keywords if keyword in story_lower) >= 2:
                themes.append(theme)

        # Identify emotional tone
        positive_emotions = [
            "happy",
            "joy",
            "excited",
            "wonderful",
            "amazing",
            "love",
            "smile",
            "laugh",
        ]
        calm_emotions = ["peaceful", "quiet", "gentle", "soft", "calm", "serene"]
        energetic_emotions = ["run", "jump", "play", "dance", "sing", "celebrate"]

        tone_score = {
            "positive": sum(1 for emotion in positive_emotions if emotion in story_lower),
            "calm": sum(1 for emotion in calm_emotions if emotion in story_lower),
            "energetic": sum(1 for emotion in energetic_emotions if emotion in story_lower),
        }

        dominant_tone = (
            max(tone_score, key=tone_score.get) if any(tone_score.values()) else "balanced"
        )

        essence_parts = []
        if themes:
            essence_parts.append(f"Themes: {', '.join(themes[:3])}")
        essence_parts.append(f"Emotional tone: {dominant_tone}")

        return "; ".join(essence_parts)

    def _get_audience_context(self, target_audience: TargetAudience) -> str:
        """Get audience-specific context for story understanding"""

        contexts = {
            TargetAudience.TODDLER: "Simple concepts, bright colors, basic emotions, safe environments",
            TargetAudience.PRESCHOOL: "Learning through play, cause and effect, social interactions, exploration",
            TargetAudience.EARLY_ELEMENTARY: "Problem-solving, friendships, school experiences, mild challenges",
            TargetAudience.LATE_ELEMENTARY: "Independence, complex emotions, social dynamics, personal growth",
            TargetAudience.TEEN: "Identity formation, relationships, future planning, complex moral choices",
        }

        return contexts.get(target_audience, "Age-appropriate content with positive themes")

    def _enhance_scene_description(
        self, scene_description: str, characters: list[StoryCharacter], story_info: str
    ) -> str:
        """Enhance scene description with better context preservation"""

        # Clean up the scene while preserving narrative flow
        enhanced = scene_description.strip()

        # Remove excessive dialogue markers but preserve narrative
        enhanced = re.sub(r'"[^"]{50,}"', "[dialogue]", enhanced)  # Replace long dialogue
        enhanced = re.sub(r'"([^"]{1,49})"', r'saying "\1"', enhanced)  # Keep short dialogue

        # Preserve emotional context words
        emotion_markers = [
            "happy",
            "sad",
            "excited",
            "worried",
            "surprised",
            "gentle",
            "calm",
            "peaceful",
        ]
        preserved_emotions = [word for word in emotion_markers if word in enhanced.lower()]

        # Don't truncate aggressively - allow up to 500 characters
        if len(enhanced) > 500:
            # Find a good breaking point
            truncation_point = enhanced.rfind(".", 0, 500)
            if truncation_point > 300:  # Good sentence break
                enhanced = enhanced[: truncation_point + 1]
            else:
                # Break at word boundary
                enhanced = enhanced[:500].rsplit(" ", 1)[0] + "..."

        return enhanced

    def _get_audience_analysis_guidance(self, target_audience: TargetAudience) -> str:
        """Get audience-specific guidance for scene analysis"""

        guidance = {
            TargetAudience.TODDLER: "Focus on simple, clear visuals. Bright colors, basic shapes, safe environments. Emphasize facial expressions and simple actions.",
            TargetAudience.PRESCHOOL: "Include educational elements and cause-and-effect visuals. Show character interactions and emotional expressions clearly.",
            TargetAudience.EARLY_ELEMENTARY: "Balance detail with clarity. Include problem-solving moments and social interactions. Show character growth and learning.",
            TargetAudience.LATE_ELEMENTARY: "Allow more complex scenes and emotions. Include environmental storytelling and character development moments.",
            TargetAudience.TEEN: "Emphasize emotional depth and character relationships. Include sophisticated visual metaphors and identity themes.",
        }

        return guidance.get(
            target_audience,
            "Create age-appropriate, engaging visuals that support the story narrative.",
        )

    def _detect_characters_in_scene(
        self, scene_text: str, characters: list[StoryCharacter]
    ) -> list[StoryCharacter]:
        """Advanced character detection using multiple heuristics"""

        scene_lower = scene_text.lower()
        detected_characters = []

        for char in characters:
            is_present = False

            # Special handling for "yourself" character - always include if it's the protagonist
            if char.relationship and char.relationship.lower() in ["yourself", "protagonist"]:
                # Check for first-person pronouns that indicate the protagonist
                first_person_indicators = ["i ", "i'", "my ", "me ", "myself", "i've", "i'll", "i'd", "i'm"]
                if any(indicator in scene_lower for indicator in first_person_indicators):
                    is_present = True
                # Also check if character's actual name is mentioned
                elif char.name.lower() in scene_lower:
                    is_present = True
            # Direct name mention
            elif char.name.lower() in scene_lower:
                is_present = True

            # Relationship-based detection
            elif char.relationship:
                rel_words = char.relationship.lower().split()
                # Check for relationship words (mom, dad, friend, etc.)
                relationship_indicators = [
                    "mom",
                    "mother",
                    "dad",
                    "father",
                    "friend",
                    "sister",
                    "brother",
                    "grandmother",
                    "grandma",
                    "grandfather",
                    "grandpa",
                    "yourself",
                    "self",
                    "me",
                    "i",
                ]
                for rel_word in rel_words:
                    if rel_word in relationship_indicators and rel_word in scene_lower:
                        is_present = True
                        break

            # Pronoun-based detection (if only one character of that type)
            elif len(characters) <= 3:  # Only for small character sets
                # Check for pronouns that might refer to this character
                if char.entry_type == "person":
                    if any(pronoun in scene_lower for pronoun in ["he ", "she ", "they "]):
                        is_present = True
                elif char.entry_type == "pet":
                    if any(
                        animal_ref in scene_lower for animal_ref in ["pet", "dog", "cat", "animal"]
                    ):
                        is_present = True

            # Trait-based detection
            if char.traits and not is_present:
                trait_matches = sum(1 for trait in char.traits if trait.lower() in scene_lower)
                if trait_matches >= 2:  # Multiple trait matches suggest presence
                    is_present = True

            if is_present:
                detected_characters.append(char)

        # If no characters detected but we have characters available, include at least some
        if not detected_characters and characters:
            # Include the first character as a minimum
            detected_characters.append(characters[0])
            logger.warning(f"🚨 CHARACTER_DETECTION: No characters detected in scene, using first character: {characters[0].name}")
        elif len(detected_characters) == 1 and len(characters) > 1:
            # If we only detected one character but have more available, check for "yourself" character
            # to ensure protagonist is included
            for char in characters:
                if char.relationship and char.relationship.lower() in ["yourself", "protagonist"] and char not in detected_characters:
                    detected_characters.append(char)
                    logger.info(f"➕ CHARACTER_DETECTION: Added protagonist character: {char.name}")
                    break

        return detected_characters

    def _get_style_requirements(self, target_audience: TargetAudience) -> str:
        """Get appropriate style requirements for target audience"""

        if target_audience in [TargetAudience.TODDLER, TargetAudience.PRESCHOOL]:
            return "children's picture book illustration, bright and colorful, simple and clear"
        elif target_audience in [TargetAudience.EARLY_ELEMENTARY, TargetAudience.LATE_ELEMENTARY]:
            return (
                "children's book illustration, colorful and engaging, detailed but age-appropriate"
            )
        elif target_audience == TargetAudience.TEEN:
            return "young adult illustration, dynamic and modern"
        else:
            return "high quality illustration, professional storybook art"

    def _create_fallback_prompt(
        self,
        scene_description: str,
        characters: list[StoryCharacter],
        target_audience: TargetAudience,
    ) -> str:
        """Create a basic but functional prompt if the agent system fails"""

        # Extract basic elements
        character_names = [char.name for char in characters[:2]]
        char_text = (
            f"featuring {' and '.join(character_names)}"
            if character_names
            else "with story characters"
        )

        # Simple scene extraction
        scene_words = scene_description.lower().split()[:10]
        basic_scene = " ".join(scene_words)

        style = self._get_style_requirements(target_audience)

        fallback = f"A story scene {char_text} in {basic_scene}, {style}"

        logger.info(f"🆘 FALLBACK_PROMPT: {fallback}")
        return fallback


# Global instance
multi_agent_image_service = MultiAgentImageService()
