"""Image storage service for Cloudflare R2 integration"""

import os
from typing import Optional

import httpx

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
        if BOTO3_AVAILABLE and all(
            [self.account_id, self.access_key, self.secret_key, self.endpoint]
        ):
            try:
                self.r2_client = boto3.client(
                    "s3",
                    endpoint_url=self.endpoint,
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key,
                    config=Config(signature_version="s3v4"),
                    region_name="auto",  # R2 uses 'auto' for region
                )
                print("✅ R2 client initialized successfully")
            except Exception as e:
                print(f"⚠️ Failed to initialize R2 client: {e}")
                self.r2_client = None
        else:
            print("⚠️ R2 not configured (missing boto3 or credentials)")

    async def store_generated_image(
        self, image_url: str, user_id: str, image_id: str
    ) -> tuple[str, int, dict]:
        """
        Download and store a generated image in R2

        Args:
            image_url: URL of the generated image to download
            user_id: User UUID string
            image_id: Image UUID string

        Returns:
            Tuple[str, int, dict]: (stored_url, file_size_bytes, dimensions)
        """
        import time

        start_time = time.time()

        print(f"⏱️ STORAGE_TIMING: Starting image storage for {image_id}")

        # If R2 is configured, upload the image properly
        if self.r2_client:
            result = await self._upload_to_r2(image_url, user_id, image_id)
            total_time = time.time() - start_time
            print(f"⏱️ STORAGE_TIMING: Image {image_id} stored in {total_time:.2f}s")
            return result
        else:
            # Fallback: use original URL (temporary solution)
            print("⚠️ R2 not configured, using original URL (may expire)")
            estimated_size = 1024000  # ~1MB estimate for 1024x1024 PNG
            estimated_dimensions = {"width": 1024, "height": 1024}
            total_time = time.time() - start_time
            print(f"⏱️ STORAGE_TIMING: Using original URL (no storage) - {total_time:.3f}s")
            return image_url, estimated_size, estimated_dimensions

    async def _upload_to_r2(
        self, image_url: str, user_id: str, image_id: str
    ) -> tuple[str, int, dict]:
        """Upload image to R2 and return permanent URL"""
        import time

        download_start_time = time.time()
        max_retries = 3

        for attempt in range(max_retries):
            try:
                print(f"🔄 Attempting to download image (attempt {attempt + 1}/{max_retries})")

                # Download the image with minimal headers to avoid authentication issues
                async with httpx.AsyncClient() as client:
                    # Use minimal headers - sometimes less is more with OpenAI blob storage
                    headers = {}

                    # Try different approaches on retries
                    if attempt == 1:
                        headers = {"User-Agent": "Mozilla/5.0 (compatible; fairydust/1.0)"}
                    elif attempt == 2:
                        headers = {"User-Agent": "curl/7.68.0", "Accept": "image/png,image/*,*/*"}

                    download_request_start = time.time()
                    response = await client.get(
                        image_url, headers=headers, timeout=30.0, follow_redirects=True
                    )
                    download_request_time = time.time() - download_request_start

                    print(
                        f"📡 Download response: {response.status_code} (took {download_request_time:.2f}s)"
                    )

                    if response.status_code == 200:
                        image_data = response.content
                        content_type = response.headers.get("content-type", "image/png")

                        if len(image_data) > 0:
                            # Success! Upload to R2
                            download_total_time = time.time() - download_start_time
                            print(
                                f"⏱️ STORAGE_TIMING: Image downloaded in {download_total_time:.2f}s ({len(image_data):,} bytes)"
                            )
                            break
                        else:
                            print("⚠️ Downloaded image is empty, retrying...")
                            continue
                    else:
                        print(f"⚠️ Download failed with status {response.status_code}, retrying...")
                        if attempt == max_retries - 1:
                            # Last attempt failed, fall back to original URL
                            print("❌ All download attempts failed, falling back to original URL")
                            return image_url, 1024000, {"width": 1024, "height": 1024}
                        continue

            except Exception as e:
                print(f"⚠️ Download attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    # Last attempt failed, fall back to original URL
                    print("❌ All download attempts failed, falling back to original URL")
                    return image_url, 1024000, {"width": 1024, "height": 1024}
                continue

        try:
            # Determine file extension
            file_extension = self._get_extension_from_content_type(content_type)

            # Generate storage key
            storage_key = f"generated/{user_id}/{image_id}.{file_extension}"

            # Upload to R2
            upload_start_time = time.time()
            self.r2_client.put_object(
                Bucket=self.bucket_name,
                Key=storage_key,
                Body=image_data,
                ContentType=content_type,
                CacheControl="public, max-age=31536000",  # Cache for 1 year
                Metadata={
                    "user-id": user_id,
                    "image-id": image_id,
                    "source": "ai-generated",
                    "original-url": image_url,
                },
            )
            upload_time = time.time() - upload_start_time
            print(f"⏱️ STORAGE_TIMING: Upload to R2 took {upload_time:.2f}s")

            # Use custom domain for R2 public access
            permanent_url = f"https://images.fairydust.fun/{storage_key}"
            print(f"🔗 Generated public URL (custom domain): {permanent_url}")

            # Get actual dimensions
            dimensions_start_time = time.time()
            dimensions = await self._get_image_dimensions(image_data)
            dimensions_time = time.time() - dimensions_start_time

            total_storage_time = time.time() - download_start_time
            print(f"✅ Image uploaded to R2: {permanent_url}")
            print("⏱️ STORAGE_TIMING_BREAKDOWN:")
            print(f"   Download: {download_total_time:.2f}s")
            print(f"   Upload: {upload_time:.2f}s")
            print(f"   Dimensions: {dimensions_time:.3f}s")
            print(f"   Total storage: {total_storage_time:.2f}s")

            return permanent_url, len(image_data), dimensions

        except ClientError as e:
            print(f"❌ R2 upload failed: {e}")
            # Fall back to original URL if R2 upload fails
            return image_url, 1024000, {"width": 1024, "height": 1024}
        except Exception as e:
            print(f"❌ Image processing failed: {e}")
            # Fall back to original URL if anything fails
            return image_url, 1024000, {"width": 1024, "height": 1024}

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
            "image/gif": "gif",
        }
        return extension_map.get(content_type, "jpg")

    def _extract_key_from_url(self, image_url: str) -> Optional[str]:
        """Extract R2 object key from image URL"""
        try:
            # Expected format: https://images.fairydust.fun/generated/user-id/image-id.ext
            if "images.fairydust.fun/" in image_url:
                return image_url.split("images.fairydust.fun/", 1)[1]
            # Fallback for old format: https://pub-abc123.r2.dev/bucket-name/key
            elif f"/{self.bucket_name}/" in image_url:
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
