# Photo Management API Documentation

## Overview
Complete API documentation for photo management in the fairydust application. This covers both user avatar upload and "People in My Life" photo management.

All photo storage uses **Cloudflare R2** with custom domain `images.fairydust.fun` for optimal performance and caching.

## Base URL
```
https://fairydust-identity-staging.up.railway.app  # Staging
https://fairydust-identity-production.up.railway.app  # Production
```

## Authentication
All endpoints require JWT authentication via the `Authorization` header:
```
Authorization: Bearer <jwt_token>
```

## File Upload Constraints
- **Supported formats**: JPEG, PNG, WebP
- **Maximum file size**: 5MB (application limit) / 6MB (server limit)
- **Content-Type**: Must be valid image MIME type
- **Empty files**: Not allowed
- **Recommended client behavior**: Resize images to under 5MB before upload

## User Avatar Endpoints

### Upload User Avatar
**POST** `/users/me/avatar`

Upload or replace the current user's avatar.

**Request:**
```http
POST /users/me/avatar
Content-Type: multipart/form-data
Authorization: Bearer <jwt_token>

file=<image_file>
```

**Response (200 OK):**
```json
{
  "message": "Avatar uploaded successfully",
  "avatar_url": "https://images.fairydust.fun/avatars/123e4567-e89b-12d3-a456-426614174000/abc123.jpg",
  "file_size": 1024000
}
```

**Error Responses:**
- `400 Bad Request`: Invalid file type, size, or format
- `404 Not Found`: User not found
- `500 Internal Server Error`: Upload failed

### Get Avatar Info
**GET** `/users/me/avatar`

Get information about the current user's avatar.

**Response (200 OK):**
```json
{
  "avatar_url": "https://images.fairydust.fun/avatars/123e4567-e89b-12d3-a456-426614174000/abc123.jpg",
  "avatar_uploaded_at": "2023-10-15T10:30:00Z",
  "avatar_size_bytes": 1024000
}
```

**Error Responses:**
- `404 Not Found`: User not found or no avatar exists

### Delete Avatar
**DELETE** `/users/me/avatar`

Delete the current user's avatar.

**Response (200 OK):**
```json
{
  "message": "Avatar deleted successfully",
  "deleted_from_storage": true
}
```

**Error Responses:**
- `404 Not Found`: User not found or no avatar to delete

## People Photo Endpoints

### Upload Person Photo
**POST** `/users/{user_id}/people/{person_id}/photo`

Upload a photo for a specific person in the user's life.

**Request:**
```http
POST /users/123e4567-e89b-12d3-a456-426614174000/people/456e7890-e89b-12d3-a456-426614174000/photo
Content-Type: multipart/form-data
Authorization: Bearer <jwt_token>

file=<image_file>
```

**Response (200 OK):**
```json
{
  "message": "Photo uploaded successfully",
  "photo_url": "https://images.fairydust.fun/people/123e4567-e89b-12d3-a456-426614174000/456e7890-e89b-12d3-a456-426614174000/def456.jpg",
  "file_size": 2048000
}
```

**Error Responses:**
- `400 Bad Request`: Invalid file type, size, or format
- `403 Forbidden`: User doesn't own this person record
- `404 Not Found`: Person not found
- `500 Internal Server Error`: Upload failed

### Get Person Photo Info
**GET** `/users/{user_id}/people/{person_id}/photo`

Get information about a person's photo.

**Response (200 OK):**
```json
{
  "photo_url": "https://images.fairydust.fun/people/123e4567-e89b-12d3-a456-426614174000/456e7890-e89b-12d3-a456-426614174000/def456.jpg",
  "photo_uploaded_at": "2023-10-15T10:30:00Z",
  "photo_size_bytes": 2048000
}
```

**Error Responses:**
- `403 Forbidden`: User doesn't own this person record
- `404 Not Found`: Person not found or no photo exists

