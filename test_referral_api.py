#!/usr/bin/env python3
"""Test script for referral API endpoints"""

import os
from urllib.parse import urljoin

import requests

# Test configuration
ADMIN_BASE_URL = os.getenv("ADMIN_BASE_URL", "http://localhost:8004")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@fairydust.fun")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")


def test_admin_login():
    """Test admin login and get session cookie"""
    login_url = urljoin(ADMIN_BASE_URL, "/admin/auth/login")

    login_data = {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}

    print(f"Testing admin login at: {login_url}")

    try:
        response = requests.post(login_url, json=login_data)
        print(f"Login response: {response.status_code}")
        print(f"Response headers: {dict(response.headers)}")

        if response.status_code == 200:
            print("✓ Login successful")
            return response.cookies
        else:
            print(f"✗ Login failed: {response.text}")
            return None

    except Exception as e:
        print(f"✗ Login error: {e}")
        return None


def test_referral_endpoints(cookies):
    """Test referral API endpoints"""
    if not cookies:
        print("No cookies available, skipping endpoint tests")
        return

    endpoints = [
        "/admin/referrals/config",
        "/admin/referrals/stats",
        "/admin/referrals/codes",
        "/admin/referrals/redemptions",
        "/admin/referrals/promotional-codes",
    ]

    for endpoint in endpoints:
        url = urljoin(ADMIN_BASE_URL, endpoint)
        print(f"\nTesting: {url}")

        try:
            response = requests.get(url, cookies=cookies)
            print(f"Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(
                    f"✓ Success - Data keys: {list(data.keys()) if isinstance(data, dict) else 'Non-dict response'}"
                )

                # Show first few items if it's a list
                if isinstance(data, dict):
                    for key, value in data.items():
                        if isinstance(value, list) and len(value) > 0:
                            print(f"  {key}: {len(value)} items")
                        elif isinstance(value, (int, float, str, bool)):
                            print(f"  {key}: {value}")

            else:
                print(f"✗ Failed - Response: {response.text[:200]}...")

        except Exception as e:
            print(f"✗ Error: {e}")


def main():
    print("=== Testing Referral API Endpoints ===\n")

    # Test login
    cookies = test_admin_login()

    # Test endpoints
    test_referral_endpoints(cookies)

    print("\n=== Test Complete ===")


if __name__ == "__main__":
    main()
