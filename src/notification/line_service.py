"""
LINE Bot push message service for group notifications.
Push-only: sends messages to a LINE group via the Messaging API.
No webhook handler needed.
"""
from __future__ import annotations

import os

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_GROUP_ID = os.getenv("LINE_GROUP_ID", "")
# When set, every successful or failed group push is also mirrored to this
# personal user ID — useful for testing/observing scheduled messages without
# depending on bot membership in the group.
LINE_MIRROR_USER_ID = os.getenv("LINE_MIRROR_USER_ID", "")


def send_line_group_message(message: str) -> tuple[bool, str]:
    """
    Send a text message to the configured LINE group.
    Returns (success, error_message).

    If LINE_MIRROR_USER_ID env var is set, the same message is also pushed to
    that personal user (attempted independently — group success/failure does
    not affect the mirror, and vice versa). The returned tuple still reflects
    the group push result only.
    """
    if not LINE_CHANNEL_ACCESS_TOKEN:
        return False, "LINE_CHANNEL_ACCESS_TOKEN not configured"
    if not LINE_GROUP_ID:
        return False, "LINE_GROUP_ID not configured"
    if not message.strip():
        return False, "Empty message"

    try:
        from linebot.v3.messaging import (
            ApiClient,
            Configuration,
            MessagingApi,
            PushMessageRequest,
            TextMessage,
        )

        configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
        with ApiClient(configuration) as api_client:
            messaging_api = MessagingApi(api_client)
            try:
                messaging_api.push_message(
                    PushMessageRequest(
                        to=LINE_GROUP_ID,
                        messages=[TextMessage(text=message)],
                    )
                )
                group_success, group_error = True, ""
            except Exception as e:
                group_success, group_error = False, str(e)

            if LINE_MIRROR_USER_ID:
                try:
                    messaging_api.push_message(
                        PushMessageRequest(
                            to=LINE_MIRROR_USER_ID,
                            messages=[TextMessage(text=message)],
                        )
                    )
                    print(f"[LINE] Mirrored to {LINE_MIRROR_USER_ID[:6]}...")
                except Exception as e:
                    print(f"[LINE] Mirror push failed: {e}")

        return group_success, group_error

    except ImportError:
        return False, "line-bot-sdk not installed"
    except Exception as e:
        return False, str(e)


def send_line_push_message(to_id: str, message: str) -> tuple[bool, str]:
    """
    Send a text push message to any LINE target ID (user / group / room).
    Returns (success, error_message).
    """
    if not LINE_CHANNEL_ACCESS_TOKEN:
        return False, "LINE_CHANNEL_ACCESS_TOKEN not configured"
    if not to_id:
        return False, "Empty to_id"
    if not message.strip():
        return False, "Empty message"

    try:
        from linebot.v3.messaging import (
            ApiClient,
            Configuration,
            MessagingApi,
            PushMessageRequest,
            TextMessage,
        )

        configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
        with ApiClient(configuration) as api_client:
            messaging_api = MessagingApi(api_client)
            messaging_api.push_message(
                PushMessageRequest(
                    to=to_id,
                    messages=[TextMessage(text=message)],
                )
            )
        return True, ""

    except ImportError:
        return False, "line-bot-sdk not installed"
    except Exception as e:
        return False, str(e)


def test_line_connection() -> dict:
    """
    Test LINE Bot connection by sending a test message to the group.
    Returns { success, message, group_id }.
    """
    if not LINE_CHANNEL_ACCESS_TOKEN:
        return {
            "success": False,
            "message": "LINE_CHANNEL_ACCESS_TOKEN not configured",
            "group_id": None,
        }
    if not LINE_GROUP_ID:
        return {
            "success": False,
            "message": "LINE_GROUP_ID not configured",
            "group_id": None,
        }

    success, error = send_line_group_message(
        "[5-Man Keeper League] LINE Bot connection test OK"
    )
    return {
        "success": success,
        "message": error if not success else "Test message sent to group",
        "group_id": LINE_GROUP_ID[:8] + "..." if LINE_GROUP_ID else None,
    }
