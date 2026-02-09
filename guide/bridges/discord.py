"""Discord bridge for bot messaging."""

from __future__ import annotations

from typing import Any

import httpx

from guide.bridges.base import (
    IncomingMessage,
    MessageBridge,
    MessageType,
    OutgoingMessage,
)


class DiscordBridge(MessageBridge):
    """Bridge for Discord Bot API.

    Handles:
    - Incoming messages via Gateway events (webhook)
    - Outgoing messages via REST API
    - File uploads for images
    """

    platform = "discord"

    def __init__(self, bot_token: str, application_id: str | None = None) -> None:
        self._token = bot_token
        self._application_id = application_id
        self._base_url = "https://discord.com/api/v10"

    async def send_message(self, message: OutgoingMessage) -> bool:
        """Send a message via Discord."""
        if message.media_data:
            return await self._send_with_file(
                message.recipient_id,
                message.media_data,
                message.text,
            )
        elif message.text:
            return await self.send_text(message.recipient_id, message.text)
        return False

    async def send_text(self, recipient_id: str, text: str) -> bool:
        """Send a text message to a channel."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base_url}/channels/{recipient_id}/messages",
                headers={"Authorization": f"Bot {self._token}"},
                json={"content": text},
                timeout=30,
            )
            return response.status_code == 200

    async def send_image(
        self,
        recipient_id: str,
        image_url: str | None = None,
        image_data: bytes | None = None,
        caption: str | None = None,
    ) -> bool:
        """Send an image to a channel."""
        if image_data:
            return await self._send_with_file(recipient_id, image_data, caption)
        elif image_url:
            # Discord can embed URLs directly
            content = caption or ""
            if image_url:
                content += f"\n{image_url}" if content else image_url
            return await self.send_text(recipient_id, content)
        return False

    async def _send_with_file(
        self,
        channel_id: str,
        file_data: bytes,
        content: str | None = None,
    ) -> bool:
        """Send a message with a file attachment."""
        async with httpx.AsyncClient() as client:
            files = {"file": ("image.jpg", file_data, "image/jpeg")}
            data = {}
            if content:
                data["content"] = content

            response = await client.post(
                f"{self._base_url}/channels/{channel_id}/messages",
                headers={"Authorization": f"Bot {self._token}"},
                data=data,
                files=files,
                timeout=60,
            )
            return response.status_code == 200

    def parse_webhook(self, payload: dict[str, Any]) -> IncomingMessage | None:
        """Parse Discord interaction/gateway event payload.

        Discord interactions come in different types:
        - type 1: PING (handled separately)
        - type 2: APPLICATION_COMMAND
        - type 3: MESSAGE_COMPONENT
        - type 4: APPLICATION_COMMAND_AUTOCOMPLETE
        - type 5: MODAL_SUBMIT

        For message-based interactions, we also support gateway MESSAGE_CREATE events.
        """
        # Handle interaction types
        interaction_type = payload.get("type")

        if interaction_type == 1:
            # PING - handled at webhook level
            return None

        # Check if this is a gateway MESSAGE_CREATE event
        if payload.get("t") == "MESSAGE_CREATE":
            return self._parse_message_create(payload.get("d", {}))

        # Handle slash commands and interactions
        if interaction_type in (2, 3, 5):
            return self._parse_interaction(payload)

        return None

    def _parse_message_create(self, data: dict[str, Any]) -> IncomingMessage | None:
        """Parse a MESSAGE_CREATE gateway event."""
        # Ignore bot messages
        author = data.get("author", {})
        if author.get("bot"):
            return None

        channel_id = data.get("channel_id", "")
        content = data.get("content", "")

        # Check for attachments
        attachments = data.get("attachments", [])
        media_url = None
        message_type = MessageType.TEXT

        for att in attachments:
            if att.get("content_type", "").startswith("image/"):
                media_url = att.get("url")
                message_type = MessageType.IMAGE
                break

        return IncomingMessage(
            platform=self.platform,
            sender_id=channel_id,
            sender_name=author.get("username"),
            message_type=message_type,
            text=content if content else None,
            media_url=media_url,
            raw_payload=data,
        )

    def _parse_interaction(self, payload: dict[str, Any]) -> IncomingMessage | None:
        """Parse a Discord interaction (slash command, button, etc.)."""
        channel_id = payload.get("channel_id", "")
        user = payload.get("user") or payload.get("member", {}).get("user", {})

        # Get the interaction data
        data = payload.get("data", {})

        # For slash commands, the command name and options become the message
        if payload.get("type") == 2:  # APPLICATION_COMMAND
            command = data.get("name", "")
            options = data.get("options", [])

            # Build text from command and options
            text_parts = [f"/{command}"]
            for opt in options:
                text_parts.append(f"{opt.get('name')}={opt.get('value')}")
            text = " ".join(text_parts)
        else:
            # For other interactions, use custom_id
            text = data.get("custom_id", "")

        return IncomingMessage(
            platform=self.platform,
            sender_id=channel_id,
            sender_name=user.get("username"),
            message_type=MessageType.TEXT,
            text=text,
            raw_payload=payload,
            metadata={"interaction_id": payload.get("id"), "interaction_token": payload.get("token")},
        )

    async def respond_to_interaction(
        self,
        interaction_id: str,
        interaction_token: str,
        content: str,
    ) -> bool:
        """Respond to a Discord interaction."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base_url}/interactions/{interaction_id}/{interaction_token}/callback",
                json={
                    "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
                    "data": {"content": content},
                },
                timeout=30,
            )
            return response.status_code in (200, 204)
