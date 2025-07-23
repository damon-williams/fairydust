#!/usr/bin/env python3
"""Test script for the new Google Places API implementation"""

import asyncio
import os
from google_places_new_api import get_google_places_new_api_service

async def test_new_places_api():
    """Test the new Places API service"""
    
    # Check if API key is available
    api_key = os.getenv("GOOGLE_PLACES_API_KEY")
    if not api_key:
        print("❌ GOOGLE_PLACES_API_KEY not set. Skipping API test.")
        return
    
    try:
        # Initialize service
        service = get_google_places_new_api_service()
        print("✅ New Places API service initialized successfully")
        
        # Test text search with a simple query
        print("\n🔍 Testing text search: 'italian restaurants'")
        results = await service.search_restaurants_text(
            text_query="italian restaurants",
            latitude=37.7749,  # San Francisco
            longitude=-122.4194,
            radius_miles=2,
            max_results=3
        )
        
        print(f"✅ Text search returned {len(results)} results")
        
        if results:
            print("\n📋 Sample result:")
            sample = results[0]
            print(f"  Name: {sample.get('name')}")
            print(f"  Cuisine: {sample.get('cuisine')}")
            print(f"  Address: {sample.get('address')}")
            print(f"  Rating: {sample.get('rating')}")
            print(f"  Features: {sample.get('features', [])}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing new Places API: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing New Google Places API Implementation")
    print("=" * 50)
    
    # Run test
    success = asyncio.run(test_new_places_api())
    
    if success:
        print("\n✅ All tests passed!")
    else:
        print("\n❌ Tests failed!")