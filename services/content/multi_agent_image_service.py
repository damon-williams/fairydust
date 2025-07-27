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
import uuid
from typing import List, Optional
from uuid import UUID

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
                "max_tokens": 200,
                "top_p": 0.9
            }
        }
        
        self.creative_config = {
            "provider": "anthropic", 
            "model": "claude-3-5-haiku-20241022",
            "parameters": {
                "temperature": 0.7,  # Higher temperature for creative tasks
                "max_tokens": 150,
                "top_p": 0.9
            }
        }
    
    async def generate_image_prompt(
        self,
        scene_description: str,
        characters_in_scene: List[StoryCharacter],
        target_audience: TargetAudience,
        user_id: Optional[UUID] = None,
        story_context: Optional[str] = None
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
        
        logger.info(f"🚀 MULTI_AGENT: Starting 4-agent image prompt generation")
        logger.info(f"📝 MULTI_AGENT: Scene content length: {len(scene_description)} chars")
        logger.info(f"👥 MULTI_AGENT: Characters provided: {[char.name for char in characters_in_scene]}")
        logger.info(f"🎯 MULTI_AGENT: Target audience: {target_audience.value}")
        
        try:
            # Agent 1: Scene Intelligence - Deep story understanding
            scene_analysis = await self._scene_intelligence_agent(
                scene_description, characters_in_scene, target_audience, user_id
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
    
    async def _scene_intelligence_agent(
        self,
        scene_description: str,
        characters: List[StoryCharacter],
        target_audience: TargetAudience,
        user_id: Optional[UUID] = None
    ) -> str:
        """
        Agent 1: Scene Intelligence
        
        Analyzes story content to understand:
        - Which characters are actually present in this scene
        - What's happening plot-wise (not just keywords)
        - Emotional tone and dramatic significance
        - Key visual elements that matter for the story
        """
        
        logger.info(f"🤖 SCENE_AGENT: Analyzing scene content...")
        
        # Prepare character context
        character_names = [char.name for char in characters]
        character_context = f"Available characters: {', '.join(character_names)}" if character_names else "No specific characters provided"
        
        scene_prompt = f"""Analyze this {target_audience.value} story scene and extract key information for image generation:

SCENE CONTENT:
{scene_description}

CHARACTER CONTEXT:
{character_context}

Please analyze and respond with:
1. CHARACTERS_PRESENT: Which characters are actually in this scene (consider pronouns, context clues, not just exact name matches)
2. MAIN_ACTION: What is happening in this scene (plot-wise, not just keywords)
3. SETTING: Where this takes place
4. EMOTION: The emotional tone/mood
5. VISUAL_FOCUS: The most important visual element that captures this scene

Format your response as:
CHARACTERS_PRESENT: [list]
MAIN_ACTION: [description]
SETTING: [location/environment]
EMOTION: [mood/feeling]
VISUAL_FOCUS: [key visual element]

Keep each section concise but meaningful."""

        try:
            # Prepare app config for LLM client
            app_config = {
                "primary_provider": self.analysis_config["provider"],
                "primary_model_id": self.analysis_config["model"],
                "primary_parameters": self.analysis_config["parameters"]
            }
            
            # Call LLM client with proper method
            content, metadata = await llm_client.generate_completion(
                prompt=scene_prompt,
                app_config=app_config,
                user_id=user_id or uuid.uuid4(),  # Use actual user_id or fallback
                app_id="fairydust-story",
                action="scene_intelligence_analysis",
                request_metadata={"purpose": "scene_intelligence_analysis"}
            )
            
            scene_analysis = content.strip() if content else ""
            
            logger.info(f"🤖 SCENE_AGENT INPUT: {scene_description[:150]}...")
            logger.info(f"🤖 SCENE_AGENT OUTPUT: {scene_analysis}")
            
            return scene_analysis
            
        except Exception as e:
            logger.error(f"❌ SCENE_AGENT: Error in analysis: {e}")
            # Fallback analysis
            fallback = f"CHARACTERS_PRESENT: {', '.join(character_names[:2])}\nMAIN_ACTION: Story scene with characters\nSETTING: Story setting\nEMOTION: Engaging\nVISUAL_FOCUS: Character interaction"
            logger.warning(f"🔄 SCENE_AGENT: Using fallback: {fallback}")
            return fallback
    
    async def _character_rendering_agent(
        self,
        scene_analysis: str,
        characters: List[StoryCharacter]
    ) -> str:
        """
        Agent 2: Character Rendering
        
        Builds detailed character descriptions from scene analysis:
        - Integrates photo references for "My People"
        - Adds visual traits and personality markers
        - Ensures age-appropriate descriptions
        """
        
        logger.info(f"👤 CHARACTER_AGENT: Rendering character descriptions...")
        
        # Build character data for the agent
        character_data = []
        for char in characters:
            char_info = {
                "name": char.name,
                "relationship": char.relationship,
                "entry_type": char.entry_type or "person",
                "species": char.species if hasattr(char, 'species') else None,
                "traits": char.traits[:5] if char.traits else [],
                "has_photo": bool(char.photo_url)
            }
            character_data.append(char_info)
        
        character_prompt = f"""Based on this scene analysis, create detailed visual descriptions for the characters present:

SCENE ANALYSIS:
{scene_analysis}

AVAILABLE CHARACTERS:
{json.dumps(character_data, indent=2)}

For each character that appears in the scene (as identified in CHARACTERS_PRESENT), provide a detailed visual description that includes:
- Physical appearance (age-appropriate)
- Key visual traits that make them recognizable
- Any special characteristics (for pets, fantasy characters, etc.)
- How they should appear in this specific scene

Focus on visual elements that will help an image generator create accurate, recognizable characters.
If a character has a photo reference (has_photo: true), mention that they should match their reference photo.

Format as:
CHARACTER_NAME: [detailed visual description]

Keep descriptions vivid but concise (2-3 sentences each)."""

        try:
            # Prepare app config for LLM client
            app_config = {
                "primary_provider": self.analysis_config["provider"],
                "primary_model_id": self.analysis_config["model"],
                "primary_parameters": self.analysis_config["parameters"]
            }
            
            # Call LLM client with proper method
            content, metadata = await llm_client.generate_completion(
                prompt=character_prompt,
                app_config=app_config,
                user_id=user_id or uuid.uuid4(),  # Use actual user_id or fallback
                app_id="fairydust-story",
                action="character_rendering",
                request_metadata={"purpose": "character_rendering"}
            )
            
            character_descriptions = content.strip() if content else ""
            
            logger.info(f"👤 CHARACTER_AGENT INPUT: Scene analysis + {len(characters)} characters")
            logger.info(f"👤 CHARACTER_AGENT OUTPUT: {character_descriptions}")
            
            return character_descriptions
            
        except Exception as e:
            logger.error(f"❌ CHARACTER_AGENT: Error in rendering: {e}")
            # Fallback character descriptions
            fallback = "\n".join([f"{char.name}: A {char.relationship} character" for char in characters[:3]])
            logger.warning(f"🔄 CHARACTER_AGENT: Using fallback: {fallback}")
            return fallback
    
    async def _visual_composition_agent(
        self,
        scene_analysis: str,
        character_descriptions: str,
        target_audience: TargetAudience
    ) -> str:
        """
        Agent 3: Visual Composition
        
        Combines characters + scene + story context into structured prompt:
        - Optimizes for image generation models
        - Maintains story relevance while being visual
        - Balances detail with clarity
        """
        
        logger.info(f"🎨 COMPOSITION_AGENT: Creating visual composition...")
        
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
                "primary_parameters": self.creative_config["parameters"]
            }
            
            # Call LLM client with proper method
            content, metadata = await llm_client.generate_completion(
                prompt=composition_prompt,
                app_config=app_config,
                user_id=user_id or uuid.uuid4(),  # Use actual user_id or fallback
                app_id="fairydust-story",
                action="visual_composition",
                request_metadata={"purpose": "visual_composition"}
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
    
    async def _quality_enhancement_agent(
        self,
        visual_prompt: str,
        original_scene: str,
        target_audience: TargetAudience
    ) -> str:
        """
        Agent 4: Quality Enhancement
        
        Refines and validates final prompt:
        - Ensures completeness and creativity
        - Optimizes prompt structure and length
        - Validates age-appropriateness
        """
        
        logger.info(f"✨ QUALITY_AGENT: Enhancing and validating prompt...")
        
        quality_prompt = f"""Review and enhance this image generation prompt for quality and completeness:

CURRENT PROMPT:
{visual_prompt}

ORIGINAL SCENE CONTEXT (for reference):
{original_scene[:200]}...

TARGET AUDIENCE: {target_audience.value}

Please review the prompt and:
1. Ensure it's specific enough for good image generation
2. Verify it captures the story essence
3. Check that it's age-appropriate for {target_audience.value}
4. Add any missing visual elements that would improve the image
5. Optimize the structure and flow

Provide your enhanced version. Keep it focused and under 300 characters.
Make it compelling and visually clear while maintaining story relevance.

Enhanced prompt:"""

        try:
            # Prepare app config for LLM client
            app_config = {
                "primary_provider": self.creative_config["provider"],
                "primary_model_id": self.creative_config["model"],
                "primary_parameters": self.creative_config["parameters"]
            }
            
            # Call LLM client with proper method
            content, metadata = await llm_client.generate_completion(
                prompt=quality_prompt,
                app_config=app_config,
                user_id=user_id or uuid.uuid4(),  # Use actual user_id or fallback
                app_id="fairydust-story",
                action="quality_enhancement",
                request_metadata={"purpose": "quality_enhancement"}
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
    
    def _get_style_requirements(self, target_audience: TargetAudience) -> str:
        """Get appropriate style requirements for target audience"""
        
        if target_audience in [TargetAudience.TODDLER, TargetAudience.PRESCHOOL]:
            return "children's picture book illustration, bright and colorful, simple and clear"
        elif target_audience in [TargetAudience.EARLY_ELEMENTARY, TargetAudience.LATE_ELEMENTARY]:
            return "children's book illustration, colorful and engaging, detailed but age-appropriate"
        elif target_audience == TargetAudience.TEEN:
            return "young adult illustration, dynamic and modern"
        else:
            return "high quality illustration, professional storybook art"
    
    def _create_fallback_prompt(
        self,
        scene_description: str,
        characters: List[StoryCharacter],
        target_audience: TargetAudience
    ) -> str:
        """Create a basic but functional prompt if the agent system fails"""
        
        # Extract basic elements
        character_names = [char.name for char in characters[:2]]
        char_text = f"featuring {' and '.join(character_names)}" if character_names else "with story characters"
        
        # Simple scene extraction
        scene_words = scene_description.lower().split()[:10]
        basic_scene = " ".join(scene_words)
        
        style = self._get_style_requirements(target_audience)
        
        fallback = f"A story scene {char_text} in {basic_scene}, {style}"
        
        logger.info(f"🆘 FALLBACK_PROMPT: {fallback}")
        return fallback


# Global instance
multi_agent_image_service = MultiAgentImageService()