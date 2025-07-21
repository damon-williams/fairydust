"""AI Image generation service for OpenAI DALL-E and Replicate integration"""

import asyncio
import json
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
        """Generate image using Replicate - selects appropriate model based on reference people"""
        
        # Choose model based on whether reference people are provided
        if reference_people:
            # Use Runway Gen-4 Image for multiple face references (up to 3)
            model = "runwayml/gen4-image"
            return await self._generate_with_gen4_image(model, prompt, style, image_size, reference_people)
        else:
            # Use standard FLUX for text-only generation
            model = "black-forest-labs/flux-1.1-pro"
            return await self._generate_standard_flux(model, prompt, style, image_size, reference_people)
        
    async def _generate_standard_flux(
        self,
        model: str,
        prompt: str,
        style: ImageStyle,
        image_size: ImageSize,
        reference_people: list[ImageReferencePerson]
    ) -> Tuple[str, dict]:
        """Generate image using standard FLUX model (text-only)"""
        
        print(f"🎭 FLUX GENERATION STARTING")
        print(f"   Original prompt: {prompt}")
        print(f"   Style: {style.value}")
        print(f"   Image size: {image_size.value}")
        
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
        
        # Add people descriptions if provided (text-only for standard FLUX)
        if reference_people:
            people_descriptions = []
            for person in reference_people:
                people_descriptions.append(f"person ({person.description})")
            enhanced_prompt += f", featuring {', '.join(people_descriptions)}"
            print(f"   Added {len(reference_people)} people descriptions")
        
        # Add quality enhancers for FLUX
        enhanced_prompt += ", high quality, detailed, professional"
        
        # Map image sizes (FLUX max dimensions: 1440x1440)
        size_map = {
            ImageSize.STANDARD: {"width": 1024, "height": 1024},
            ImageSize.LARGE: {"width": 1024, "height": 1440},  # FLUX max height is 1440
            ImageSize.SQUARE: {"width": 1024, "height": 1024}
        }
        
        dimensions = size_map[image_size]
        
        payload = {
            "input": {
                "prompt": enhanced_prompt,
                "width": dimensions["width"],
                "height": dimensions["height"],
                "output_format": "png",
                "safety_tolerance": 2,
                "prompt_upsampling": False
            }
        }
        
        headers = {
            "Authorization": f"Token {self.replicate_api_token}",
            "Content-Type": "application/json"
        }
        
        # Start prediction
        async with httpx.AsyncClient() as client:
            try:
                print(f"🤖 REPLICATE REQUEST: {model}")
                print(f"🎨 FULL ENHANCED PROMPT: {enhanced_prompt}")
                print(f"📏 PROMPT LENGTH: {len(enhanced_prompt)} characters")
                print(f"👥 REFERENCE PEOPLE: {len(reference_people)}")
                if 'width' in locals() and 'height' in locals():
                    print(f"🖼️ IMAGE SIZE: {width}x{height}")
                elif 'dimensions' in locals():
                    print(f"🖼️ IMAGE SIZE: {dimensions.get('width', 'unknown')}x{dimensions.get('height', 'unknown')}")
                print(f"⚙️ REQUEST PAYLOAD:")
                print(json.dumps(payload, indent=2))
                
                response = await client.post(
                    f"https://api.replicate.com/v1/models/{model}/predictions",
                    headers=headers,
                    json=payload,
                    timeout=10.0
                )
                
                if response.status_code != 201:
                    error_data = response.json() if response.content else {}
                    error_detail = error_data.get('detail', 'Unknown error')
                    
                    # Enhanced error logging
                    print(f"❌ REPLICATE API ERROR: {response.status_code}")
                    print(f"   Model: {model}")
                    print(f"   Error Detail: {error_detail}")
                    print(f"   Full Error Response: {error_data}")
                    print(f"   Request Payload: {payload}")
                    
                    # Handle NSFW content detection gracefully
                    if 'nsfw' in error_detail.lower() or 'inappropriate' in error_detail.lower():
                        raise HTTPException(
                            status_code=400,
                            detail="Content not allowed. Please modify your prompt to avoid inappropriate content."
                        )
                    
                    raise HTTPException(
                        status_code=500,
                        detail=f"Image generation service error: {error_detail}"
                    )
                    
            except httpx.TimeoutException as e:
                print(f"⏱️ REPLICATE TIMEOUT: Request to {model} timed out after 10s")
                print(f"   Prompt: {prompt[:100]}...")
                raise HTTPException(
                    status_code=500,
                    detail="Image generation service timeout - please try again"
                )
            except httpx.RequestError as e:
                print(f"🌐 REPLICATE CONNECTION ERROR: {str(e)}")
                print(f"   Model: {model}")
                print(f"   Prompt: {prompt[:100]}...")
                raise HTTPException(
                    status_code=500,
                    detail="Unable to connect to image generation service"
                )
            
            prediction = response.json()
            prediction_id = prediction["id"]
            print(f"✅ REPLICATE PREDICTION STARTED: {prediction_id}")
        
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
                    
                    # Enhanced error logging for failed predictions
                    print(f"❌ REPLICATE PREDICTION FAILED: {prediction_id}")
                    print(f"   Model: {model}")
                    print(f"   Error Message: {error_msg}")
                    print(f"   Full Result: {result}")
                    print(f"   Elapsed Time: {elapsed_time}s")
                    
                    # Handle NSFW content detection gracefully
                    if 'nsfw' in error_msg.lower() or 'inappropriate' in error_msg.lower():
                        raise HTTPException(
                            status_code=400,
                            detail="Content not allowed. Please modify your prompt to avoid inappropriate content."
                        )
                    
                    raise HTTPException(status_code=500, detail=f"Image generation failed: {error_msg}")
        
        # Timeout - enhanced logging
        print(f"⏱️ REPLICATE PREDICTION TIMEOUT: {prediction_id}")
        print(f"   Model: {model}")
        print(f"   Max Wait Time: {max_wait_time}s")
        print(f"   Total Elapsed: {elapsed_time}s")
        print(f"   Last Status: {result.get('status', 'unknown') if 'result' in locals() else 'unknown'}")
        
        raise HTTPException(status_code=500, detail="Image generation timed out")
    
    async def _generate_with_gen4_image(
        self,
        model: str,
        prompt: str,
        style: ImageStyle,
        image_size: ImageSize,
        reference_people: list[ImageReferencePerson]
    ) -> Tuple[str, dict]:
        """Generate image using Runway Gen-4 Image with multiple face references (up to 3)"""
        
        # Map our styles to Gen-4 optimized prompts
        style_prompts = {
            ImageStyle.REALISTIC: "photorealistic, high quality, professional photography, detailed",
            ImageStyle.ARTISTIC: "artistic, painted style, fine art, creative composition",
            ImageStyle.CARTOON: "cartoon style, animated, colorful, stylized illustration",
            ImageStyle.ABSTRACT: "abstract art, artistic interpretation, creative",
            ImageStyle.VINTAGE: "vintage style, retro aesthetic, classic photography",
            ImageStyle.MODERN: "modern, contemporary, clean aesthetic"
        }
        
        # Build enhanced prompt with style
        enhanced_prompt = f"{prompt}, {style_prompts[style]}"
        
        # Map image sizes to Gen-4 aspect ratios
        size_map = {
            ImageSize.STANDARD: "1:1",
            ImageSize.LARGE: "4:3", 
            ImageSize.SQUARE: "1:1"
        }
        
        aspect_ratio = size_map[image_size]
        
        # Prepare reference images and tags (up to 3 people)
        reference_images = []
        reference_tags = []
        
        for person in reference_people[:3]:  # Limit to 3 people
            if person.photo_url:
                reference_images.append(person.photo_url)
                
                # Extract person name and create alphanumeric tag
                person_name = person.description.split(" (")[0] if " (" in person.description else person.description
                # Create clean alphanumeric tag from name (Gen-4 requirements: 3-15 chars, start with letter)
                import re
                tag = re.sub(r'[^a-zA-Z0-9]', '', person_name.lower())[:15]  # Remove non-alphanumeric, max 15 chars
                if not tag or not tag[0].isalpha():  # Ensure starts with letter
                    tag = f"person{len(reference_tags)+1}"
                elif len(tag) < 3:  # Ensure minimum 3 chars
                    tag = f"{tag}{len(reference_tags)+1}"
                
                reference_tags.append(tag)
                
                # Add person reference to prompt using their name as tag
                enhanced_prompt += f", featuring @{tag} as {person_name}"
        
        # Add quality enhancers
        enhanced_prompt += ", high quality, detailed"
        
        payload = {
            "input": {
                "prompt": enhanced_prompt,
                "reference_images": reference_images,
                "reference_tags": reference_tags,
                "aspect_ratio": aspect_ratio,
                "resolution": "1080p"
            }
        }
        
        headers = {
            "Authorization": f"Token {self.replicate_api_token}",
            "Content-Type": "application/json"
        }
        
        # Start prediction
        async with httpx.AsyncClient() as client:
            try:
                print(f"🤖 REPLICATE REQUEST: {model}")
                print(f"🎨 FULL ENHANCED PROMPT: {enhanced_prompt}")
                print(f"📏 PROMPT LENGTH: {len(enhanced_prompt)} characters")
                print(f"👥 REFERENCE PEOPLE: {len(reference_people)}")
                if 'width' in locals() and 'height' in locals():
                    print(f"🖼️ IMAGE SIZE: {width}x{height}")
                elif 'dimensions' in locals():
                    print(f"🖼️ IMAGE SIZE: {dimensions.get('width', 'unknown')}x{dimensions.get('height', 'unknown')}")
                print(f"⚙️ REQUEST PAYLOAD:")
                print(json.dumps(payload, indent=2))
                
                response = await client.post(
                    f"https://api.replicate.com/v1/models/{model}/predictions",
                    headers=headers,
                    json=payload,
                    timeout=10.0
                )
                
                if response.status_code != 201:
                    error_data = response.json() if response.content else {}
                    error_detail = error_data.get('detail', 'Unknown error')
                    
                    # Enhanced error logging
                    print(f"❌ REPLICATE API ERROR: {response.status_code}")
                    print(f"   Model: {model}")
                    print(f"   Error Detail: {error_detail}")
                    print(f"   Full Error Response: {error_data}")
                    print(f"   Request Payload: {payload}")
                    
                    # Handle NSFW content detection gracefully
                    if 'nsfw' in error_detail.lower() or 'inappropriate' in error_detail.lower():
                        raise HTTPException(
                            status_code=400,
                            detail="Content not allowed. Please modify your prompt to avoid inappropriate content."
                        )
                    
                    raise HTTPException(
                        status_code=500,
                        detail=f"Image generation service error: {error_detail}"
                    )
                    
            except httpx.TimeoutException as e:
                print(f"⏱️ REPLICATE TIMEOUT: Request to {model} timed out after 10s")
                print(f"   Prompt: {prompt[:100]}...")
                raise HTTPException(
                    status_code=500,
                    detail="Image generation service timeout - please try again"
                )
            except httpx.RequestError as e:
                print(f"🌐 REPLICATE CONNECTION ERROR: {str(e)}")
                print(f"   Model: {model}")
                print(f"   Prompt: {prompt[:100]}...")
                raise HTTPException(
                    status_code=500,
                    detail="Unable to connect to image generation service"
                )
            
            prediction = response.json()
            prediction_id = prediction["id"]
            print(f"✅ REPLICATE PREDICTION STARTED: {prediction_id}")
        
        # Poll for completion
        max_wait_time = 180  # 3 minutes (Gen-4 may take longer)
        poll_interval = 3    # 3 seconds
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
                        "model_used": "runway-gen4-image",
                        "api_provider": "replicate",
                        "enhanced_prompt": enhanced_prompt,
                        "prediction_id": prediction_id,
                        "reference_people_count": len(reference_people),
                        "generation_approach": "gen4_multiple_faces",
                        "reference_images": reference_images,
                        "reference_tags": reference_tags,
                        "aspect_ratio": aspect_ratio
                    }
                    
                    return image_url, metadata
                
                elif status == "failed":
                    error_msg = result.get("error", "Unknown generation error")
                    
                    # Enhanced error logging for failed predictions
                    print(f"❌ REPLICATE PREDICTION FAILED: {prediction_id}")
                    print(f"   Model: {model}")
                    print(f"   Error Message: {error_msg}")
                    print(f"   Full Result: {result}")
                    print(f"   Elapsed Time: {elapsed_time}s")
                    
                    # Handle NSFW content detection gracefully
                    if 'nsfw' in error_msg.lower() or 'inappropriate' in error_msg.lower():
                        raise HTTPException(
                            status_code=400,
                            detail="Content not allowed. Please modify your prompt to avoid inappropriate content."
                        )
                    
                    raise HTTPException(status_code=500, detail=f"Image generation failed: {error_msg}")
        
        # Timeout - enhanced logging
        print(f"⏱️ REPLICATE PREDICTION TIMEOUT: {prediction_id}")
        print(f"   Model: {model}")
        print(f"   Max Wait Time: {max_wait_time}s")
        print(f"   Total Elapsed: {elapsed_time}s")
        print(f"   Last Status: {result.get('status', 'unknown') if 'result' in locals() else 'unknown'}")
        
        raise HTTPException(status_code=500, detail="Image generation timed out")


# Global instance
image_generation_service = ImageGenerationService()