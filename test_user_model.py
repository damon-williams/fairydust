#!/usr/bin/env python3

import sys
import os
sys.path.append('services/identity')
sys.path.append('shared')

from models import User
from datetime import datetime
from uuid import uuid4
import json

# Create test user data (simulating database row)
user_data = {
    'id': uuid4(),
    'fairyname': 'testfairy123',
    'email': 'test@example.com',
    'phone': None,
    'is_admin': False,
    'first_name': 'Test',
    'birth_date': None,
    'is_onboarding_completed': True,
    'dust_balance': 100,
    'auth_provider': 'otp',
    'last_login_date': datetime.now(),
    'created_at': datetime.now(),
    'updated_at': datetime.now(),
    'daily_bonus_eligible': True  # This is the calculated field
}

print("=== Testing User Model Serialization ===")
print("Input data keys:", list(user_data.keys()))

# Create User model
user = User(**user_data)
print("\nUser model created successfully")

# Serialize to dict
user_dict = user.model_dump()
print("\nSerialized user dict keys:", list(user_dict.keys()))
print("daily_bonus_eligible value:", user_dict.get('daily_bonus_eligible'))

# Check for any unwanted fields
unwanted_fields = [k for k in user_dict.keys() if 'is_daily_bonus' in k]
print("Unwanted fields with 'is_daily_bonus':", unwanted_fields)

# Serialize to JSON (what API would return)
user_json = user.model_dump_json()
print("\nJSON representation:")
print(user_json)