-- Check current image URLs in database
SELECT 
    id,
    LEFT(url, 80) as url_preview,
    created_at
FROM user_images 
ORDER BY created_at DESC 
LIMIT 10;

-- Count different URL patterns
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