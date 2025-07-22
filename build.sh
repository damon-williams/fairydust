#!/bin/bash
# Build and deploy back end

set -e

echo "🚀 Building fairydust"
echo "=================================="

git add .
git commit -m "new build"

echo ""
echo "🚀 Changes committed successfully!"

git push
echo "Pushing changes"