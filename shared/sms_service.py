# sms_service.py
import os

import httpx

# SMS configuration (using Twilio as example)
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")


async def send_sms(to_number: str, message: str):
    """Send SMS using Twilio"""
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER]):
        # Log warning in production
        print(f"SMS not configured. Would send to {to_number}: {message}")
        return

    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
            data={"From": TWILIO_FROM_NUMBER, "To": to_number, "Body": message},
        )

        if response.status_code != 201:
            raise Exception(f"Failed to send SMS: {response.text}")


async def send_otp_sms(phone: str, otp: str):
    """Send OTP verification SMS"""
    message = f"Your fairydust verification code is: {otp}. Valid for 10 minutes."
    await send_sms(phone, message)
