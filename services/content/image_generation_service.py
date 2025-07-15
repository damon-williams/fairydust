"""AI Image generation service for OpenAI DALL-E and Replicate integration"""

import asyncio
import os
import time
from typing import Optional, Tuple

import aiohttp
from fastapi import HTTPException

from models import ImageStyle, ImageSize, ImageReferencePerson


class ImageGenerationService:
    """Service for generating AI images using OpenAI DALL-E and Replicate"""
    
    def __init__(self):
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.replicate_api_token = os.getenv("REPLICATE_API_TOKEN")
        
        if not self.openai_api_key:
            raise ValueError("Missing OPENAI_API_KEY environment variable")
        if not self.replicate_api_token:
            raise ValueError("Missing REPLICATE_API_TOKEN environment variable")
    
    async def generate_image(
        self,
        prompt: str,
        style: ImageStyle,
        image_size: ImageSize,
        reference_people: list[ImageReferencePerson]
    ) -> Tuple[str, dict]:
        """
        Generate an AI image using appropriate API based on requirements
        
        Returns:
            Tuple[str, dict]: (image_url, metadata)
        """
        start_time = time.time()
        
        # Use Replicate for images with people, OpenAI for text-only
        if reference_people:
            image_url, metadata = await self._generate_with_replicate(
                prompt, style, image_size, reference_people
            )
        else:
            image_url, metadata = await self._generate_with_openai(
                prompt, style, image_size
            )
        
        generation_time_ms = int((time.time() - start_time) * 1000)
        metadata["generation_time_ms"] = generation_time_ms
        metadata["has_reference_people"] = len(reference_people) > 0
        
        return image_url, metadata
    
    async def _generate_with_openai(
        self,
        prompt: str,
        style: ImageStyle,
        image_size: ImageSize
    ) -> Tuple[str, dict]:
        """Generate image using OpenAI DALL-E 3"""
        
        # Map our styles to DALL-E prompts
        style_prompts = {
            ImageStyle.REALISTIC: "photorealistic, high quality, detailed",
            ImageStyle.ARTISTIC: "artistic, painted style, creative interpretation",
            ImageStyle.CARTOON: "cartoon style, animated, colorful",
            ImageStyle.ABSTRACT: "abstract art, modern, artistic interpretation",
            ImageStyle.VINTAGE: "vintage style, retro, classic aesthetic",
            ImageStyle.MODERN: "modern style, contemporary, clean design"
        }
        
        # Map our sizes to DALL-E sizes
        size_map = {
            ImageSize.STANDARD: "1024x1024",
            ImageSize.LARGE: "1024x1792", 
            ImageSize.SQUARE: "1024x1024"
        }
        
        # Enhance prompt with style
        enhanced_prompt = f"{prompt}, {style_prompts[style]}"
        
        payload = {
            "model": "dall-e-3",
            "prompt": enhanced_prompt,
            "n": 1,
            "size": size_map[image_size],
            "quality": "standard",
            "response_format": "url"
        }
        
        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.openai.com/v1/images/generations",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                if response.status != 200:
                    error_data = await response.json()
                    raise HTTPException(
                        status_code=500,
                        detail=f"OpenAI API error: {error_data.get('error', {}).get('message', 'Unknown error')}"
                    )
                
                data = await response.json()
                image_url = data["data"][0]["url"]
                
                metadata = {
                    "model_used": "dall-e-3",
                    "api_provider": "openai",
                    "enhanced_prompt": enhanced_prompt
                }
                
                return image_url, metadata
    
    async def _generate_with_replicate(
        self,
        prompt: str,
        style: ImageStyle,
        image_size: ImageSize,
        reference_people: list[ImageReferencePerson]
    ) -> Tuple[str, dict]:
        """Generate image using Replicate FLUX/Stable Diffusion"""
        
        # Use FLUX model for face consistency
        model = "black-forest-labs/flux-1.1-pro"
        
        # Map our styles to appropriate prompts
        style_prompts = {
            ImageStyle.REALISTIC: "photorealistic, professional photography, high detail",
            ImageStyle.ARTISTIC: "artistic painting, oil painting style, masterpiece",
            ImageStyle.CARTOON: "cartoon illustration, animated style, vibrant colors",
            ImageStyle.ABSTRACT: "abstract art, modern artistic interpretation",
            ImageStyle.VINTAGE: "vintage photography, retro style, film grain",
            ImageStyle.MODERN: "modern digital art, contemporary style"
        }
        
        # Build enhanced prompt with people descriptions
        people_descriptions = []
        for person in reference_people:
            people_descriptions.append(f"person ({person.description})")
        
        enhanced_prompt = f"{prompt}, {style_prompts[style]}"
        if people_descriptions:
            enhanced_prompt += f", featuring {', '.join(people_descriptions)}"
        
        # Map image sizes
        size_map = {
            ImageSize.STANDARD: {"width": 1024, "height": 1024},
            ImageSize.LARGE: {"width": 1024, "height": 1792},
            ImageSize.SQUARE: {"width": 1024, "height": 1024}
        }
        
        dimensions = size_map[image_size]
        
        payload = {
            "input": {
                "prompt": enhanced_prompt,
                "width": dimensions["width"],
                "height": dimensions["height"],
                "steps": 28,
                "guidance": 3.5,
                "safety_tolerance": 2,
                "seed": None
            }
        }
        
        headers = {
            "Authorization": f"Token {self.replicate_api_token}",
            "Content-Type": "application/json"
        }
        
        # Start prediction
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://api.replicate.com/v1/models/{model}/predictions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status != 201:
                    error_data = await response.json()
                    raise HTTPException(
                        status_code=500,
                        detail=f"Replicate API error: {error_data.get('detail', 'Unknown error')}"
                    )
                
                prediction = await response.json()
                prediction_id = prediction["id"]
            
            # Poll for completion
            max_wait_time = 120  # 2 minutes
            poll_interval = 2    # 2 seconds
            elapsed_time = 0
            
            while elapsed_time < max_wait_time:
                await asyncio.sleep(poll_interval)
                elapsed_time += poll_interval
                
                async with session.get(
                    f"https://api.replicate.com/v1/predictions/{prediction_id}",
                    headers=headers
                ) as poll_response:
                    if poll_response.status != 200:
                        raise HTTPException(status_code=500, detail="Failed to check prediction status")
                    
                    result = await poll_response.json()
                    status = result["status"]
                    
                    if status == "succeeded":
                        image_url = result["output"][0] if isinstance(result["output"], list) else result["output"]
                        
                        metadata = {
                            "model_used": model,
                            "api_provider": "replicate",
                            "enhanced_prompt": enhanced_prompt,
                            "prediction_id": prediction_id,
                            "reference_people_count": len(reference_people)
                        }
                        
                        return image_url, metadata
                    
                    elif status == "failed":
                        error_msg = result.get("error", "Unknown generation error")
                        raise HTTPException(status_code=500, detail=f"Image generation failed: {error_msg}")
            
            # Timeout
            raise HTTPException(status_code=500, detail="Image generation timed out")
    


# Global instance
image_generation_service = ImageGenerationService()