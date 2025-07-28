#!/usr/bin/env python3

import sys

sys.path.append("services/identity")

import json
from datetime import datetime
from uuid import uuid4

from models import User

# Test data similar to what comes from database
user_data = {
    "id": uuid4(),
    "fairyname": "testuser123",
    "email": "test@example.com",
    "phone": None,
    "is_admin": False,
    "first_name": "Test",
    "birth_date": None,
    "is_onboarding_completed": True,
    "dust_balance": 100,
    "auth_provider": "otp",
    "last_login_date": datetime.now(),
    "created_at": datetime.now(),
    "updated_at": datetime.now(),
    "daily_bonus_eligible": True,
}

print("=== Input data ===")
print("Keys:", list(user_data.keys()))
print("daily_bonus_eligible value:", user_data.get("daily_bonus_eligible"))

print("\n=== Creating User model ===")
user = User(**user_data)
print("User created successfully")

print("\n=== model_dump() output ===")
user_dict = user.model_dump()
print("Keys:", list(user_dict.keys()))
print("daily_bonus_eligible in dict:", "daily_bonus_eligible" in user_dict)
print("is_daily_bonus_eligible in dict:", "is_daily_bonus_eligible" in user_dict)
print("daily_bonus_eligible value:", user_dict.get("daily_bonus_eligible"))
print("is_daily_bonus_eligible value:", user_dict.get("is_daily_bonus_eligible"))

print("\n=== JSON serialization ===")
json_output = user.model_dump_json()
print("JSON output:")
print(json_output)

# Parse back to see structure
parsed = json.loads(json_output)
print("\nParsed JSON keys:", list(parsed.keys()))
print("daily_bonus_eligible in parsed:", "daily_bonus_eligible" in parsed)
print("is_daily_bonus_eligible in parsed:", "is_daily_bonus_eligible" in parsed)
