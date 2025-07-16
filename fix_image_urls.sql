-- Fix existing image URLs to use custom domain

-- Update old pub-domain URLs
UPDATE user_images 
SET url = REPLACE(url, 'https://pub-88a91804.r2.dev/fairydust-images/', 'https://images.fairydust.fun/')
WHERE url LIKE 'https://pub-88a91804%';

-- Update signed URLs (extract the path after fairydust-images/)
UPDATE user_images 
SET url = REGEXP_REPLACE(url, 
    'https://[a-f0-9]+\.r2\.cloudflarestorage\.com/fairydust-images/([^?]+).*', 
    'https://images.fairydust.fun/\1')
WHERE url LIKE '%r2.cloudflarestorage.com%';

-- Verify the changes
SELECT 
    CASE 
        WHEN url LIKE 'https://pub-88a91804%' THEN 'pub-domain'
        WHEN url LIKE '%r2.cloudflarestorage.com%' THEN 'signed-url'
        WHEN url LIKE 'https://images.fairydust.fun%' THEN 'custom-domain'
        ELSE 'other'
    END as url_type,
    COUNT(*) as count
FROM user_images 
GROUP BY 1;