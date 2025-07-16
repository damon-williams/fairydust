"""Cloud storage service for handling file uploads to Cloudflare R2"""

import os
import uuid
from typing import Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi import HTTPException, UploadFile


class StorageService:
    """Service for uploading and managing files in Cloudflare R2"""
    
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
    
    async def upload_person_photo(
        self, 
        file: UploadFile, 
        user_id: str, 
        person_id: str
    ) -> tuple[str, int]:
        """
        Upload a photo for a person in someone's life
        
        Returns:
            tuple: (photo_url, file_size_bytes)
        """
        # Validate file type
        allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/webp"]
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid file type. Allowed: {', '.join(allowed_types)}"
            )
        
        # Validate file size (5MB limit)
        content = await file.read()
        file_size = len(content)
        if file_size > 5 * 1024 * 1024:  # 5MB
            raise HTTPException(status_code=400, detail="File too large. Maximum 5MB allowed.")
        
        if file_size == 0:
            raise HTTPException(status_code=400, detail="Empty file not allowed.")
        
        # Generate unique filename
        file_extension = self._get_file_extension(file.filename, file.content_type)
        unique_filename = f"people/{user_id}/{person_id}/{uuid.uuid4()}.{file_extension}"
        
        try:
            # Upload to R2
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=unique_filename,
                Body=content,
                ContentType=file.content_type,
                CacheControl="public, max-age=31536000",  # Cache for 1 year
                Metadata={
                    'user-id': user_id,
                    'person-id': person_id,
                    'original-filename': file.filename or 'unknown'
                }
            )
            
            # Generate public URL using custom domain
            photo_url = f"https://images.fairydust.fun/{unique_filename}"
            
            return photo_url, file_size
            
        except ClientError as e:
            raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    
    async def delete_person_photo(self, photo_url: str) -> bool:
        """
        Delete a person's photo from R2
        
        Args:
            photo_url: The URL of the photo to delete
            
        Returns:
            bool: True if deleted successfully
        """
        try:
            # Extract key from URL
            key = self._extract_key_from_url(photo_url)
            if not key:
                return False
            
            self.client.delete_object(Bucket=self.bucket_name, Key=key)
            return True
            
        except ClientError:
            return False
    
    async def upload_user_avatar(self, file: UploadFile, user_id: str) -> tuple[str, int]:
        """
        Upload an avatar for a user
        
        Args:
            file: UploadFile object containing the avatar image
            user_id: User UUID string
            
        Returns:
            tuple: (avatar_url, file_size_bytes)
        """
        # Validate file type
        allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/webp"]
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid file type. Allowed: {', '.join(allowed_types)}"
            )
        
        # Validate file size (5MB limit)
        content = await file.read()
        file_size = len(content)
        if file_size > 5 * 1024 * 1024:  # 5MB
            raise HTTPException(status_code=400, detail="File too large. Maximum 5MB allowed.")
        
        if file_size == 0:
            raise HTTPException(status_code=400, detail="Empty file not allowed.")
        
        # Generate unique filename
        file_extension = self._get_file_extension(file.filename, file.content_type)
        unique_filename = f"avatars/{user_id}/{uuid.uuid4()}.{file_extension}"
        
        try:
            # Upload to R2
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=unique_filename,
                Body=content,
                ContentType=file.content_type,
                CacheControl="public, max-age=31536000",  # Cache for 1 year
                Metadata={
                    'user-id': user_id,
                    'type': 'avatar',
                    'original-filename': file.filename or 'unknown'
                }
            )
            
            # Generate public URL using custom domain
            avatar_url = f"https://images.fairydust.fun/{unique_filename}"
            
            return avatar_url, file_size
            
        except ClientError as e:
            raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    
    async def delete_user_avatar(self, avatar_url: str) -> bool:
        """
        Delete a user's avatar from R2
        
        Args:
            avatar_url: The URL of the avatar to delete
            
        Returns:
            bool: True if deleted successfully
        """
        try:
            # Extract key from URL
            key = self._extract_key_from_url(avatar_url)
            if not key:
                return False
            
            self.client.delete_object(Bucket=self.bucket_name, Key=key)
            return True
            
        except ClientError:
            return False
    
    def _get_file_extension(self, filename: Optional[str], content_type: str) -> str:
        """Get file extension from filename or content type"""
        if filename and '.' in filename:
            return filename.split('.')[-1].lower()
        
        # Fallback to content type
        extension_map = {
            "image/jpeg": "jpg",
            "image/jpg": "jpg", 
            "image/png": "png",
            "image/webp": "webp"
        }
        return extension_map.get(content_type, "jpg")
    
    def _extract_key_from_url(self, photo_url: str) -> Optional[str]:
        """Extract R2 object key from photo URL"""
        try:
            # Custom domain format: https://images.fairydust.fun/key
            if "images.fairydust.fun/" in photo_url:
                return photo_url.split("images.fairydust.fun/", 1)[1]
            # Legacy format: https://pub-abc123.r2.dev/bucket-name/key
            elif f"/{self.bucket_name}/" in photo_url:
                return photo_url.split(f"/{self.bucket_name}/", 1)[1]
            return None
        except Exception:
            return None


# Global instance
storage_service = StorageService()


async def upload_person_photo(file: UploadFile, user_id: str, person_id: str) -> tuple[str, int]:
    """Convenience function for uploading person photos"""
    return await storage_service.upload_person_photo(file, user_id, person_id)


async def delete_person_photo(photo_url: str) -> bool:
    """Convenience function for deleting person photos"""
    return await storage_service.delete_person_photo(photo_url)


async def upload_user_avatar(file: UploadFile, user_id: str) -> tuple[str, int]:
    """Convenience function for uploading user avatars"""
    return await storage_service.upload_user_avatar(file, user_id)


async def delete_user_avatar(avatar_url: str) -> bool:
    """Convenience function for deleting user avatars"""
    return await storage_service.delete_user_avatar(avatar_url)