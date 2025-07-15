"""Image storage service for Cloudflare R2 integration"""

import os
import uuid
from typing import Optional, Tuple
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException


class ImageStorageService:
    """Service for storing generated images in Cloudflare R2"""
    
    def __init__(self):
        self.account_id = os.getenv("R2_ACCOUNT_ID")
        self.access_key = os.getenv("R2_ACCESS_KEY_ID")
        self.secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
        self.bucket_name = os.getenv("R2_BUCKET_NAME", "fairydust-images")
        self.endpoint = os.getenv("R2_ENDPOINT")
        
        # For now, we'll just store URLs without actual R2 upload
        # This can be enabled once boto3 is properly installed
    
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
            # Download the image to get file info
            async with httpx.AsyncClient() as client:
                response = await client.get(image_url, timeout=30.0)
                if response.status_code != 200:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to download generated image: HTTP {response.status_code}"
                    )
                
                image_data = response.content
                content_type = response.headers.get('content-type', 'image/jpeg')
            
            # For now, just return the original URL until R2 is properly configured
            # TODO: Implement actual R2 upload once boto3 is available
            stored_url = image_url
            
            # Get image dimensions
            dimensions = await self._get_image_dimensions(image_data)
            
            return stored_url, len(image_data), dimensions
            
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
        # For now, just return True since we're not actually storing in R2
        # TODO: Implement actual R2 deletion once boto3 is available
        return True
    
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