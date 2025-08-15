"""AI Image generation service for OpenAI DALL-E and Replicate integration"""

import asyncio
import json
import os
import time

import httpx
from fastapi import HTTPException
from models import ImageReferencePerson, ImageSize, ImageStyle


class ImageGenerationService:
    """Service for generating AI images using Replicate FLUX"""

    def __init__(self):
        self.replicate_api_token = os.getenv("REPLICATE_API_TOKEN")

        if not self.replicate_api_token:
            raise ValueError("Missing REPLICATE_API_TOKEN environment variable")

    async def _get_image_model_config(self) -> dict:
        """Get image model configuration from app config (reads from parameters JSON)"""
        try:
            from shared.database import get_db
            from shared.json_utils import parse_jsonb_field

            # Get the Story app ID (which has image generation capabilities)
            STORY_APP_ID = "fairydust-story"

            # Fetch the single image model configuration record
            db = await get_db()
            model_record = await db.fetch_one(
                """
                SELECT provider, model_id, parameters
                FROM app_model_configs
                WHERE app_id = (SELECT id FROM apps WHERE slug = $1)
                AND model_type = 'image'
                AND is_enabled = true
                """,
                STORY_APP_ID,
            )

            if model_record:
                # Parse parameters to get standard_model and reference_model
                params = parse_jsonb_field(
                    model_record["parameters"], default={}, field_name="image_parameters"
                )

                # Extract models from parameters (admin portal stores them here)
                standard_model = params.get("standard_model", model_record["model_id"])
                reference_model = params.get("reference_model", "runwayml/gen4-image")
                
                # Build fallback list from global fallbacks if available
                fallback_models = ["stability-ai/sdxl", "black-forest-labs/flux-schnell"]
                
                config_result = {
                    "standard_model": standard_model,
                    "reference_model": reference_model,
                    "fallback_models": fallback_models,
                }

                print(f"✅ IMAGE_CONFIG: Loaded image config from database")
                print(f"   Standard: {config_result['standard_model']}")
                print(f"   Reference: {config_result['reference_model']}")
                print(f"   Fallbacks: {config_result['fallback_models']}")

                return config_result

            # Return defaults if no config found
            print("⚠️ IMAGE_CONFIG: No image models found in database, using defaults")
            return {
                "standard_model": "black-forest-labs/flux-1.1-pro",
                "reference_model": "runwayml/gen4-image",
                "fallback_models": ["stability-ai/sdxl", "black-forest-labs/flux-schnell"],
            }

        except Exception as e:
            print(f"⚠️ IMAGE_MODEL_CONFIG: Error loading config: {e}")
            # Return defaults on error
            return {
                "standard_model": "black-forest-labs/flux-1.1-pro",
                "reference_model": "runwayml/gen4-image",
                "fallback_models": ["stability-ai/sdxl", "black-forest-labs/flux-schnell"],
            }

    async def generate_image(
        self,
        prompt: str,
        style: ImageStyle,
        image_size: ImageSize,
        reference_people: list[ImageReferencePerson],
        image_id: str = None,
    ) -> tuple[str, dict]:
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
        reference_people: list[ImageReferencePerson],
        image_id: str = None,
    ) -> tuple[str, dict]:
        """Generate image using Replicate - selects appropriate model based on reference people"""

        # Get image model configuration from app config
        image_models = await self._get_image_model_config()

        # Choose model based on whether reference people are provided
        if reference_people:
            # Use configured model for multiple face references (up to 3)
            model = image_models.get("reference_model", "runwayml/gen4-image")
            
            # Check if it's a gen4-turbo model (supports both with and without reference people)
            if "gen4-image-turbo" in model:
                return await self._generate_with_gen4_turbo(
                    model, prompt, style, image_size, reference_people, image_id
                )
            else:
                return await self._generate_with_gen4_image(
                    model, prompt, style, image_size, reference_people, image_id
                )
        else:
            # Use configured model for text-only generation with fallback support
            primary_model = image_models.get("standard_model", "black-forest-labs/flux-1.1-pro")
            fallback_models = image_models.get(
                "fallback_models", ["stability-ai/sdxl", "black-forest-labs/flux-schnell"]
            )

            # Try primary model first
            try:
                print(f"🎯 IMAGE_GENERATION: Attempting primary model: {primary_model}")
                
                # Check if primary model is gen4-turbo (can handle text-only generation)
                if "gen4-image-turbo" in primary_model:
                    return await self._generate_with_gen4_turbo(
                        primary_model, prompt, style, image_size, reference_people, image_id
                    )
                else:
                    return await self._generate_standard_replicate(
                        primary_model, prompt, style, image_size, reference_people, image_id
                    )
            except Exception as e:
                print(f"❌ IMAGE_GENERATION: Primary model {primary_model} failed: {str(e)}")

                # Try fallback models
                for fallback_model in fallback_models:
                    try:
                        print(f"🔄 IMAGE_GENERATION: Attempting fallback model: {fallback_model}")
                        
                        # Check if fallback model is gen4-turbo
                        if "gen4-image-turbo" in fallback_model:
                            result = await self._generate_with_gen4_turbo(
                                fallback_model, prompt, style, image_size, reference_people, image_id
                            )
                        else:
                            result = await self._generate_standard_replicate(
                                fallback_model, prompt, style, image_size, reference_people, image_id
                            )
                        # Add fallback metadata
                        url, metadata = result
                        metadata["was_fallback"] = True
                        metadata[
                            "fallback_reason"
                        ] = f"Primary model {primary_model} failed: {str(e)}"
                        metadata["primary_model_attempted"] = primary_model
                        return url, metadata
                    except Exception as fallback_error:
                        print(
                            f"❌ IMAGE_GENERATION: Fallback model {fallback_model} also failed: {str(fallback_error)}"
                        )
                        continue

                # All models failed
                raise HTTPException(
                    status_code=500,
                    detail=f"All image generation models failed. Primary: {primary_model}, Fallbacks: {fallback_models}",
                )

    async def _generate_standard_replicate(
        self,
        model: str,
        prompt: str,
        style: ImageStyle,
        image_size: ImageSize,
        reference_people: list[ImageReferencePerson],
        image_id: str = None,
    ) -> tuple[str, dict]:
        """Generate image using standard Replicate models (text-only)"""

        # Detect model type for specific handling
        is_seedream = "seedream" in model.lower()  # ByteDance SeeDream-3 via Replicate
        is_flux = "flux" in model.lower()  # Black Forest Labs FLUX models
        is_sdxl = "sdxl" in model.lower()  # Stability AI SDXL

        print(f"🎭 REPLICATE GENERATION STARTING - Model: {model}")
        print(f"   Original prompt: {prompt}")
        print(f"   Style: {style.value}")
        print(f"   Image size: {image_size.value}")

        # Map our styles to model-optimized prompts
        if is_seedream:
            # SeeDream-3 style optimization
            style_prompts = {
                ImageStyle.REALISTIC: "photorealistic, highly detailed, professional photography, 8K resolution",
                ImageStyle.ARTISTIC: "artistic style, creative composition, masterpiece, fine art quality",
                ImageStyle.CARTOON: "cartoon style, animated, colorful, clean lines, stylized illustration",
                ImageStyle.ABSTRACT: "abstract art, creative interpretation, modern artistic style",
                ImageStyle.VINTAGE: "vintage style, retro aesthetic, classic photography, nostalgic",
                ImageStyle.MODERN: "modern style, contemporary design, clean and minimalist",
            }
        elif is_sdxl:
            # SDXL style optimization (more concise prompts work better)
            style_prompts = {
                ImageStyle.REALISTIC: "photorealistic, detailed, professional photo",
                ImageStyle.ARTISTIC: "artistic painting, fine art style",
                ImageStyle.CARTOON: "cartoon style, animated, colorful",
                ImageStyle.ABSTRACT: "abstract art, modern composition",
                ImageStyle.VINTAGE: "vintage photo, retro style, nostalgic",
                ImageStyle.MODERN: "modern digital art, contemporary",
            }
        else:
            # FLUX and other models style optimization
            style_prompts = {
                ImageStyle.REALISTIC: "photorealistic, professional photography, high detail, sharp focus, studio lighting",
                ImageStyle.ARTISTIC: "artistic masterpiece, oil painting style, fine art, brush strokes, gallery quality",
                ImageStyle.CARTOON: "cartoon illustration, animated style, vibrant colors, clean lines, stylized",
                ImageStyle.ABSTRACT: "abstract art, modern artistic interpretation, geometric shapes, color theory",
                ImageStyle.VINTAGE: "vintage photography, retro aesthetic, film grain, sepia tones, nostalgic",
                ImageStyle.MODERN: "modern digital art, contemporary style, minimalist, clean composition",
            }

        # Build enhanced prompt
        enhanced_prompt = f"{prompt}, {style_prompts[style]}"

        # Add people descriptions if provided (text-only generation)
        if reference_people:
            people_descriptions = []
            for person in reference_people:
                people_descriptions.append(f"person ({person.description})")
            enhanced_prompt += f", featuring {', '.join(people_descriptions)}"
            print(f"   Added {len(reference_people)} people descriptions")

        # Add quality enhancers
        enhanced_prompt += ", high quality, detailed, professional"

        # Map image sizes based on model capabilities
        if is_seedream:
            # SeeDream-3 supports custom dimensions up to 2048x2048
            size_map = {
                ImageSize.STANDARD: {"width": 1024, "height": 1024, "aspect_ratio": "1:1"},
                ImageSize.LARGE: {"width": 1024, "height": 1440, "aspect_ratio": "3:4"},
                ImageSize.SQUARE: {"width": 1024, "height": 1024, "aspect_ratio": "1:1"},
            }
        elif is_sdxl:
            # SDXL optimal dimensions
            size_map = {
                ImageSize.STANDARD: {"width": 1024, "height": 1024},
                ImageSize.LARGE: {"width": 1024, "height": 1536},  # 2:3 aspect ratio
                ImageSize.SQUARE: {"width": 1024, "height": 1024},
            }
        else:
            # FLUX and other models (FLUX max dimensions: 1440x1440)
            size_map = {
                ImageSize.STANDARD: {"width": 1024, "height": 1024},
                ImageSize.LARGE: {"width": 1024, "height": 1440},
                ImageSize.SQUARE: {"width": 1024, "height": 1024},
            }

        dimensions = size_map[image_size]

        # Build payload based on model type
        if is_seedream:
            # SeeDream-3 specific parameters
            payload = {
                "input": {
                    "prompt": enhanced_prompt,
                    "aspect_ratio": dimensions.get("aspect_ratio", "1:1"),
                    "size": "regular",  # small, regular, big
                    "guidance_scale": 2.5,  # Default guidance scale
                }
            }
            # Only add width/height if using custom aspect ratio
            if dimensions.get("aspect_ratio") == "custom":
                payload["input"]["width"] = dimensions["width"]
                payload["input"]["height"] = dimensions["height"]
        elif is_sdxl:
            # SDXL specific parameters
            payload = {
                "input": {
                    "prompt": enhanced_prompt,
                    "width": dimensions["width"],
                    "height": dimensions["height"],
                    "num_outputs": 1,
                    "scheduler": "DPMSolverMultistep",  # Fast and high quality
                    "num_inference_steps": 25,  # Good balance of speed/quality
                    "guidance_scale": 7.5,  # Standard guidance for SDXL
                    "apply_watermark": False,
                    "negative_prompt": "ugly, blurry, low quality, distorted, disfigured, deformed, glitch, noise, grainy, low resolution",
                }
            }
        else:
            # FLUX and other models - original parameter structure
            payload = {
                "input": {
                    "prompt": enhanced_prompt,
                    "width": dimensions["width"],
                    "height": dimensions["height"],
                    "output_format": "png",
                    "safety_tolerance": 2,
                    "prompt_upsampling": False,
                }
            }

        headers = {
            "Authorization": f"Token {self.replicate_api_token}",
            "Content-Type": "application/json",
        }

        # Start prediction
        async with httpx.AsyncClient() as client:
            try:
                print(f"🤖 REPLICATE REQUEST: {model}")
                print(f"🎨 FULL ENHANCED PROMPT: {enhanced_prompt}")
                print(f"📏 PROMPT LENGTH: {len(enhanced_prompt)} characters")
                print(f"👥 REFERENCE PEOPLE: {len(reference_people)}")
                if "width" in locals() and "height" in locals():
                    print(f"🖼️ IMAGE SIZE: {width}x{height}")
                elif "dimensions" in locals():
                    print(
                        f"🖼️ IMAGE SIZE: {dimensions.get('width', 'unknown')}x{dimensions.get('height', 'unknown')}"
                    )
                print("⚙️ REQUEST PAYLOAD:")
                print(json.dumps(payload, indent=2))

                # Time the initial API request
                api_request_start = time.time()
                response = await client.post(
                    f"https://api.replicate.com/v1/models/{model}/predictions",
                    headers=headers,
                    json=payload,
                    timeout=10.0,
                )
                api_request_time = time.time() - api_request_start
                print(f"⏱️ API_TIMING: Initial request took {api_request_time:.2f}s")

                if response.status_code != 201:
                    error_data = response.json() if response.content else {}
                    error_detail = error_data.get("detail", "Unknown error")

                    # Enhanced error logging
                    print(f"❌ REPLICATE API ERROR: {response.status_code}")
                    print(f"   Model: {model}")
                    print(f"   Error Detail: {error_detail}")
                    print(f"   Full Error Response: {error_data}")
                    print(f"   Request Payload: {payload}")

                    # Handle NSFW content detection gracefully
                    if "nsfw" in error_detail.lower() or "inappropriate" in error_detail.lower():
                        raise HTTPException(
                            status_code=400,
                            detail="Content not allowed. Please modify your prompt to avoid inappropriate content.",
                        )

                    raise HTTPException(
                        status_code=500, detail=f"Image generation service error: {error_detail}"
                    )

            except httpx.TimeoutException:
                print(f"⏱️ REPLICATE TIMEOUT: Request to {model} timed out after 10s")
                print(f"   Prompt: {prompt[:100]}...")
                raise HTTPException(
                    status_code=500, detail="Image generation service timeout - please try again"
                )
            except httpx.RequestError as e:
                print(f"🌐 REPLICATE CONNECTION ERROR: {str(e)}")
                print(f"   Model: {model}")
                print(f"   Prompt: {prompt[:100]}...")
                raise HTTPException(
                    status_code=500, detail="Unable to connect to image generation service"
                )

            prediction = response.json()
            prediction_id = prediction["id"]
            print(f"✅ REPLICATE PREDICTION STARTED: {prediction_id}")

        # Poll for completion with dynamic intervals
        max_wait_time = 120  # 2 minutes
        elapsed_time = 0
        poll_start_time = time.time()
        poll_count = 0

        # Dynamic polling intervals: start fast, then slow down
        poll_intervals = [1, 1, 2, 2, 3, 4, 5, 6, 7, 8, 10]  # seconds
        poll_index = 0

        print(f"⏱️ POLLING_TIMING: Starting to poll prediction {prediction_id}")

        async with httpx.AsyncClient() as client:
            while elapsed_time < max_wait_time:
                # Use dynamic interval
                current_interval = poll_intervals[min(poll_index, len(poll_intervals) - 1)]
                await asyncio.sleep(current_interval)
                elapsed_time += current_interval
                poll_index += 1
                poll_count += 1

                poll_request_start = time.time()
                poll_response = await client.get(
                    f"https://api.replicate.com/v1/predictions/{prediction_id}", headers=headers
                )
                poll_request_time = time.time() - poll_request_start

                if poll_response.status_code != 200:
                    raise HTTPException(status_code=500, detail="Failed to check prediction status")

                result = poll_response.json()
                status = result["status"]

                print(
                    f"⏱️ POLLING_TIMING: Poll #{poll_count} after {elapsed_time}s - Status: {status} (poll took {poll_request_time:.3f}s)"
                )

                if status == "succeeded":
                    total_poll_time = time.time() - poll_start_time
                    print(
                        f"✅ POLLING_TIMING: Prediction completed! Total polling time: {total_poll_time:.2f}s over {poll_count} polls"
                    )

                    image_url = (
                        result["output"][0]
                        if isinstance(result["output"], list)
                        else result["output"]
                    )

                    # Determine generation approach based on model
                    if is_seedream:
                        approach = "seedream_text_to_image"
                    elif is_flux:
                        approach = "flux_text_to_image"
                    elif is_sdxl:
                        approach = "sdxl_text_to_image"
                    else:
                        approach = "replicate_text_to_image"

                    metadata = {
                        "model_used": model,  # Use actual model name instead of hardcoded
                        "api_provider": "replicate",
                        "enhanced_prompt": enhanced_prompt,
                        "prediction_id": prediction_id,
                        "reference_people_count": len(reference_people),
                        "generation_approach": approach,
                        "api_request_time": api_request_time,
                        "polling_time": total_poll_time,
                        "poll_count": poll_count,
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
                    if (
                        "nsfw" in error_msg.lower()
                        or "inappropriate" in error_msg.lower()
                        or "flagged as sensitive" in error_msg.lower()
                        or "(e005)" in error_msg.lower()
                        or "sensitive content" in error_msg.lower()
                    ):
                        raise HTTPException(
                            status_code=400,
                            detail="Content not allowed. Please modify your prompt to avoid inappropriate content.",
                        )

                    raise HTTPException(
                        status_code=500, detail=f"Image generation failed: {error_msg}"
                    )

        # Timeout - enhanced logging
        print(f"⏱️ REPLICATE PREDICTION TIMEOUT: {prediction_id}")
        print(f"   Model: {model}")
        print(f"   Max Wait Time: {max_wait_time}s")
        print(f"   Total Elapsed: {elapsed_time}s")
        print(
            f"   Last Status: {result.get('status', 'unknown') if 'result' in locals() else 'unknown'}"
        )

        raise HTTPException(status_code=500, detail="Image generation timed out")

    async def _generate_with_gen4_image(
        self,
        model: str,
        prompt: str,
        style: ImageStyle,
        image_size: ImageSize,
        reference_people: list[ImageReferencePerson],
        image_id: str = None,
    ) -> tuple[str, dict]:
        """Generate image using Runway Gen-4 Image with multiple face references (up to 3)"""

        # Map our styles to Gen-4 optimized prompts
        style_prompts = {
            ImageStyle.REALISTIC: "photorealistic, high quality, professional photography, detailed",
            ImageStyle.ARTISTIC: "artistic, painted style, fine art, creative composition",
            ImageStyle.CARTOON: "cartoon style, animated, colorful, stylized illustration",
            ImageStyle.ABSTRACT: "abstract art, artistic interpretation, creative",
            ImageStyle.VINTAGE: "vintage style, retro aesthetic, classic photography",
            ImageStyle.MODERN: "modern, contemporary, clean aesthetic",
        }

        # Build enhanced prompt with style
        enhanced_prompt = f"{prompt}, {style_prompts[style]}"

        # Map image sizes to Gen-4 aspect ratios
        size_map = {ImageSize.STANDARD: "1:1", ImageSize.LARGE: "4:3", ImageSize.SQUARE: "1:1"}

        aspect_ratio = size_map[image_size]

        # Prepare reference images and tags (up to 3 people)
        reference_images = []
        reference_tags = []

        for person in reference_people[:3]:  # Limit to 3 people
            if person.photo_url:
                reference_images.append(person.photo_url)

                # Extract person name and create alphanumeric tag
                person_name = (
                    person.description.split(" (")[0]
                    if " (" in person.description
                    else person.description
                )
                # Create clean alphanumeric tag from name (Gen-4 requirements: 3-15 chars, start with letter)
                import re

                tag = re.sub(r"[^a-zA-Z0-9]", "", person_name.lower())[
                    :15
                ]  # Remove non-alphanumeric, max 15 chars
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
                "resolution": "720p",
            }
        }

        headers = {
            "Authorization": f"Token {self.replicate_api_token}",
            "Content-Type": "application/json",
        }

        # Start prediction
        async with httpx.AsyncClient() as client:
            try:
                print(f"🤖 REPLICATE REQUEST: {model}")
                print(f"🎨 FULL ENHANCED PROMPT: {enhanced_prompt}")
                print(f"📏 PROMPT LENGTH: {len(enhanced_prompt)} characters")
                print(f"👥 REFERENCE PEOPLE: {len(reference_people)}")
                if "width" in locals() and "height" in locals():
                    print(f"🖼️ IMAGE SIZE: {width}x{height}")
                elif "dimensions" in locals():
                    print(
                        f"🖼️ IMAGE SIZE: {dimensions.get('width', 'unknown')}x{dimensions.get('height', 'unknown')}"
                    )
                print("⚙️ REQUEST PAYLOAD:")
                print(json.dumps(payload, indent=2))

                # Time the initial API request
                api_request_start = time.time()
                response = await client.post(
                    f"https://api.replicate.com/v1/models/{model}/predictions",
                    headers=headers,
                    json=payload,
                    timeout=10.0,
                )
                api_request_time = time.time() - api_request_start
                print(f"⏱️ API_TIMING: Initial request took {api_request_time:.2f}s")

                if response.status_code != 201:
                    error_data = response.json() if response.content else {}
                    error_detail = error_data.get("detail", "Unknown error")

                    # Enhanced error logging
                    print(f"❌ REPLICATE API ERROR: {response.status_code}")
                    print(f"   Model: {model}")
                    print(f"   Error Detail: {error_detail}")
                    print(f"   Full Error Response: {error_data}")
                    print(f"   Request Payload: {payload}")

                    # Handle NSFW content detection gracefully
                    if "nsfw" in error_detail.lower() or "inappropriate" in error_detail.lower():
                        raise HTTPException(
                            status_code=400,
                            detail="Content not allowed. Please modify your prompt to avoid inappropriate content.",
                        )

                    raise HTTPException(
                        status_code=500, detail=f"Image generation service error: {error_detail}"
                    )

            except httpx.TimeoutException:
                print(f"⏱️ REPLICATE TIMEOUT: Request to {model} timed out after 10s")
                print(f"   Prompt: {prompt[:100]}...")
                raise HTTPException(
                    status_code=500, detail="Image generation service timeout - please try again"
                )
            except httpx.RequestError as e:
                print(f"🌐 REPLICATE CONNECTION ERROR: {str(e)}")
                print(f"   Model: {model}")
                print(f"   Prompt: {prompt[:100]}...")
                raise HTTPException(
                    status_code=500, detail="Unable to connect to image generation service"
                )

            prediction = response.json()
            prediction_id = prediction["id"]
            print(f"✅ REPLICATE PREDICTION STARTED: {prediction_id}")

        # Poll for completion
        max_wait_time = 180  # 3 minutes (Gen-4 may take longer)
        poll_interval = 3  # 3 seconds
        elapsed_time = 0
        poll_start_time = time.time()
        poll_count = 0

        print(f"⏱️ POLLING_TIMING: Starting to poll Gen-4 prediction {prediction_id}")

        async with httpx.AsyncClient() as client:
            while elapsed_time < max_wait_time:
                await asyncio.sleep(poll_interval)
                elapsed_time += poll_interval
                poll_count += 1

                poll_request_start = time.time()
                poll_response = await client.get(
                    f"https://api.replicate.com/v1/predictions/{prediction_id}", headers=headers
                )
                poll_request_time = time.time() - poll_request_start

                if poll_response.status_code != 200:
                    raise HTTPException(status_code=500, detail="Failed to check prediction status")

                result = poll_response.json()
                status = result["status"]

                print(
                    f"⏱️ POLLING_TIMING: Gen-4 Poll #{poll_count} after {elapsed_time}s - Status: {status} (poll took {poll_request_time:.3f}s) - Image: {image_id or 'unknown'}"
                )

                if status == "succeeded":
                    total_poll_time = time.time() - poll_start_time
                    print(
                        f"✅ POLLING_TIMING: Gen-4 prediction completed! Total polling time: {total_poll_time:.2f}s over {poll_count} polls"
                    )

                    image_url = (
                        result["output"][0]
                        if isinstance(result["output"], list)
                        else result["output"]
                    )

                    metadata = {
                        "model_used": model,  # Use actual model name instead of hardcoded
                        "api_provider": "replicate",
                        "enhanced_prompt": enhanced_prompt,
                        "prediction_id": prediction_id,
                        "reference_people_count": len(reference_people),
                        "generation_approach": "gen4_multiple_faces",
                        "reference_images": reference_images,
                        "reference_tags": reference_tags,
                        "aspect_ratio": aspect_ratio,
                        "api_request_time": api_request_time,
                        "polling_time": total_poll_time,
                        "poll_count": poll_count,
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
                    if (
                        "nsfw" in error_msg.lower()
                        or "inappropriate" in error_msg.lower()
                        or "flagged as sensitive" in error_msg.lower()
                        or "(e005)" in error_msg.lower()
                        or "sensitive content" in error_msg.lower()
                    ):
                        raise HTTPException(
                            status_code=400,
                            detail="Content not allowed. Please modify your prompt to avoid inappropriate content.",
                        )

                    raise HTTPException(
                        status_code=500, detail=f"Image generation failed: {error_msg}"
                    )

        # Timeout - enhanced logging
        print(f"⏱️ REPLICATE PREDICTION TIMEOUT: {prediction_id}")
        print(f"   Model: {model}")
        print(f"   Max Wait Time: {max_wait_time}s")
        print(f"   Total Elapsed: {elapsed_time}s")
        print(
            f"   Last Status: {result.get('status', 'unknown') if 'result' in locals() else 'unknown'}"
        )

        raise HTTPException(status_code=500, detail="Image generation timed out")

    async def _generate_with_gen4_turbo(
        self,
        model: str,
        prompt: str,
        style: ImageStyle,
        image_size: ImageSize,
        reference_people: list[ImageReferencePerson],
        image_id: str = None,
    ) -> tuple[str, dict]:
        """Generate image using Runway Gen-4 Turbo (supports both text-only and reference images)"""

        # Map our styles to Gen-4 Turbo optimized prompts
        style_prompts = {
            ImageStyle.REALISTIC: "photorealistic, high quality, professional photography, detailed",
            ImageStyle.ARTISTIC: "artistic, painted style, fine art, creative composition",
            ImageStyle.CARTOON: "cartoon style, animated, colorful, stylized illustration",
            ImageStyle.ABSTRACT: "abstract art, artistic interpretation, creative",
            ImageStyle.VINTAGE: "vintage style, retro aesthetic, classic photography",
            ImageStyle.MODERN: "modern, contemporary, clean aesthetic",
        }

        # Build enhanced prompt with style
        enhanced_prompt = f"{prompt}, {style_prompts[style]}"

        # Map image sizes to Gen-4 Turbo aspect ratios
        size_map = {
            ImageSize.STANDARD: "16:9",  # Standard widescreen
            ImageSize.LARGE: "4:3",      # Portrait-ish 
            ImageSize.SQUARE: "1:1"      # Square
        }

        aspect_ratio = size_map[image_size]

        # Prepare reference images and tags if people are provided
        reference_images = []
        reference_tags = []

        if reference_people:
            for person in reference_people[:3]:  # Limit to 3 people
                if person.photo_url:
                    reference_images.append(person.photo_url)

                    # Extract person name and create alphanumeric tag
                    person_name = (
                        person.description.split(" (")[0]
                        if " (" in person.description
                        else person.description
                    )
                    # Create clean alphanumeric tag from name (Gen-4 requirements: 3-15 chars, start with letter)
                    import re

                    tag = re.sub(r"[^a-zA-Z0-9]", "", person_name.lower())[
                        :15
                    ]  # Remove non-alphanumeric, max 15 chars
                    if not tag or not tag[0].isalpha():  # Ensure starts with letter
                        tag = f"person{len(reference_tags)+1}"
                    elif len(tag) < 3:  # Ensure minimum 3 chars
                        tag = f"{tag}{len(reference_tags)+1}"

                    reference_tags.append(tag)

                    # Add person reference to prompt using their name as tag
                    enhanced_prompt += f", featuring @{tag} as {person_name}"

        # Add quality enhancers
        enhanced_prompt += ", high quality, detailed"

        # Build payload - reference images are optional for gen4-turbo
        payload = {
            "input": {
                "prompt": enhanced_prompt,
                "aspect_ratio": aspect_ratio,
                "resolution": "1080p",  # Default to high quality
            }
        }

        # Only add reference data if we have reference people
        if reference_images and reference_tags:
            payload["input"]["reference_images"] = reference_images
            payload["input"]["reference_tags"] = reference_tags

        headers = {
            "Authorization": f"Token {self.replicate_api_token}",
            "Content-Type": "application/json",
        }

        # Start prediction
        async with httpx.AsyncClient() as client:
            try:
                print(f"🤖 REPLICATE REQUEST: {model}")
                print(f"🎨 FULL ENHANCED PROMPT: {enhanced_prompt}")
                print(f"📏 PROMPT LENGTH: {len(enhanced_prompt)} characters")
                print(f"👥 REFERENCE PEOPLE: {len(reference_people)}")
                print(f"🖼️ ASPECT RATIO: {aspect_ratio}")
                print("⚙️ REQUEST PAYLOAD:")
                print(json.dumps(payload, indent=2))

                # Time the initial API request
                api_request_start = time.time()
                response = await client.post(
                    f"https://api.replicate.com/v1/models/{model}/predictions",
                    headers=headers,
                    json=payload,
                    timeout=10.0,
                )
                api_request_time = time.time() - api_request_start
                print(f"⏱️ API_TIMING: Initial request took {api_request_time:.2f}s")

                if response.status_code != 201:
                    error_data = response.json() if response.content else {}
                    error_detail = error_data.get("detail", "Unknown error")

                    # Enhanced error logging
                    print(f"❌ REPLICATE API ERROR: {response.status_code}")
                    print(f"   Model: {model}")
                    print(f"   Error Detail: {error_detail}")
                    print(f"   Full Error Response: {error_data}")
                    print(f"   Request Payload: {payload}")

                    # Handle NSFW content detection gracefully
                    if "nsfw" in error_detail.lower() or "inappropriate" in error_detail.lower():
                        raise HTTPException(
                            status_code=400,
                            detail="Content not allowed. Please modify your prompt to avoid inappropriate content.",
                        )

                    raise HTTPException(
                        status_code=500, detail=f"Image generation service error: {error_detail}"
                    )

            except httpx.TimeoutException:
                print(f"⏱️ REPLICATE TIMEOUT: Request to {model} timed out after 10s")
                print(f"   Prompt: {prompt[:100]}...")
                raise HTTPException(
                    status_code=500, detail="Image generation service timeout - please try again"
                )
            except httpx.RequestError as e:
                print(f"🌐 REPLICATE CONNECTION ERROR: {str(e)}")
                print(f"   Model: {model}")
                print(f"   Prompt: {prompt[:100]}...")
                raise HTTPException(
                    status_code=500, detail="Unable to connect to image generation service"
                )

            prediction = response.json()
            prediction_id = prediction["id"]
            print(f"✅ REPLICATE PREDICTION STARTED: {prediction_id}")

        # Poll for completion
        max_wait_time = 120  # 2 minutes (Gen-4 Turbo should be faster than regular Gen-4)
        poll_interval = 2  # 2 seconds
        elapsed_time = 0
        poll_start_time = time.time()
        poll_count = 0

        print(f"⏱️ POLLING_TIMING: Starting to poll Gen-4 Turbo prediction {prediction_id}")

        async with httpx.AsyncClient() as client:
            while elapsed_time < max_wait_time:
                await asyncio.sleep(poll_interval)
                elapsed_time += poll_interval
                poll_count += 1

                poll_request_start = time.time()
                poll_response = await client.get(
                    f"https://api.replicate.com/v1/predictions/{prediction_id}", headers=headers
                )
                poll_request_time = time.time() - poll_request_start

                if poll_response.status_code != 200:
                    raise HTTPException(status_code=500, detail="Failed to check prediction status")

                result = poll_response.json()
                status = result["status"]

                print(
                    f"⏱️ POLLING_TIMING: Gen-4 Turbo Poll #{poll_count} after {elapsed_time}s - Status: {status} (poll took {poll_request_time:.3f}s) - Image: {image_id or 'unknown'}"
                )

                if status == "succeeded":
                    total_poll_time = time.time() - poll_start_time
                    print(
                        f"✅ POLLING_TIMING: Gen-4 Turbo prediction completed! Total polling time: {total_poll_time:.2f}s over {poll_count} polls"
                    )

                    image_url = (
                        result["output"][0]
                        if isinstance(result["output"], list)
                        else result["output"]
                    )

                    generation_approach = "gen4_turbo_text_only" if not reference_people else "gen4_turbo_with_references"

                    metadata = {
                        "model_used": model,
                        "api_provider": "replicate",
                        "enhanced_prompt": enhanced_prompt,
                        "prediction_id": prediction_id,
                        "reference_people_count": len(reference_people),
                        "generation_approach": generation_approach,
                        "aspect_ratio": aspect_ratio,
                        "api_request_time": api_request_time,
                        "polling_time": total_poll_time,
                        "poll_count": poll_count,
                    }

                    # Add reference data to metadata if used
                    if reference_images and reference_tags:
                        metadata["reference_images"] = reference_images
                        metadata["reference_tags"] = reference_tags

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
                    if (
                        "nsfw" in error_msg.lower()
                        or "inappropriate" in error_msg.lower()
                        or "flagged as sensitive" in error_msg.lower()
                        or "(e005)" in error_msg.lower()
                        or "sensitive content" in error_msg.lower()
                    ):
                        raise HTTPException(
                            status_code=400,
                            detail="Content not allowed. Please modify your prompt to avoid inappropriate content.",
                        )

                    raise HTTPException(
                        status_code=500, detail=f"Image generation failed: {error_msg}"
                    )

        # Timeout - enhanced logging
        print(f"⏱️ REPLICATE PREDICTION TIMEOUT: {prediction_id}")
        print(f"   Model: {model}")
        print(f"   Max Wait Time: {max_wait_time}s")
        print(f"   Total Elapsed: {elapsed_time}s")
        print(
            f"   Last Status: {result.get('status', 'unknown') if 'result' in locals() else 'unknown'}"
        )

        raise HTTPException(status_code=500, detail="Image generation timed out")


# Global instance
image_generation_service = ImageGenerationService()
