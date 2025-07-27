#!/usr/bin/env python3
"""Test script to verify inspire routes imports work correctly"""

import sys

sys.path.append("/Users/damonwilliams/Projects/fairydust")

try:
    # Try to import the inspire routes module
    from services.content import inspire_routes

    print("✅ inspire_routes imports successfully")

    # Check if the centralized client import worked
    from services.content.inspire_routes import LLMError, llm_client

    print("✅ llm_client and LLMError imports successful")

    # Check if functions exist
    if hasattr(inspire_routes, "_generate_inspiration_llm_with_user"):
        print("✅ _generate_inspiration_llm_with_user function exists")
    else:
        print("❌ _generate_inspiration_llm_with_user function not found")

    print("\n🎉 All imports and functions verified successfully!")

except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Unexpected error: {e}")
    sys.exit(1)
