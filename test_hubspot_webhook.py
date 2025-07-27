#!/usr/bin/env python3
"""
Test script for HubSpot webhook integration
Run this to test the webhook functionality before setting up Zapier
"""

import asyncio
import os
import sys
from datetime import datetime
from uuid import uuid4

# Add shared directory to Python path
sys.path.append("shared")

from hubspot_webhook import send_user_created_webhook, send_user_updated_webhook

# Test data
SAMPLE_USER_DATA = {
    "id": str(uuid4()),
    "fairyname": "testcrystal123",
    "email": "test@example.com",
    "phone": "+1234567890",
    "first_name": "Test",
    "birth_date": datetime(1990, 1, 15).date(),
    "auth_provider": "otp",
    "dust_balance": 25,
    "city": "San Francisco",
    "country": "US",
    "created_at": datetime.now(),
    "updated_at": datetime.now(),
    "is_admin": False,
    "is_onboarding_completed": True,
}


async def test_user_created_webhook():
    """Test user creation webhook"""
    print("🧪 Testing user.created webhook...")

    success = await send_user_created_webhook(SAMPLE_USER_DATA)

    if success:
        print("✅ User created webhook sent successfully")
    else:
        print("❌ User created webhook failed")

    return success


async def test_user_updated_webhook():
    """Test user update webhook"""
    print("🧪 Testing user.updated webhook...")

    changed_fields = ["first_name", "birth_date"]
    success = await send_user_updated_webhook(SAMPLE_USER_DATA, changed_fields)

    if success:
        print("✅ User updated webhook sent successfully")
    else:
        print("❌ User updated webhook failed")

    return success


async def main():
    """Run all webhook tests"""
    print("🚀 HubSpot Webhook Integration Tests")
    print("=" * 50)

    # Check environment variables
    webhook_url = os.getenv("ZAPIER_HUBSPOT_WEBHOOK")
    webhook_enabled = os.getenv("HUBSPOT_WEBHOOK_ENABLED", "true").lower() == "true"

    print("📊 Environment Check:")
    print(f"   ZAPIER_HUBSPOT_WEBHOOK: {'✅ Set' if webhook_url else '❌ Not set'}")
    print(f"   HUBSPOT_WEBHOOK_ENABLED: {webhook_enabled}")
    print()

    if not webhook_url:
        print("⚠️  WARNING: ZAPIER_HUBSPOT_WEBHOOK not set")
        print("   Set this environment variable to test webhook integration")
        print(
            "   Example: export ZAPIER_HUBSPOT_WEBHOOK='https://hooks.zapier.com/hooks/catch/...'"
        )
        print()

    # Run tests
    results = []

    try:
        # Test user creation
        created_success = await test_user_created_webhook()
        results.append(("User Created", created_success))

        print()

        # Test user update
        updated_success = await test_user_updated_webhook()
        results.append(("User Updated", updated_success))

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        return False

    # Summary
    print()
    print("📋 Test Results:")
    print("-" * 30)

    all_passed = True
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"   {test_name}: {status}")
        if not success:
            all_passed = False

    print()
    if all_passed:
        print("🎉 All tests passed! HubSpot webhook integration is working.")
    else:
        print("⚠️  Some tests failed. Check your webhook configuration.")

    return all_passed


if __name__ == "__main__":
    # Run the tests
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
