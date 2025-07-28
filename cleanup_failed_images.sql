-- Cleanup script for old failed story images
-- This removes failed images older than 7 days to prevent Railway health monitoring issues

-- First, let's see what we're dealing with
SELECT 
    status,
    COUNT(*) as count,
    MIN(created_at) as oldest,
    MAX(created_at) as newest
FROM story_images 
GROUP BY status
ORDER BY status;

-- Show failed images older than 7 days
SELECT 
    story_id,
    image_id,
    status,
    created_at,
    updated_at,
    generation_metadata->>'error' as error_message
FROM story_images 
WHERE status = 'failed' 
    AND updated_at < NOW() - INTERVAL '7 days'
ORDER BY updated_at DESC
LIMIT 20;

-- Count of failed images to be deleted
SELECT COUNT(*) as failed_images_to_delete
FROM story_images 
WHERE status = 'failed' 
    AND updated_at < NOW() - INTERVAL '7 days';

-- DELETE old failed images (uncomment to execute)
-- CAUTION: This will permanently delete failed image records
/*
DELETE FROM story_images 
WHERE status = 'failed' 
    AND updated_at < NOW() - INTERVAL '7 days';
*/

-- Alternative: Archive failed images to a backup table first
CREATE TABLE IF NOT EXISTS story_images_archive AS 
SELECT * FROM story_images WHERE false;

-- Move failed images to archive (uncomment to execute)
/*
INSERT INTO story_images_archive 
SELECT * FROM story_images 
WHERE status = 'failed' 
    AND updated_at < NOW() - INTERVAL '7 days';

DELETE FROM story_images 
WHERE status = 'failed' 
    AND updated_at < NOW() - INTERVAL '7 days';
*/

-- For immediate cleanup of the specific problematic image (if you know the IDs)
-- Replace with actual story_id and image_id from your logs
/*
DELETE FROM story_images 
WHERE story_id = '2ac97462-8cc5-485b-919b-23708368ee8e' 
    AND image_id = 'img_f49afa0a' 
    AND status = 'failed';
*/

-- Verify cleanup results
SELECT 
    status,
    COUNT(*) as count,
    MIN(created_at) as oldest,
    MAX(created_at) as newest
FROM story_images 
GROUP BY status
ORDER BY status;