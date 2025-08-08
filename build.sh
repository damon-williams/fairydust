#!/bin/bash
# Build and deploy back end

set -e

echo "🚀 Building fairydust"
echo "=================================="

git add .

# Check if a commit message was provided as an argument
if [ -n "$1" ]; then
    echo "📝 Using custom commit message: $1"
    git commit -m "$1"
else
    echo "📝 Using default commit message"
    git commit -m "new build"
fi

echo ""
echo "🚀 Changes committed successfully!"

git push
echo "Pushing changes"