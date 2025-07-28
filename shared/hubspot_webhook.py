import asyncio
import logging
import os
from typing import Any, Optional

import aiohttp

logger = logging.getLogger(__name__)


async def send_hubspot_webhook(
    event_type: str, user_data: dict[str, Any], changed_fields: Optional[list[str]] = None
) -> bool:
    """
    Send user data to HubSpot via Zapier webhook

    Args:
        event_type: Type of event ('user.created' or 'user.updated')
        user_data: User data dictionary from database
        changed_fields: List of fields that were updated (for user.updated events)

    Returns:
        bool: True if webhook sent successfully, False otherwise
    """
    webhook_url = os.getenv("ZAPIER_HUBSPOT_WEBHOOK")
    webhook_enabled = os.getenv("HUBSPOT_WEBHOOK_ENABLED", "true").lower() == "true"

    if not webhook_url or not webhook_enabled:
        logger.debug(
            f"HubSpot webhook skipped - URL: {bool(webhook_url)}, Enabled: {webhook_enabled}"
        )
        return True  # Return success if webhook is intentionally disabled

    # Build webhook payload
    payload = {
        "event_type": event_type,
        "user_id": str(user_data["id"]),
        "fairyname": user_data["fairyname"],
        "email": user_data.get("email"),
        "phone": user_data.get("phone"),
        "first_name": user_data.get("first_name"),
        "birth_date": user_data.get("birth_date").isoformat()
        if user_data.get("birth_date")
        else None,
        "auth_provider": user_data.get("auth_provider"),
        "dust_balance": user_data.get("dust_balance", 0),
        "city": user_data.get("city"),
        "country": user_data.get("country"),
        "created_at": user_data["created_at"].isoformat() if user_data.get("created_at") else None,
        "updated_at": user_data["updated_at"].isoformat() if user_data.get("updated_at") else None,
        "is_admin": user_data.get("is_admin", False),
        "is_onboarding_completed": user_data.get("is_onboarding_completed", False),
    }

    # Add changed fields for update events
    if event_type == "user.updated" and changed_fields:
        payload["changed_fields"] = changed_fields

    # Remove None values to keep payload clean
    payload = {k: v for k, v in payload.items() if v is not None}

    try:
        timeout = aiohttp.ClientTimeout(total=5)  # 5 second timeout

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(webhook_url, json=payload) as response:
                if response.status == 200:
                    logger.info(
                        f"HubSpot webhook sent successfully: {event_type} for user {user_data.get('fairyname')}"
                    )
                    return True
                else:
                    logger.warning(
                        f"HubSpot webhook failed with status {response.status}: {event_type} for user {user_data.get('fairyname')}"
                    )
                    return False

    except asyncio.TimeoutError:
        logger.warning(
            f"HubSpot webhook timeout: {event_type} for user {user_data.get('fairyname')}"
        )
        return False
    except Exception as e:
        logger.warning(
            f"HubSpot webhook error: {e} for {event_type} user {user_data.get('fairyname')}"
        )
        return False


def send_hubspot_webhook_sync(
    event_type: str, user_data: dict[str, Any], changed_fields: Optional[list[str]] = None
) -> bool:
    """
    Synchronous wrapper for send_hubspot_webhook
    Use when you can't use async/await syntax
    """
    try:
        return asyncio.run(send_hubspot_webhook(event_type, user_data, changed_fields))
    except Exception as e:
        logger.warning(f"HubSpot webhook sync error: {e}")
        return False


async def send_user_created_webhook(user_data: dict[str, Any]) -> bool:
    """
    Convenience function for user creation events
    """
    return await send_hubspot_webhook("user.created", user_data)


async def send_user_updated_webhook(user_data: dict[str, Any], changed_fields: list[str]) -> bool:
    """
    Convenience function for user update events
    """
    return await send_hubspot_webhook("user.updated", user_data, changed_fields)
