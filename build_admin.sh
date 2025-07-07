#!/bin/bash
# Build and deploy admin portal

set -e

echo "🚀 Building Admin Portal v2.10.0..."
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
echo "📍 Version: 2.10.0"
echo ""
echo "Next steps:"
echo "1. git add ."
echo "2. git commit -m 'Update admin portal to v2.10.0 - Add action analytics'"