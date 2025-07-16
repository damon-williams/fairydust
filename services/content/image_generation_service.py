"""AI Image generation service for OpenAI DALL-E and Replicate integration"""

import asyncio
import os
import time
from typing import Optional, Tuple

import httpx
from fastapi import HTTPException

from models import ImageStyle, ImageSize, ImageReferencePerson


class ImageGenerationService:
    """Service for generating AI images using Replicate FLUX"""
    
    def __init__(self):
        self.replicate_api_token = os.getenv("REPLICATE_API_TOKEN")
        
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
        Generate an AI image using FLUX for all generations
        
        Returns:
            Tuple[str, dict]: (image_url, metadata)
        """
        start_time = time.time()
        
        # Use FLUX for all image generation (better quality and no storage auth issues)
        image_url, metadata = await self._generate_with_replicate(
            prompt, style, image_size, reference_people
        )
        
        generation_time_ms = int((time.time() - start_time) * 1000)
        metadata["generation_time_ms"] = generation_time_ms
        metadata["has_reference_people"] = len(reference_people) > 0
        
        return image_url, metadata
    
    
    async def _generate_with_replicate(
        self,
        prompt: str,
        style: ImageStyle,
        image_size: ImageSize,
        reference_people: list[ImageReferencePerson]
    ) -> Tuple[str, dict]:
        """Generate image using Replicate FLUX for all image generation"""
        
        # Use FLUX model for all generation (consistent quality)
        model = "black-forest-labs/flux-1.1-pro"
        
        # Map our styles to FLUX-optimized prompts
        style_prompts = {
            ImageStyle.REALISTIC: "photorealistic, professional photography, high detail, sharp focus, studio lighting",
            ImageStyle.ARTISTIC: "artistic masterpiece, oil painting style, fine art, brush strokes, gallery quality",
            ImageStyle.CARTOON: "cartoon illustration, animated style, vibrant colors, clean lines, stylized",
            ImageStyle.ABSTRACT: "abstract art, modern artistic interpretation, geometric shapes, color theory",
            ImageStyle.VINTAGE: "vintage photography, retro aesthetic, film grain, sepia tones, nostalgic",
            ImageStyle.MODERN: "modern digital art, contemporary style, minimalist, clean composition"
        }
        
        # Build enhanced prompt
        enhanced_prompt = f"{prompt}, {style_prompts[style]}"
        
        # Add people descriptions if provided
        if reference_people:
            people_descriptions = []
            for person in reference_people:
                people_descriptions.append(f"person ({person.description})")
            enhanced_prompt += f", featuring {', '.join(people_descriptions)}"
        
        # Add quality enhancers for FLUX
        enhanced_prompt += ", high quality, detailed, professional"
        
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
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.replicate.com/v1/models/{model}/predictions",
                headers=headers,
                json=payload,
                timeout=10.0
            )
            if response.status_code != 201:
                error_data = response.json()
                raise HTTPException(
                    status_code=500,
                    detail=f"Replicate API error: {error_data.get('detail', 'Unknown error')}"
                )
            
            prediction = response.json()
            prediction_id = prediction["id"]
        
        # Poll for completion
        max_wait_time = 120  # 2 minutes
        poll_interval = 2    # 2 seconds
        elapsed_time = 0
        
        async with httpx.AsyncClient() as client:
            while elapsed_time < max_wait_time:
                await asyncio.sleep(poll_interval)
                elapsed_time += poll_interval
                
                poll_response = await client.get(
                    f"https://api.replicate.com/v1/predictions/{prediction_id}",
                    headers=headers
                )
                if poll_response.status_code != 200:
                    raise HTTPException(status_code=500, detail="Failed to check prediction status")
                
                result = poll_response.json()
                status = result["status"]
                
                if status == "succeeded":
                    image_url = result["output"][0] if isinstance(result["output"], list) else result["output"]
                    
                    metadata = {
                        "model_used": "flux-1.1-pro",
                        "api_provider": "replicate",
                        "enhanced_prompt": enhanced_prompt,
                        "prediction_id": prediction_id,
                        "reference_people_count": len(reference_people),
                        "generation_approach": "flux_universal"
                    }
                    
                    return image_url, metadata
                
                elif status == "failed":
                    error_msg = result.get("error", "Unknown generation error")
                    raise HTTPException(status_code=500, detail=f"Image generation failed: {error_msg}")
        
        # Timeout
        raise HTTPException(status_code=500, detail="Image generation timed out")
    


# Global instance
image_generation_service = ImageGenerationService()