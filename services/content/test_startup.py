#!/usr/bin/env python3
"""
Minimal startup test for content service
"""

print("🚨 TEST: Starting content service startup test...")

try:
    print("🚨 TEST: Testing FastAPI import...")
    from fastapi import FastAPI
    print("🚨 TEST: ✅ FastAPI imported successfully")
except Exception as e:
    print(f"🚨 TEST: ❌ FastAPI import failed: {e}")
    exit(1)

try:
    print("🚨 TEST: Testing Google Places import...")
    from google_places_service import get_google_places_service
    print("🚨 TEST: ✅ Google Places service imported successfully")
except Exception as e:
    print(f"🚨 TEST: ❌ Google Places import failed: {e}")

try:
    print("🚨 TEST: Testing restaurant routes import...")
    from restaurant_routes import router as restaurant_router
    print("🚨 TEST: ✅ Restaurant routes imported successfully")
except Exception as e:
    print(f"🚨 TEST: ❌ Restaurant routes import failed: {e}")
    exit(1)

try:
    print("🚨 TEST: Testing main app import...")
    from main import app
    print("🚨 TEST: ✅ Main app imported successfully")
except Exception as e:
    print(f"🚨 TEST: ❌ Main app import failed: {e}")
    exit(1)

print("🚨 TEST: ✅ All imports successful - content service should start properly")