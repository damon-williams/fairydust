#!/usr/bin/env python3
"""
Basic test script for the Activity API endpoint
"""
from uuid import uuid4

import httpx

# Test configuration
BASE_URL = "http://localhost:8006"  # Content service URL
ENDPOINT = "/activity/search"

# Sample test request
test_request = {
    "user_id": str(uuid4()),  # Random UUID for testing
    "location": {"latitude": 37.7749, "longitude": -122.4194, "radius_miles": 10},  # San Francisco
    "location_type": "both",
    "selected_people": [],  # Empty for solo search
}


async def test_activity_search():
    """Test the activity search endpoint"""
    print("🧪 Testing Activity Search API...")
    print(
        f"📍 Location: {test_request['location']['latitude']}, {test_request['location']['longitude']}"
    )
    print(f"🎯 Radius: {test_request['location']['radius_miles']} miles")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{BASE_URL}{ENDPOINT}",
                json=test_request,
                headers={
                    "Content-Type": "application/json",
                    # Note: In real usage, you'd need proper JWT token here
                    "Authorization": "Bearer test-token",
                },
            )

            print(f"📊 Response Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                activities = data.get("activities", [])
                metadata = data.get("search_metadata", {})

                print(f"✅ Success! Found {len(activities)} activities")
                print(f"📈 Total found: {metadata.get('total_found', 0)}")
                print(f"📍 Search area: {metadata.get('location_address', 'Unknown')}")

                # Show first few activities
                for i, activity in enumerate(activities[:3]):
                    print(f"\n🎯 Activity {i+1}:")
                    print(f"   Name: {activity['name']}")
                    print(f"   Type: {activity['type']}")
                    print(f"   Distance: {activity['distance_miles']} miles")
                    print(f"   Rating: {activity.get('rating', 'N/A')}")
                    print(f"   AI Context: {activity['ai_context'][:100]}...")
                    print(f"   Tags: {activity['suitability_tags']}")

            else:
                print(f"❌ Error {response.status_code}: {response.text}")

    except Exception as e:
        print(f"❌ Test failed: {str(e)}")


def test_models():
    """Test Pydantic models can be imported and validated"""
    print("\n🧪 Testing Pydantic Models...")

    try:
        # Test importing models
        import os
        import sys

        sys.path.append(os.path.join(os.path.dirname(__file__), "services", "content"))

        from models import Activity, ActivitySearchRequest, ActivityType

        # Test basic model validation
        search_request = ActivitySearchRequest(**test_request)
        print("✅ ActivitySearchRequest validation passed")
        print(f"   User ID: {search_request.user_id}")
        print(f"   Location Type: {search_request.location_type}")

        # Test Activity model
        sample_activity = {
            "id": "act_123",
            "tripadvisor_id": "456",
            "name": "Sample Museum",
            "type": ActivityType.ATTRACTION,
            "address": "123 Main St",
            "distance_miles": 2.5,
            "latitude": 37.7749,
            "longitude": -122.4194,
            "ai_context": "Great place to visit!",
            "suitability_tags": ["educational", "indoor"],
        }

        activity = Activity(**sample_activity)
        print("✅ Activity model validation passed")
        print(f"   Activity: {activity.name} ({activity.type})")

    except Exception as e:
        print(f"❌ Model test failed: {str(e)}")


if __name__ == "__main__":
    print("🚀 Activity API Test Suite")
    print("=" * 50)

    # Test models first (no server required)
    test_models()

    # Test API endpoint (requires running server)
    print("\n" + "=" * 50)
    print("⚠️  Note: API test requires content service running on localhost:8006")
    print("   Start with: cd services/content && python main.py")
    print("   And proper authentication setup")

    # Uncomment to run API test when server is available
    # asyncio.run(test_activity_search())
