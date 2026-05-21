"""
LINE Bot push message service for group notifications.
Push-only: sends messages to a LINE group via the Messaging API.
No webhook handler needed.
"""
from __future__ import annotations

import os

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_GROUP_ID = os.getenv("LINE_GROUP_ID", "")
# Failed group pushes mirror a diagnostic message to this user.
# Successful group pushes mirror only when explicitly enabled to preserve quota.
LINE_MIRROR_USER_ID = os.getenv("LINE_MIRROR_USER_ID", "")
LINE_MIRROR_SUCCESS_ENABLED = (
    os.getenv("LINE_MIRROR_SUCCESS_ENABLED", "false").strip().lower()
    in {"1", "true", "yes", "on"}
)
LINE_PERSONAL_FALLBACK_ON_GROUP_FAILURE = (
    os.getenv("LINE_PERSONAL_FALLBACK_ON_GROUP_FAILURE", "true").strip().lower()
    in {"1", "true", "yes", "on"}
)
LINE_TEXT_LIMIT = 4900


def _preview_target(target_id: str) -> str:
    """Return a short, non-sensitive preview of a LINE target ID."""
    target_id = (target_id or "").strip()
    if not target_id:
        return "(empty)"
    if len(target_id) <= 10:
        return f"{target_id[:2]}..."
    return f"{target_id[:6]}...{target_id[-4:]}"


def _truncate_line_text(text: str, limit: int = LINE_TEXT_LIMIT) -> str:
    """Keep LINE text payloads safely below the API limit."""
    text = text or ""
    if len(text) <= limit:
        return text
    suffix = "\n\n[message truncated for LINE]"
    return text[: max(0, limit - len(suffix))] + suffix


def _summarize_error(error: Exception | str) -> str:
    """Bound LINE SDK errors so logs and mirror diagnostics stay readable."""
    message = str(error).strip() or error.__class__.__name__
    return _truncate_line_text(message, 1000)


def _group_target_error(target_id: str) -> str:
    """Detect the common case where LINE_GROUP_ID was set to a personal user ID."""
    target_id = (target_id or "").strip()
    if target_id.startswith("U"):
        return (
            "LINE_GROUP_ID points to a personal user ID. "
            "Configure the group/room target ID instead (usually starts with C or R)."
        )
    return ""


def _build_group_failure_diagnostic(error: str, original_message: str) -> str:
    preview = _truncate_line_text(original_message, 1200)
    lower_error = (error or "").lower()
    if (
        "monthly limit" in lower_error
        or "too many requests" in lower_error
        or "(429)" in lower_error
        or " 429" in lower_error
    ):
        action_hint = (
            "LINE monthly message quota is exhausted. "
            "Reduce group pushes or wait for the quota reset."
        )
    else:
        action_hint = "Please verify LINE_GROUP_ID and that the bot is still in the group."
    return "\n".join(
        [
            "[5-Man Keeper League] LINE group push failed",
            f"Group target: {_preview_target(LINE_GROUP_ID)}",
            f"Error: {error}",
            "",
            "The original message was not delivered to the group.",
            action_hint,
            "",
            "-- Original message preview --",
            preview,
        ]
    )


def _build_personal_fallback_message(original_message: str) -> str:
    return "\n".join(
        [
            "[5-Man Keeper League] 個人備份",
            "群組推送失敗，以下只送給你個人，不代表群組已送達。",
            "",
            original_message,
        ]
    )


