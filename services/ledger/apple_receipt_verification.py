# services/ledger/apple_receipt_verification.py
import json
import os
from typing import Dict, Optional, Tuple

import httpx
from fastapi import HTTPException


class AppleReceiptVerificationService:
    """Service for verifying Apple App Store receipts"""

    def __init__(self):
        self.bundle_id = os.getenv("APPLE_BUNDLE_ID")
        self.team_id = os.getenv("APPLE_TEAM_ID", "5W2L2KPQDY")
        # Note: shared_secret not needed for one-time purchases, only auto-renewable subscriptions
        
        # Use configurable verification URL (defaults to sandbox for safety)
        self.verification_url = os.getenv("APPLE_VERIFICATION_URL", "https://sandbox.itunes.apple.com/verifyReceipt")
        
        # Keep both URLs for Apple's recommended fallback pattern
        self.production_url = "https://buy.itunes.apple.com/verifyReceipt"
        self.sandbox_url = "https://sandbox.itunes.apple.com/verifyReceipt"
        
        # Product ID to DUST amount mapping
        self.product_dust_mapping = {
            "dust_50": 50,
            "dust_100": 100,
            "dust_200": 200,
            "dust_500": 500,
            "dust_1000": 1000,
        }

    async def verify_receipt(self, receipt_data: str, product_id: str) -> Tuple[bool, Dict, Optional[str]]:
        """
        Verify receipt with Apple App Store
        
        Returns:
            (is_valid, verification_response, error_message)
        """
        if not self.bundle_id:
            return False, {}, "Apple Bundle ID not configured"
            
        if product_id not in self.product_dust_mapping:
            return False, {}, f"Invalid product ID: {product_id}"

        # Prepare request payload for one-time purchases
        # Note: password (shared secret) only needed for auto-renewable subscriptions
        request_data = {
            "receipt-data": receipt_data,
            "exclude-old-transactions": True
        }

        # First try the configured environment (staging = sandbox)
        primary_env = "sandbox" if "sandbox" in self.verification_url else "production"
        is_valid, response, error = await self._verify_with_url(
            self.verification_url, request_data, primary_env
        )
        
        # Apple's recommended fallback: if we get 21007/21008 (wrong environment), try the other
        status_code = response.get("status") if response else None
        if not is_valid and status_code in [21007, 21008]:
            fallback_url = self.sandbox_url if primary_env == "production" else self.production_url
            fallback_env = "sandbox" if primary_env == "production" else "production"
            
            print(f"🍎 APPLE_RECEIPT: {primary_env} returned {status_code}, trying {fallback_env}")
            is_valid, response, error = await self._verify_with_url(
                fallback_url, request_data, fallback_env
            )
        
        if is_valid:
            # Additional validation
            validation_error = self._validate_receipt_contents(response, product_id)
            if validation_error:
                return False, response, validation_error
                
        return is_valid, response, error

    async def _verify_with_url(self, url: str, request_data: Dict, environment: str) -> Tuple[bool, Dict, Optional[str]]:
        """Verify receipt with specific Apple URL"""
        try:
            print(f"🍎 APPLE_RECEIPT: Verifying with {environment} environment")
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    json=request_data,
                    headers={"Content-Type": "application/json"}
                )
                
                print(f"🍎 APPLE_RECEIPT: {environment} response status: {response.status_code}")
                
                if response.status_code != 200:
                    return False, {}, f"Apple API returned status {response.status_code}"
                
                verification_response = response.json()
                status = verification_response.get("status", -1)
                
                print(f"🍎 APPLE_RECEIPT: Apple verification status: {status}")
                
                # Status 0 = valid receipt
                if status == 0:
                    return True, verification_response, None
                else:
                    error_msg = self._get_error_message(status)
                    return False, verification_response, error_msg
                    
        except httpx.TimeoutException:
            return False, {}, "Apple verification request timed out"
        except httpx.RequestError as e:
            return False, {}, f"Network error verifying receipt: {str(e)}"
        except json.JSONDecodeError:
            return False, {}, "Invalid JSON response from Apple"
        except Exception as e:
            return False, {}, f"Unexpected error verifying receipt: {str(e)}"

    def _validate_receipt_contents(self, response: Dict, expected_product_id: str) -> Optional[str]:
        """Validate the contents of a verified receipt"""
        
        # Check bundle ID matches
        receipt = response.get("receipt", {})
        bundle_id = receipt.get("bundle_id")
        
        if bundle_id != self.bundle_id:
            return f"Bundle ID mismatch. Expected: {self.bundle_id}, Got: {bundle_id}"
        
        # Check for in-app purchases
        in_app_purchases = receipt.get("in_app", [])
        if not in_app_purchases:
            return "No in-app purchases found in receipt"
        
        # Find the purchase with matching product ID
        matching_purchase = None
        for purchase in in_app_purchases:
            if purchase.get("product_id") == expected_product_id:
                matching_purchase = purchase
                break
        
        if not matching_purchase:
            return f"Product ID {expected_product_id} not found in receipt"
        
        # Additional checks could be added here:
        # - Purchase date validation
        # - Quantity validation
        # - Transaction ID uniqueness check
        
        return None  # Valid

    def _get_error_message(self, status_code: int) -> str:
        """Get human-readable error message for Apple status codes"""
        error_messages = {
            21000: "The App Store could not read the JSON object you provided.",
            21002: "The data in the receipt-data property was malformed or missing.",
            21003: "The receipt could not be authenticated.",
            21004: "The shared secret you provided does not match the shared secret on file for your account.",
            21005: "The receipt server is not currently available.",
            21006: "This receipt is valid but the subscription has expired.",
            21007: "This receipt is from the sandbox environment, but it was sent to the production environment for verification.",
            21008: "This receipt is from the production environment, but it was sent to the sandbox environment for verification.",
            21010: "This receipt could not be authorized. Treat this the same as if a purchase was never made.",
        }
        
        return error_messages.get(status_code, f"Unknown Apple verification error: {status_code}")

    def extract_transaction_data(self, verification_response: Dict, product_id: str) -> Dict:
        """Extract transaction data from Apple's verification response"""
        receipt = verification_response.get("receipt", {})
        in_app_purchases = receipt.get("in_app", [])
        
        # Find the matching purchase
        matching_purchase = None
        for purchase in in_app_purchases:
            if purchase.get("product_id") == product_id:
                matching_purchase = purchase
                break
        
        if not matching_purchase:
            raise HTTPException(status_code=400, detail="Purchase not found in receipt")
        
        return {
            "apple_transaction_id": matching_purchase.get("transaction_id"),
            "apple_original_transaction_id": matching_purchase.get("original_transaction_id"),
            "apple_product_id": matching_purchase.get("product_id"),
            "apple_purchase_date_ms": int(matching_purchase.get("purchase_date_ms", 0)),
            "dust_amount": self.product_dust_mapping.get(product_id, 0),
            "quantity": int(matching_purchase.get("quantity", 1)),
        }

    def get_dust_amount_for_product(self, product_id: str) -> int:
        """Get DUST amount for a product ID"""
        return self.product_dust_mapping.get(product_id, 0)