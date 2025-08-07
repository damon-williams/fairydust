# Video API Documentation for Front-End Team

## Overview
The video generation API has been updated to support asynchronous processing. Video generation can take up to 4 minutes, so requests now return immediately with a job ID that you can use to poll for status and retrieve the final result.

## Key Changes
- **Generate** and **Animate** endpoints now return a job response immediately
- Poll the status endpoint to check progress
- Retrieve the final video from the result endpoint when ready
- All other CRUD operations remain synchronous and unchanged

## Endpoints

### 1. Generate Video from Text (Async)
**POST** `/videos/generate`

**Request Body:**
```json
{
  "user_id": "uuid",
  "prompt": "A cat playing piano in a jazz club",
  "duration": "short|medium|long",  // short=5s, medium=10s, long=15s
  "resolution": "sd_480p|hd_720p|hd_1080p|4k_2160p",
  "aspect_ratio": "16:9|9:16|1:1|4:3|3:4",
  "reference_person": {  // Optional - for personalized videos
    "person_id": "uuid",
    "relationship": "string"
  },
  "camera_fixed": true  // Optional - default false
}
```

**Response (202 Accepted):**
```json
{
  "success": true,
  "job_id": "uuid",
  "status": "queued",
  "estimated_completion_seconds": 240,
  "message": "Video generation started. Use the job_id to check status."
}
```

### 2. Animate Image to Video (Async)
**POST** `/videos/animate`

**Request Body:**
```json
{
  "user_id": "uuid",
  "image_url": "https://example.com/image.jpg",
  "prompt": "Make the person in the image dance",
  "duration": "short|medium|long",
  "resolution": "sd_480p|hd_720p|hd_1080p|4k_2160p",
  "camera_fixed": false  // Optional
}
```

**Response (202 Accepted):**
```json
{
  "success": true,
  "job_id": "uuid",
  "status": "queued",
  "estimated_completion_seconds": 180,
  "message": "Video animation started. Use the job_id to check status."
}
```

### 3. Check Job Status
**GET** `/videos/jobs/{job_id}/status`

**Response (200 OK):**
```json
{
  "success": true,
  "job_id": "uuid",
  "status": "queued|starting|processing|completed|failed|cancelled",
  "progress": 0.75,  // 0.0 to 1.0 (optional)
  "generation_info": {  // Optional progress info
    "current_step": "Generating frames",
    "estimated_remaining_seconds": 60
  },
  "created_at": "2024-01-10T12:00:00Z",
  "updated_at": "2024-01-10T12:01:30Z"
}
```

### 4. Get Job Result
**GET** `/videos/jobs/{job_id}/result`

**Response when completed (200 OK):**
```json
{
  "success": true,
  "video": {
    "id": "uuid",
    "user_id": "uuid",
    "url": "https://cdn.example.com/videos/abc123.mp4",
    "thumbnail_url": "https://cdn.example.com/thumbnails/abc123.jpg",
    "prompt": "A cat playing piano in a jazz club",
    "generation_type": "text_to_video|image_to_video",
    "source_image_url": null,  // Only for image_to_video
    "duration_seconds": 5,
    "resolution": "hd_1080p",
    "aspect_ratio": "16:9",
    "reference_person": null,
    "metadata": {},
    "is_favorited": false,
    "created_at": "2024-01-10T12:00:00Z",
    "updated_at": "2024-01-10T12:00:00Z"
  },
  "generation_info": {
    "model_used": "replicate/minimax-video-01",
    "generation_time_ms": 180000
  }
}
```

**Response when failed (200 OK):**
```json
{
  "success": false,
  "job_id": "uuid",
  "status": "failed",
  "error": "Video generation failed: Model timeout"
}
```

**Response when still processing (200 OK):**
```json
{
  "success": true,
  "job_id": "uuid",
  "status": "processing",
  "message": "Video generation still in progress"
}
```

### 5. Cancel Job
**DELETE** `/videos/jobs/{job_id}`

**Response (200 OK):**
```json
{
  "success": true,
  "job_id": "uuid",
  "status": "cancelled",
  "message": "Video generation job cancelled successfully"
}
```

### 6. Get Active Jobs
**GET** `/videos/jobs/active`

**Response (200 OK):**
```json
{
  "success": true,
  "active_jobs": [
    {
      "job_id": "uuid",
      "status": "processing",
      "generation_type": "text_to_video",
      "created_at": "2024-01-10T12:00:00Z",
      "estimated_completion_seconds": 240
    }
  ],
  "count": 1
}
```

### 7. List Videos (Unchanged)
**GET** `/videos?limit=20&offset=0&favorites_only=false&generation_type=all`

**Response (200 OK):**
```json
{
  "videos": [...],  // Array of UserVideo objects
  "pagination": {
    "total": 50,
    "limit": 20,
    "offset": 0,
    "has_more": true
  }
}
```

### 8. Get Video Details (Unchanged)
**GET** `/videos/{video_id}`

**Response (200 OK):**
```json
{
  "video": {
    // Same UserVideo object as in job result
  }
}
```

### 9. Update Video (Unchanged)
**PUT** `/videos/{video_id}`

**Request Body:**
```json
{
  "is_favorited": true
}
```

**Response (200 OK):**
```json
{
  "video": {
    // Updated UserVideo object
  }
}
```

### 10. Delete Video (Unchanged)
**DELETE** `/videos/{video_id}`

**Response (200 OK):**
```json
{
  "deleted_from_storage": true
}
```

### 11. Background Processor Stats
**GET** `/videos/stats`

**Response (200 OK):**
```json
{
  "is_running": true,
  "jobs_processed": 156,
  "jobs_queued": 3,
  "jobs_in_progress": 1,
  "last_job_completed_at": "2024-01-10T12:00:00Z",
  "average_processing_time_seconds": 185.4
}
```

## Recommended Front-End Flow

### For Video Generation:
1. **Submit Request**: POST to `/videos/generate` or `/videos/animate`
2. **Store Job ID**: Save the returned `job_id` 
3. **Show Progress**: Display "Video generating..." with estimated time
4. **Poll Status**: Every 5-10 seconds, GET `/videos/jobs/{job_id}/status`
5. **Handle Completion**: 
   - When status is `completed`, GET `/videos/jobs/{job_id}/result`
   - When status is `failed`, show error message
   - When status is `cancelled`, show cancellation message
6. **Display Video**: Show the video player with the returned URL

### Error Handling:
- **403**: User trying to access someone else's job
- **404**: Job not found or already expired
- **500**: Server error - retry after delay

### Important Notes:
1. **Job Expiration**: Jobs are kept for 24 hours after completion
2. **Polling Frequency**: Recommend polling every 5-10 seconds
3. **DUST Costs**: 
   - Text-to-video: 10 DUST per video
   - Image-to-video: 8 DUST per video
   - DUST is deducted when job starts, refunded if generation fails
4. **Concurrent Jobs**: Users can have multiple jobs running simultaneously
5. **Video Storage**: Videos are stored permanently in CloudFlare R2 with CDN distribution

## Migration Guide
If you're currently using the synchronous endpoints:
1. Update your generate/animate calls to handle the job response
2. Implement a polling mechanism for job status
3. Add UI for showing generation progress
4. Handle the async result retrieval
5. All other endpoints (list, get, update, delete) work exactly the same