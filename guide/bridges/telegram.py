"""Telegram bridge for bot messaging."""

from __future__ import annotations

from typing import Any

import httpx

from guide.bridges.base import (
    IncomingMessage,
    MessageBridge,
    MessageType,
    OutgoingMessage,
)


class TelegramBridge(MessageBridge):
    """Bridge for Telegram Bot API.

    Handles:
    - Incoming messages (via webhook or polling)
    - Outgoing text and media messages
    - Inline keyboards for quick actions
    """

    platform = "telegram"

    def __init__(self, bot_token: str) -> None:
        self._token = bot_token
        self._base_url = f"https://api.telegram.org/bot{bot_token}"

    async def send_message(self, message: OutgoingMessage) -> bool:
        """Send a message via Telegram."""
        if message.media_url or message.media_data:
            return await self.send_image(
                message.recipient_id,
                image_url=message.media_url,
                caption=message.text,
            )
        elif message.text:
            return await self.send_text(
                message.recipient_id,
                message.text,
                buttons=message.buttons,
            )
        return False

    async def send_text(
        self,
        recipient_id: str,
        text: str,
        buttons: list[dict[str, str]] | None = None,
    ) -> bool:
        """Send a text message with optional inline keyboard."""
        data: dict[str, Any] = {
            "chat_id": recipient_id,
            "text": text,
            "parse_mode": "Markdown",
        }

        # Add inline keyboard if buttons provided
        if buttons:
            keyboard = {
                "inline_keyboard": [
                    [{"text": b.get("text", ""), "callback_data": b.get("data", "")}]
                    for b in buttons
                ]
            }
            data["reply_markup"] = keyboard

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base_url}/sendMessage",
                json=data,
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
        """Send a photo."""
        async with httpx.AsyncClient() as client:
            if image_url:
                response = await client.post(
                    f"{self._base_url}/sendPhoto",
                    json={
                        "chat_id": recipient_id,
                        "photo": image_url,
                        "caption": caption,
                    },
                    timeout=30,
                )
            elif image_data:
                response = await client.post(
                    f"{self._base_url}/sendPhoto",
                    data={"chat_id": recipient_id, "caption": caption or ""},
                    files={"photo": ("image.jpg", image_data, "image/jpeg")},
                    timeout=30,
                )
            else:
                return False

            return response.status_code == 200

    async def send_voice(
        self,
        recipient_id: str,
        audio_data: bytes,
        caption: str | None = None,
    ) -> bool:
        """Send a voice message (for TTS responses)."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base_url}/sendVoice",
                data={"chat_id": recipient_id, "caption": caption or ""},
                files={"voice": ("voice.ogg", audio_data, "audio/ogg")},
                timeout=30,
            )
            return response.status_code == 200

    async def send_action(self, recipient_id: str, action: str = "typing") -> bool:
        """Send a chat action (typing indicator, etc.)."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base_url}/sendChatAction",
                json={"chat_id": recipient_id, "action": action},
                timeout=10,
            )
            return response.status_code == 200

    def parse_webhook(self, payload: dict[str, Any]) -> IncomingMessage | None:
        """Parse Telegram webhook update."""
        # Handle regular messages
        message = payload.get("message") or payload.get("edited_message")

        # Handle callback queries (button presses)
        callback = payload.get("callback_query")
        if callback:
            return IncomingMessage(
                platform=self.platform,
                sender_id=str(callback["from"]["id"]),
                sender_name=callback["from"].get("first_name"),
                message_type=MessageType.TEXT,
                text=callback.get("data"),  # Button callback data
                raw_payload=payload,
            )

        if not message:
            return None

        sender = message.get("from", {})
        chat = message.get("chat", {})

        # Determine message type
        message_type = MessageType.TEXT
        text = message.get("text")
        media_url = None

        if "photo" in message:
            message_type = MessageType.IMAGE
            # Get largest photo
            photos = message["photo"]
            if photos:
                file_id = photos[-1]["file_id"]
                media_url = f"tg://file/{file_id}"  # Will need to fetch actual URL

        elif "voice" in message:
            message_type = MessageType.AUDIO
            media_url = f"tg://file/{message['voice']['file_id']}"

        elif "audio" in message:
            message_type = MessageType.AUDIO
            media_url = f"tg://file/{message['audio']['file_id']}"

        # Handle location
        location = None
        if "location" in message:
            loc = message["location"]
            location = (loc["latitude"], loc["longitude"])
            message_type = MessageType.LOCATION

        # Caption for media messages
        if not text and "caption" in message:
            text = message["caption"]

        return IncomingMessage(
            platform=self.platform,
            sender_id=str(chat.get("id")),
            sender_name=sender.get("first_name"),
            message_type=message_type,
            text=text,
            media_url=media_url,
            location=location,
            raw_payload=payload,
        )

    async def download_media(self, media_url: str) -> bytes | None:
        """Download media from Telegram.

        Telegram requires fetching file path first, then downloading.
        """
        if not media_url.startswith("tg://file/"):
            return await super().download_media(media_url)

        file_id = media_url.replace("tg://file/", "")

        async with httpx.AsyncClient() as client:
            # Get file path
            response = await client.get(
                f"{self._base_url}/getFile",
                params={"file_id": file_id},
                timeout=30,
            )

            if response.status_code != 200:
                return None

            data = response.json()
            if not data.get("ok"):
                return None

            file_path = data["result"]["file_path"]

            # Download file
            download_url = f"https://api.telegram.org/file/bot{self._token}/{file_path}"
            file_response = await client.get(download_url, timeout=60)

            if file_response.status_code == 200:
                return file_response.content

        return None

    async def set_webhook(self, webhook_url: str) -> bool:
        """Set the webhook URL for receiving updates."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base_url}/setWebhook",
                json={"url": webhook_url},
                timeout=30,
            )
            return response.status_code == 200

    async def delete_webhook(self) -> bool:
        """Remove the webhook (use polling instead)."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base_url}/deleteWebhook",
                timeout=30,
            )
            return response.status_code == 200
