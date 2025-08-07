# Video API Update - Frontend Team Summary

## 🚨 Important Changes

The video generation API has been updated to support **asynchronous processing**. Video generation can take up to 4 minutes, so we've implemented a job-based system.

### What Changed:
1. **`POST /videos/generate`** and **`POST /videos/animate`** now return immediately with a job ID
2. You need to poll for status and retrieve the final video when ready
3. All other endpoints (`GET`, `PUT`, `DELETE`) remain unchanged

### Quick Migration Guide:

**Old Flow:**
```javascript
// Wait 4 minutes for response 😱
const response = await fetch('/videos/generate', { 
  method: 'POST',
  body: JSON.stringify(videoRequest)
});
const { video } = await response.json();
```

**New Flow:**
```javascript
// 1. Start generation (returns immediately)
const response = await fetch('/videos/generate', {
  method: 'POST', 
  body: JSON.stringify(videoRequest)
});
const { job_id } = await response.json();

// 2. Poll for status
const checkStatus = async () => {
  const status = await fetch(`/videos/jobs/${job_id}/status`);
  const data = await status.json();
  
  if (data.status === 'completed') {
    // 3. Get the final video
    const result = await fetch(`/videos/jobs/${job_id}/result`);
    const { video } = await result.json();
    // Show video to user
  } else if (data.status === 'failed') {
    // Handle error
  } else {
    // Still processing, check again in 5 seconds
    setTimeout(checkStatus, 5000);
  }
};

checkStatus();
```

### Key Points:
- **Status Codes**: Generate/Animate now return `202 Accepted` (not 200)
- **Polling Interval**: Recommend 5-10 seconds
- **DUST Costs**: Deducted when job starts, refunded if fails
- **Job Expiration**: Results available for 24 hours
- **Cancellation**: Users can cancel queued jobs

### New Endpoints:
- `GET /videos/jobs/{job_id}/status` - Check progress
- `GET /videos/jobs/{job_id}/result` - Get completed video
- `DELETE /videos/jobs/{job_id}` - Cancel job
- `GET /videos/jobs/active` - List user's active jobs
- `GET /videos/stats` - System statistics

### Swagger Docs:
All endpoints now have detailed Swagger documentation with:
- Request/response examples
- Status descriptions
- Error scenarios
- DUST costs and timing estimates

### Full Documentation:
See `VIDEO_API_DOCUMENTATION.md` for complete API reference with all request/response examples.

## Questions?
The backend team is available to help with any integration issues!