"""Image storage service for Cloudflare R2 integration"""

import os
import uuid
from typing import Optional, Tuple
from urllib.parse import urlparse

import aiohttp
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi import HTTPException


class ImageStorageService:
    """Service for storing generated images in Cloudflare R2"""
    
    def __init__(self):
        self.account_id = os.getenv("R2_ACCOUNT_ID")
        self.access_key = os.getenv("R2_ACCESS_KEY_ID")
        self.secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
        self.bucket_name = os.getenv("R2_BUCKET_NAME", "fairydust-images")
        self.endpoint = os.getenv("R2_ENDPOINT")
        
        if not all([self.account_id, self.access_key, self.secret_key]):
            raise ValueError("Missing R2 configuration. Check environment variables.")
        
        # Initialize R2 client
        self.client = boto3.client(
            's3',
            endpoint_url=self.endpoint,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            config=Config(signature_version='s3v4'),
            region_name='auto'  # R2 uses 'auto' for region
        )
    
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
        try:
            # Download the image
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status != 200:
                        raise HTTPException(
                            status_code=500,
                            detail=f"Failed to download generated image: HTTP {response.status}"
                        )
                    
                    image_data = await response.read()
                    content_type = response.headers.get('content-type', 'image/jpeg')
            
            # Determine file extension
            file_extension = self._get_extension_from_content_type(content_type)
            
            # Generate storage key
            storage_key = f"generated/{user_id}/{image_id}.{file_extension}"
            
            # Upload to R2
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=storage_key,
                Body=image_data,
                ContentType=content_type,
                CacheControl="public, max-age=31536000",  # Cache for 1 year
                Metadata={
                    'user-id': user_id,
                    'image-id': image_id,
                    'source': 'ai-generated'
                }
            )
            
            # Generate public URL
            stored_url = f"https://pub-{self.account_id[:8]}.r2.dev/{self.bucket_name}/{storage_key}"
            
            # Get image dimensions
            dimensions = await self._get_image_dimensions(image_data)
            
            return stored_url, len(image_data), dimensions
            
        except ClientError as e:
            raise HTTPException(status_code=500, detail=f"Storage failed: {str(e)}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Image processing failed: {str(e)}")
    
    async def delete_generated_image(self, image_url: str) -> bool:
        """
        Delete a generated image from R2
        
        Args:
            image_url: The URL of the image to delete
            
        Returns:
            bool: True if deleted successfully
        """
        try:
            # Extract key from URL
            key = self._extract_key_from_url(image_url)
            if not key:
                return False
            
            self.client.delete_object(Bucket=self.bucket_name, Key=key)
            return True
            
        except ClientError:
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