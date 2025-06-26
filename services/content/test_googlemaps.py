#!/usr/bin/env python3
"""
Test script to verify googlemaps package installation
"""

print("🔍 GOOGLEMAPS_TEST: Testing googlemaps package availability...")

try:
    import googlemaps

    print("🔍 GOOGLEMAPS_TEST: ✅ googlemaps package imported successfully")
    print(f"🔍 GOOGLEMAPS_TEST: Package version: {googlemaps.__version__}")

    # Test creating client (without API key)
    try:
        client = googlemaps.Client(key="test_key")
        print("🔍 GOOGLEMAPS_TEST: ✅ googlemaps.Client created successfully")
    except Exception as e:
        print(f"🔍 GOOGLEMAPS_TEST: ⚠️ Client creation failed (expected): {e}")

except ImportError as e:
    print(f"🔍 GOOGLEMAPS_TEST: ❌ googlemaps package not available: {e}")

    # Check what packages are installed
    try:
        import pkg_resources

        installed_packages = [d.project_name for d in pkg_resources.working_set]
        print(f"🔍 GOOGLEMAPS_TEST: Total installed packages: {len(installed_packages)}")

        # Look for google-related packages
        google_packages = [p for p in installed_packages if "google" in p.lower()]
        if google_packages:
            print(f"🔍 GOOGLEMAPS_TEST: Google-related packages: {google_packages}")
        else:
            print("🔍 GOOGLEMAPS_TEST: No google-related packages found")

    except Exception as e:
        print(f"🔍 GOOGLEMAPS_TEST: Could not check installed packages: {e}")

print("🔍 GOOGLEMAPS_TEST: Test complete")
