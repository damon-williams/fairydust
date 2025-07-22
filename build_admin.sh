#!/bin/bash
# Build and deploy admin portal

set -e

echo "🚀 Building Admin Portal ..."
echo "=================================="

# Change to admin-ui directory
cd services/admin-ui

# Build the React app
echo "📦 Building React app..."
npm run build

# Copy to static directory
echo "📂 Copying files to admin/static..."
cp -r dist/* ../admin/static/

echo "✅ Admin Portal build complete!"
echo ""

# Return to project root for git commands
cd ../..

echo "📝 Committing changes..."
git add .
git commit -m "Update admin portal"

echo ""
echo "🚀 Changes committed successfully!"

git push
echo "Pushing changes"