#!/bin/bash

# Script to register the yoga-playlist-agents app in fairydust
# This should be run against the production database

echo "Registering yoga-playlist-agents app in fairydust..."
echo ""
echo "App Details:"
echo "- App ID: 7f3e4d2c-1a5b-4c3d-8e7f-9b8a7c6d5e4f"
echo "- Name: Yoga Playlist Generator"
echo "- Slug: yoga-playlist-generator"
echo "- Status: approved"
echo "- Pricing: 5 DUST (basic), 8 DUST (extended)"
echo ""

# For local development
if [ "$1" == "local" ]; then
    echo "Running against local database..."
    PGPASSWORD=password psql -h localhost -U postgres -d fairydust -f register_yoga_app.sql
else
    echo "To run this against production, you'll need to:"
    echo "1. Go to Railway dashboard"
    echo "2. Open the postgres service"
    echo "3. Go to the 'Query' tab"
    echo "4. Copy and paste the contents of register_yoga_app.sql"
    echo "5. Execute the query"
    echo ""
    echo "Or use Railway CLI:"
    echo "railway run psql -f scripts/register_yoga_app.sql"
fi