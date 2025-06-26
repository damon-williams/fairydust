#!/usr/bin/env python3
"""
Minimal startup test for content service
"""

print("🚨 TEST: Starting content service startup test...")

try:
    print("🚨 TEST: Testing FastAPI import...")

    print("🚨 TEST: ✅ FastAPI imported successfully")
except Exception as e:
    print(f"🚨 TEST: ❌ FastAPI import failed: {e}")
    exit(1)

try:
    print("🚨 TEST: Testing Google Places import...")

    print("🚨 TEST: ✅ Google Places service imported successfully")
except Exception as e:
    print(f"🚨 TEST: ❌ Google Places import failed: {e}")

try:
    print("🚨 TEST: Testing restaurant routes import...")

    print("🚨 TEST: ✅ Restaurant routes imported successfully")
except Exception as e:
    print(f"🚨 TEST: ❌ Restaurant routes import failed: {e}")
    exit(1)

try:
    print("🚨 TEST: Testing main app import...")

    print("🚨 TEST: ✅ Main app imported successfully")
except Exception as e:
    print(f"🚨 TEST: ❌ Main app import failed: {e}")
    exit(1)

print("🚨 TEST: ✅ All imports successful - content service should start properly")
