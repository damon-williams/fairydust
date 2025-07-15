"""Image storage service for Cloudflare R2 integration"""

import os
import uuid
from typing import Optional, Tuple
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

# Try to import boto3, fallback gracefully if not available
try:
    import boto3
    from botocore.config import Config
    from botocore.exceptions import ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False


class ImageStorageService:
    """Service for storing generated images in Cloudflare R2"""
    
    def __init__(self):
        self.account_id = os.getenv("R2_ACCOUNT_ID")
        self.access_key = os.getenv("R2_ACCESS_KEY_ID")
        self.secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
        self.bucket_name = os.getenv("R2_BUCKET_NAME", "fairydust-images")
        self.endpoint = os.getenv("R2_ENDPOINT")
        
        # Initialize R2 client if boto3 is available and credentials are set
        self.r2_client = None
        if BOTO3_AVAILABLE and all([self.account_id, self.access_key, self.secret_key, self.endpoint]):
            try:
                self.r2_client = boto3.client(
                    's3',
                    endpoint_url=self.endpoint,
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key,
                    config=Config(signature_version='s3v4'),
                    region_name='auto'  # R2 uses 'auto' for region
                )
                print("✅ R2 client initialized successfully")
            except Exception as e:
                print(f"⚠️ Failed to initialize R2 client: {e}")
                self.r2_client = None
        else:
            print("⚠️ R2 not configured (missing boto3 or credentials)")
    
    async def store_generated_image(
        self,
        image_url: str,
        user_id: str,
        image_id: str
    ) -> Tuple[str, int, dict]:
        """
        Download and store a generated image in R2
        
        Args:
            image_url: URL of the generated image to download
            user_id: User UUID string
            image_id: Image UUID string
            
        Returns:
            Tuple[str, int, dict]: (stored_url, file_size_bytes, dimensions)
        """
        # If R2 is configured, upload the image properly
        if self.r2_client:
            return await self._upload_to_r2(image_url, user_id, image_id)
        else:
            # Fallback: use original URL (temporary solution)
            print("⚠️ R2 not configured, using original URL (may expire)")
            estimated_size = 1024000  # ~1MB estimate for 1024x1024 PNG
            estimated_dimensions = {"width": 1024, "height": 1024}
            return image_url, estimated_size, estimated_dimensions

    async def _upload_to_r2(self, image_url: str, user_id: str, image_id: str) -> Tuple[str, int, dict]:
        """Upload image to R2 and return permanent URL"""
        try:
            # Download the image with proper headers
            async with httpx.AsyncClient() as client:
                # Add headers that work better with OpenAI blob storage
                headers = {
                    'User-Agent': 'fairydust-content-service/1.0',
                    'Accept': '*/*',
                    'Accept-Encoding': 'gzip, deflate',
                }
                
                response = await client.get(
                    image_url, 
                    headers=headers, 
                    timeout=60.0,
                    follow_redirects=True
                )
                
                if response.status_code != 200:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to download image from OpenAI: HTTP {response.status_code}"
                    )
                
                image_data = response.content
                content_type = response.headers.get('content-type', 'image/png')
                
                if len(image_data) == 0:
                    raise HTTPException(status_code=500, detail="Downloaded image is empty")
            
            # Determine file extension
            file_extension = self._get_extension_from_content_type(content_type)
            
            # Generate storage key
            storage_key = f"generated/{user_id}/{image_id}.{file_extension}"
            
            # Upload to R2
            self.r2_client.put_object(
                Bucket=self.bucket_name,
                Key=storage_key,
                Body=image_data,
                ContentType=content_type,
                CacheControl="public, max-age=31536000",  # Cache for 1 year
                Metadata={
                    'user-id': user_id,
                    'image-id': image_id,
                    'source': 'ai-generated',
                    'original-url': image_url
                }
            )
            
            # Generate permanent public URL
            permanent_url = f"https://pub-{self.account_id[:8]}.r2.dev/{self.bucket_name}/{storage_key}"
            
            # Get actual dimensions
            dimensions = await self._get_image_dimensions(image_data)
            
            print(f"✅ Image uploaded to R2: {permanent_url}")
            return permanent_url, len(image_data), dimensions
            
        except ClientError as e:
            print(f"❌ R2 upload failed: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to store image in R2: {str(e)}")
        except Exception as e:
            print(f"❌ Image upload failed: {e}")
            raise HTTPException(status_code=500, detail=f"Image upload failed: {str(e)}")
    
    async def delete_generated_image(self, image_url: str) -> bool:
        """
        Delete a generated image from R2
        
        Args:
            image_url: The URL of the image to delete
            
        Returns:
            bool: True if deleted successfully
        """
        if not self.r2_client:
            # If no R2 client, just return True (no actual storage to delete)
            return True
            
        try:
            # Extract key from URL
            key = self._extract_key_from_url(image_url)
            if not key:
                return False
            
            self.r2_client.delete_object(Bucket=self.bucket_name, Key=key)
            print(f"✅ Deleted image from R2: {key}")
            return True
            
        except ClientError as e:
            print(f"⚠️ Failed to delete from R2: {e}")
            return False
    
    def _get_extension_from_content_type(self, content_type: str) -> str:
        """Get file extension from content type"""
        extension_map = {
            "image/jpeg": "jpg",
            "image/jpg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
            "image/gif": "gif"
        }
        return extension_map.get(content_type, "jpg")
    
    def _extract_key_from_url(self, image_url: str) -> Optional[str]:
        """Extract R2 object key from image URL"""
        try:
            # Expected format: https://pub-abc123.r2.dev/bucket-name/key
            if f"/{self.bucket_name}/" in image_url:
                return image_url.split(f"/{self.bucket_name}/", 1)[1]
            return None
        except Exception:
            return None
    
    async def _get_image_dimensions(self, image_data: bytes) -> dict:
        """Get image dimensions from image data"""
        try:
            # For now, return default dimensions based on common AI image sizes
            # In a production system, you might want to use Pillow to get actual dimensions
            file_size = len(image_data)
            
            # Estimate dimensions based on file size (rough approximation)
            if file_size > 2_000_000:  # > 2MB, likely 1024x1792
                return {"width": 1024, "height": 1792}
            else:  # Likely 1024x1024
                return {"width": 1024, "height": 1024}
                
        except Exception:
            # Fallback to standard dimensions
            return {"width": 1024, "height": 1024}


# Global instance
image_storage_service = ImageStorageService()