def send_line_group_message(message: str) -> tuple[bool, str]:
    """
    Send a text message to the configured LINE group.
    Returns (success, error_message).

    If LINE_MIRROR_USER_ID env var is set, failed group pushes mirror a
    diagnostic message and, by default, a clearly labeled personal fallback
    copy of the original message. Successful group pushes mirror only when
    LINE_MIRROR_SUCCESS_ENABLED=true,
    so a personal push cannot look like successful group delivery. The returned
    tuple always reflects the group push result.
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

            def push_text(to_id: str, text: str):
                messaging_api.push_message(
                    PushMessageRequest(
                        to=to_id,
                        messages=[TextMessage(text=_truncate_line_text(text))],
                    )
                )

            def push_failure_mirror(error: str) -> str:
                notes: list[str] = []
                try:
                    push_text(
                        LINE_MIRROR_USER_ID,
                        _build_group_failure_diagnostic(error, message),
                    )
                    notes.append(
                        f"mirror diagnostic sent to {_preview_target(LINE_MIRROR_USER_ID)}"
                    )
                    print(
                        f"[LINE] Mirror diagnostic sent to "
                        f"{_preview_target(LINE_MIRROR_USER_ID)}"
                    )
                except Exception as e:
                    mirror_error = _summarize_error(e)
                    notes.append(f"mirror diagnostic failed: {mirror_error}")
                    print(f"[LINE] Mirror diagnostic failed: {mirror_error}")

                if LINE_PERSONAL_FALLBACK_ON_GROUP_FAILURE:
                    try:
                        push_text(
                            LINE_MIRROR_USER_ID,
                            _build_personal_fallback_message(message),
                        )
                        notes.append(
                            f"personal fallback sent to {_preview_target(LINE_MIRROR_USER_ID)}"
                        )
                        print(
                            f"[LINE] Personal fallback sent to "
                            f"{_preview_target(LINE_MIRROR_USER_ID)}"
                        )
                    except Exception as e:
                        fallback_error = _summarize_error(e)
                        notes.append(f"personal fallback failed: {fallback_error}")
                        print(f"[LINE] Personal fallback failed: {fallback_error}")

                return "; " + "; ".join(notes) if notes else ""

            target_error = _group_target_error(LINE_GROUP_ID)
            if target_error:
                group_error = target_error
                print(
                    f"[LINE] Group target invalid: {_preview_target(LINE_GROUP_ID)}. "
                    f"{group_error}"
                )
                mirror_note = ""
                if LINE_MIRROR_USER_ID:
                    mirror_note = push_failure_mirror(group_error)
                return False, group_error + mirror_note

            try:
                push_text(LINE_GROUP_ID, message)
                group_success, group_error = True, ""
                print(f"[LINE] Group push sent to {_preview_target(LINE_GROUP_ID)}")
            except Exception as e:
                group_success, group_error = False, _summarize_error(e)
                print(
                    f"[LINE] Group push failed for {_preview_target(LINE_GROUP_ID)}: "
                    f"{group_error}"
                )

            if LINE_MIRROR_USER_ID:
                try:
                    if group_success and LINE_MIRROR_SUCCESS_ENABLED:
                        push_text(LINE_MIRROR_USER_ID, message)
                        print(
                            f"[LINE] Mirrored to "
                            f"{_preview_target(LINE_MIRROR_USER_ID)}"
                        )
                    elif not group_success:
                        group_error = f"{group_error}{push_failure_mirror(group_error)}"
                except Exception as e:
                    mirror_error = _summarize_error(e)
                    if not group_success:
                        group_error = (
                            f"{group_error}; mirror diagnostic failed: {mirror_error}"
                        )
                    print(f"[LINE] Mirror push failed: {mirror_error}")

        return group_success, group_error

    except ImportError:
        return False, "line-bot-sdk not installed"
    except Exception as e:
        return False, _summarize_error(e)


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
                    messages=[TextMessage(text=_truncate_line_text(message))],
                )
            )
        return True, ""

    except ImportError:
        return False, "line-bot-sdk not installed"
    except Exception as e:
        return False, _summarize_error(e)


def test_line_connection() -> dict:
    """
    Test LINE Bot connection by sending a test message to the group.
    Returns { success, message, group_id, mirror_user_id }.
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
        "mirror_user_id": (
            _preview_target(LINE_MIRROR_USER_ID) if LINE_MIRROR_USER_ID else None
        ),
    }
