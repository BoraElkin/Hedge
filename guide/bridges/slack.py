"""Slack bridge for bot messaging."""

from __future__ import annotations

from typing import Any

import httpx

from guide.bridges.base import (
    IncomingMessage,
    MessageBridge,
    MessageType,
    OutgoingMessage,
)


class SlackBridge(MessageBridge):
    """Bridge for Slack Bot API.

    Handles:
    - Incoming messages via Events API webhook
    - Outgoing messages via Web API
    - File uploads for images
    """

    platform = "slack"

    def __init__(self, bot_token: str) -> None:
        self._token = bot_token
        self._base_url = "https://slack.com/api"

    async def send_message(self, message: OutgoingMessage) -> bool:
        """Send a message via Slack."""
        if message.media_url:
            # Send image with optional text
            return await self._send_with_image(
                message.recipient_id,
                message.media_url,
                message.text,
            )
        elif message.text:
            return await self.send_text(message.recipient_id, message.text)
        return False

    async def send_text(self, recipient_id: str, text: str) -> bool:
        """Send a text message to a channel or DM."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base_url}/chat.postMessage",
                headers={"Authorization": f"Bearer {self._token}"},
                json={
                    "channel": recipient_id,
                    "text": text,
                    "mrkdwn": True,
                },
                timeout=30,
            )
            data = response.json()
            return data.get("ok", False)

    async def send_image(
        self,
        recipient_id: str,
        image_url: str | None = None,
        image_data: bytes | None = None,
        caption: str | None = None,
    ) -> bool:
        """Send an image to a channel."""
        if image_url:
            return await self._send_with_image(recipient_id, image_url, caption)
        elif image_data:
            return await self._upload_image(recipient_id, image_data, caption)
        return False

    async def _send_with_image(
        self,
        channel: str,
        image_url: str,
        text: str | None = None,
    ) -> bool:
        """Send a message with an image attachment."""
        blocks = [
            {
                "type": "image",
                "image_url": image_url,
                "alt_text": text or "Image",
            }
        ]

        if text:
            blocks.insert(0, {
                "type": "section",
                "text": {"type": "mrkdwn", "text": text},
            })

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base_url}/chat.postMessage",
                headers={"Authorization": f"Bearer {self._token}"},
                json={
                    "channel": channel,
                    "blocks": blocks,
                    "text": text or "Image",
                },
                timeout=30,
            )
            data = response.json()
            return data.get("ok", False)

    async def _upload_image(
        self,
        channel: str,
        image_data: bytes,
        caption: str | None = None,
    ) -> bool:
        """Upload an image file to Slack."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base_url}/files.upload",
                headers={"Authorization": f"Bearer {self._token}"},
                data={
                    "channels": channel,
                    "initial_comment": caption or "",
                },
                files={"file": ("image.jpg", image_data, "image/jpeg")},
                timeout=60,
            )
            data = response.json()
            return data.get("ok", False)

    def parse_webhook(self, payload: dict[str, Any]) -> IncomingMessage | None:
        """Parse Slack Events API webhook payload."""
        event = payload.get("event", {})

        if event.get("type") != "message":
            return None

        # Ignore bot messages
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return None

        user_id = event.get("user", "")
        channel = event.get("channel", "")
        text = event.get("text", "")

        # Check for file attachments
        files = event.get("files", [])
        media_url = None
        message_type = MessageType.TEXT

        if files:
            for f in files:
                if f.get("mimetype", "").startswith("image/"):
                    media_url = f.get("url_private")
                    message_type = MessageType.IMAGE
                    break

        return IncomingMessage(
            platform=self.platform,
            sender_id=channel,  # Reply to channel
            sender_name=user_id,
            message_type=message_type,
            text=text if text else None,
            media_url=media_url,
            raw_payload=payload,
        )

    async def download_media(self, media_url: str) -> bytes | None:
        """Download media from Slack (requires auth)."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                media_url,
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=60,
            )
            if response.status_code == 200:
                return response.content
        return None