### Update Person Photo
**PATCH** `/users/{user_id}/people/{person_id}/photo`

Replace an existing person's photo.

**Request:**
```http
PATCH /users/123e4567-e89b-12d3-a456-426614174000/people/456e7890-e89b-12d3-a456-426614174000/photo
Content-Type: multipart/form-data
Authorization: Bearer <jwt_token>

file=<image_file>
```

**Response (200 OK):**
```json
{
  "message": "Photo updated successfully",
  "photo_url": "https://images.fairydust.fun/people/123e4567-e89b-12d3-a456-426614174000/456e7890-e89b-12d3-a456-426614174000/ghi789.jpg",
  "file_size": 1536000
}
```

**Error Responses:**
- `400 Bad Request`: Invalid file type, size, or format
- `403 Forbidden`: User doesn't own this person record
- `404 Not Found`: Person not found
- `500 Internal Server Error`: Update failed

### Delete Person Photo
**DELETE** `/users/{user_id}/people/{person_id}/photo`

Delete a person's photo.

**Response (200 OK):**
```json
{
  "message": "Photo deleted successfully",
  "deleted_from_storage": true
}
```

**Error Responses:**
- `403 Forbidden`: User doesn't own this person record
- `404 Not Found`: Person not found or no photo to delete

## User Profile Integration

### Get Current User Profile
**GET** `/users/me`

The user profile endpoint now includes avatar information:

**Response (200 OK):**
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "fairyname": "john_doe",
  "email": "john@example.com",
  "phone": "+1234567890",
  "is_admin": false,
  "first_name": "John",
  "birth_date": "1990-01-01",
  "is_onboarding_completed": true,
  "last_login_date": "2023-10-15T10:30:00Z",
  "auth_provider": "google",
  "avatar_url": "https://images.fairydust.fun/avatars/123e4567-e89b-12d3-a456-426614174000/abc123.jpg",
  "avatar_uploaded_at": "2023-10-15T10:30:00Z",
  "avatar_size_bytes": 1024000,
  "created_at": "2023-01-01T00:00:00Z",
  "updated_at": "2023-10-15T10:30:00Z",
  "dust_balance": 1000
}
```

## Frontend Implementation Guide

### Client-Side Image Resizing (Recommended)

Before uploading, resize images to ensure they're under 5MB:

```javascript
const resizeImage = (file, maxWidth = 1024, maxHeight = 1024, quality = 0.8) => {
  return new Promise((resolve) => {
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    const img = new Image();
    
    img.onload = () => {
      // Calculate new dimensions
      let { width, height } = img;
      
      if (width > height) {
        if (width > maxWidth) {
          height = (height * maxWidth) / width;
          width = maxWidth;
        }
      } else {
        if (height > maxHeight) {
          width = (width * maxHeight) / height;
          height = maxHeight;
        }
      }
      
      canvas.width = width;
      canvas.height = height;
      
      // Draw and compress
      ctx.drawImage(img, 0, 0, width, height);
      canvas.toBlob(resolve, 'image/jpeg', quality);
    };
    
    img.src = URL.createObjectURL(file);
  });
};
```

### Avatar Upload Example
```javascript
const uploadAvatar = async (file) => {
  // Resize image if needed
  const resizedFile = await resizeImage(file);
  
  const formData = new FormData();
  formData.append('file', resizedFile);
  
  const response = await fetch('/users/me/avatar', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${authToken}`
    },
    body: formData
  });
  
  if (!response.ok) {
    throw new Error('Upload failed');
  }
  
  return await response.json();
};
```

### Display Avatar with Fallback
```javascript
const AvatarComponent = ({ user }) => {
  const [avatarError, setAvatarError] = useState(false);
  
  return (
    <img 
      src={avatarError ? '/default-avatar.png' : user.avatar_url}
      alt="User avatar"
      onError={() => setAvatarError(true)}
      className="avatar"
    />
  );
};
```

### Person Photo Upload Example
```javascript
const uploadPersonPhoto = async (userId, personId, file) => {
  const formData = new FormData();
  formData.append('file', file);
  
  const response = await fetch(`/users/${userId}/people/${personId}/photo`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${authToken}`
    },
    body: formData
  });
  
  if (!response.ok) {
    throw new Error('Upload failed');
  }
  
  return await response.json();
};
```

## Error Handling

### Common Error Codes
- `400 Bad Request`: Invalid file, size, or format
- `401 Unauthorized`: Invalid or missing JWT token
- `403 Forbidden`: User doesn't have permission
- `404 Not Found`: Resource not found
- `413 Payload Too Large`: File exceeds 5MB limit
- `500 Internal Server Error`: Server-side error

### Error Response Format
```json
{
  "detail": "Invalid file type. Allowed: image/jpeg, image/png, image/webp"
}
```

## ⚠️ **Important: Reference Image Limitations**

### **FLUX Model Limitations**
The current image generation service uses **FLUX-1.1-Pro**, which has the following limitations regarding reference images:

❌ **Does NOT support direct image references** (unlike DALL-E)  
❌ **Cannot generate accurate likenesses** from uploaded photos  
❌ **Only uses text descriptions** for people references  

### **Current Implementation**
When you provide reference people, the system:
1. ✅ **Validates** that people belong to the user
2. ✅ **Extracts descriptions** from the people references
3. ✅ **Adds text descriptions** to the prompt (e.g., "featuring person (Damon), person (Leslie)")
4. ❌ **Does NOT use the actual photos** for visual reference

### **Example:**
```javascript
// Request with reference people
{
  "prompt": "walking together in a park",
  "reference_people": [
    {
      "person_id": "user-id",
      "description": "Damon (Me)",
      "photo_url": "https://images.fairydust.fun/avatars/..."
    },
    {
      "person_id": "person-id", 
      "description": "Leslie (Wife)",
      "photo_url": "https://images.fairydust.fun/people/..."
    }
  ]
}

