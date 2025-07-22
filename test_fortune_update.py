#!/usr/bin/env python3
"""
Quick test script to verify that the fortune routes imports and functions work correctly
after updating to use the centralized LLM client.
"""

import sys
import os
sys.path.append('/Users/damonwilliams/Projects/fairydust')

def test_imports():
    """Test that all imports work correctly"""
    try:
        # Test importing the updated fortune routes
        from services.content.fortune_routes import (
            router, 
            _build_fortune_prompt,
            _generate_fortune_llm,
            _get_llm_model_config,
            _calculate_zodiac,
            _calculate_life_path_number
        )
        
        # Test that LLM client is imported correctly
        from shared.llm_client import llm_client, LLMError
        
        print("✅ All imports successful")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_helper_functions():
    """Test that fortune-specific helper functions still work"""
    try:
        from services.content.fortune_routes import _calculate_zodiac, _calculate_life_path_number
        
        # Test zodiac calculation
        sign, element, planet = _calculate_zodiac("1990-07-15")  # Leo
        assert sign == "Leo"
        assert element == "Fire"
        assert planet == "Sun"
        print(f"✅ Zodiac calculation works: {sign} ({element}, {planet})")
        
        # Test life path calculation
        life_path = _calculate_life_path_number("1990-07-15")
        assert isinstance(life_path, int)
        assert 1 <= life_path <= 33
        print(f"✅ Life path calculation works: {life_path}")
        
        return True
        
    except Exception as e:
        print(f"❌ Helper function error: {e}")
        return False

def main():
    print("🔮 Testing Fortune Routes Updates...")
    print("=" * 50)
    
    success = True
    success &= test_imports()
    success &= test_helper_functions()
    
    print("=" * 50)
    if success:
        print("🎉 All tests passed! Fortune routes successfully updated to use centralized LLM client.")
    else:
        print("💥 Some tests failed. Please check the output above.")
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())