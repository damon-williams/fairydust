# email_service.py
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import aiosmtplib

# Email configuration
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@fairydust.fun")


async def send_email(to_email: str, subject: str, body: str, html_body: Optional[str] = None):
    """Send email using SMTP"""
    message = MIMEMultipart("alternative")
    message["From"] = FROM_EMAIL
    message["To"] = to_email
    message["Subject"] = subject

    # Add plain text part
    message.attach(MIMEText(body, "plain"))

    # Add HTML part if provided
    if html_body:
        message.attach(MIMEText(html_body, "html"))

    # Send email
    await aiosmtplib.send(
        message,
        hostname=SMTP_HOST,
        port=SMTP_PORT,
        username=SMTP_USERNAME,
        password=SMTP_PASSWORD,
        start_tls=True,
    )


async def send_otp_email(email: str, otp: str):
    """Send OTP verification email"""
    subject = "Your fairydust verification code"

    body = f"""
    Your verification code is: {otp}

    This code will expire in 10 minutes.

    If you didn't request this code, please ignore this email.

    - The fairydust team
    """

    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #667eea;">Your fairydust verification code</h2>
                <div style="background-color: #f4f4f4; padding: 20px; border-radius: 8px; text-align: center; margin: 20px 0;">
                    <h1 style="font-size: 36px; letter-spacing: 8px; color: #667eea; margin: 0;">{otp}</h1>
                </div>
                <p>This code will expire in 10 minutes.</p>
                <p style="color: #666; font-size: 14px;">If you didn't request this code, please ignore this email.</p>
                <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
                <p style="color: #999; font-size: 12px; text-align: center;">- The fairydust team</p>
            </div>
        </body>
    </html>
    """

    await send_email(email, subject, body, html_body)