// Actual prompt sent to FLUX
"walking together in a park, featuring person (Damon), person (Leslie), photorealistic..."
```

### **Recommendations for Frontend**
1. **Set expectations** - Inform users that generated people won't look like the reference photos
2. **Focus on descriptions** - Encourage detailed descriptions rather than relying on photos
3. **Consider alternative models** - Future integration with models that support image references
4. **Use for composition** - Good for generating scenes with multiple people, but not accurate likenesses

### **Future Improvements**
- Integration with models that support image references (e.g., Midjourney, Stable Diffusion with ControlNet)
- Face detection and description generation from uploaded photos
- Hybrid approach combining FLUX with face-swapping post-processing

## Storage & Performance

### CDN Integration
- All images are served via `images.fairydust.fun` custom domain
- Images are cached for 1 year (`max-age=31536000`)
- Optimized for fast loading and global distribution

### File Organization
```
avatars/
  └── {user_id}/
      └── {uuid}.{ext}

people/
  └── {user_id}/
      └── {person_id}/
          └── {uuid}.{ext}
```

### Best Practices
1. **Always validate file types** before upload
2. **Show loading states** during uploads
3. **Handle errors gracefully** with user-friendly messages
4. **Use progressive loading** for image displays
5. **Implement retry logic** for failed uploads
6. **Cache image URLs** to reduce API calls

## Testing

### Test Upload Workflow
1. Select valid image file (JPEG, PNG, WebP)
2. Verify file size is under 5MB
3. Upload via appropriate endpoint
4. Verify response contains valid image URL
5. Test image accessibility via returned URL
6. Verify database reflects new image metadata

### Test Error Scenarios
1. Upload invalid file type
2. Upload file exceeding size limit
3. Upload without authentication
4. Upload to non-existent person
5. Delete non-existent photo
6. Access photo without permission