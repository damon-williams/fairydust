#!/usr/bin/env python3
"""
Test script for restaurant app endpoints
Usage: python3 test_restaurant_endpoints.py
"""

from uuid import uuid4

import requests

# Base URL for content service
BASE_URL = "https://fairydust-content-production.up.railway.app"


def test_health():
    """Test basic service health"""
    print("🔍 Testing service health...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"   Error: {e}")
        return False


def test_openapi():
    """Test if restaurant endpoints are in OpenAPI schema"""
    print("\n🔍 Testing OpenAPI schema for restaurant endpoints...")
    try:
        response = requests.get(f"{BASE_URL}/openapi.json")
        if response.status_code == 200:
            schema = response.json()
            restaurant_paths = [
                path for path in schema.get("paths", {}).keys() if "restaurant" in path
            ]
            print(f"   Found restaurant paths: {restaurant_paths}")
            return len(restaurant_paths) > 0
        else:
            print(f"   Failed to get OpenAPI schema: {response.status_code}")
            return False
    except Exception as e:
        print(f"   Error: {e}")
        return False


def test_generate_endpoint():
    """Test the restaurant generate endpoint"""
    print("\n🔍 Testing restaurant generate endpoint...")

    # This will fail without auth, but we can check if the endpoint exists
    test_data = {
        "user_id": str(uuid4()),
        "location": {"latitude": 37.7749, "longitude": -122.4194, "address": "San Francisco, CA"},
        "preferences": {
            "party_size": 4,
            "cuisine_types": ["Italian"],
            "time_preference": "tonight",
        },
        "selected_people": [],
    }

    try:
        response = requests.post(
            f"{BASE_URL}/restaurant/generate",
            json=test_data,
            headers={"Content-Type": "application/json"},
        )
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text[:200]}...")

        # We expect 401/403 (auth required) not 404 (endpoint not found)
        return response.status_code in [401, 403, 422]  # 422 = validation error is also OK
    except Exception as e:
        print(f"   Error: {e}")
        return False


def test_preferences_endpoint():
    """Test the restaurant preferences endpoint"""
    print("\n🔍 Testing restaurant preferences endpoint...")

    test_user_id = str(uuid4())

    try:
        response = requests.get(
            f"{BASE_URL}/restaurant/preferences/{test_user_id}",
            headers={"Content-Type": "application/json"},
        )
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text[:200]}...")

        # We expect 401/403 (auth required) not 404 (endpoint not found)
        return response.status_code in [401, 403, 422]
    except Exception as e:
        print(f"   Error: {e}")
        return False


def main():
    """Run all tests"""
    print("🍽️  Restaurant App Endpoint Testing")
    print("=" * 50)

    tests = [
        ("Service Health", test_health),
        ("OpenAPI Schema", test_openapi),
        ("Generate Endpoint", test_generate_endpoint),
        ("Preferences Endpoint", test_preferences_endpoint),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"   Unexpected error in {test_name}: {e}")
            results.append((test_name, False))

    print("\n📊 Test Results:")
    print("=" * 30)
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} {test_name}")

    total_passed = sum(1 for _, passed in results if passed)
    print(f"\nPassed: {total_passed}/{len(results)}")

    if total_passed == len(results):
        print("\n🎉 All tests passed! Restaurant endpoints are working.")
    elif total_passed >= 2:  # Health + at least one endpoint
        print("\n⚠️  Some tests failed, but core functionality appears to be working.")
    else:
        print("\n🚨 Multiple tests failed. Check deployment status.")


if __name__ == "__main__":
    main()
