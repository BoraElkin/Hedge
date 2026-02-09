"""Twilio bridge for SMS and WhatsApp messaging."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from guide.bridges.base import (
    IncomingMessage,
    MessageBridge,
    MessageType,
    OutgoingMessage,
)


@dataclass
class TwilioConfig:
    """Twilio configuration."""

    account_sid: str
    auth_token: str
    phone_number: str  # Your Twilio phone number
    whatsapp_number: str | None = None  # Your WhatsApp-enabled number


class TwilioBridge(MessageBridge):
    """Bridge for Twilio SMS and WhatsApp.

    Handles:
    - Incoming SMS/WhatsApp messages (via webhook)
    - Outgoing SMS/WhatsApp messages
    - MMS (images) for SMS
    - Media messages for WhatsApp
    """

    platform = "twilio"

    def __init__(self, config: TwilioConfig) -> None:
        self._config = config
        self._base_url = f"https://api.twilio.com/2010-04-01/Accounts/{config.account_sid}"
        self._auth = (config.account_sid, config.auth_token)

    async def send_message(self, message: OutgoingMessage) -> bool:
        """Send a message via Twilio."""
        # Determine if WhatsApp or SMS based on recipient format
        is_whatsapp = message.recipient_id.startswith("whatsapp:")

        from_number = (
            f"whatsapp:{self._config.whatsapp_number}"
            if is_whatsapp
            else self._config.phone_number
        )

        data = {
            "From": from_number,
            "To": message.recipient_id,
        }

        if message.text:
            data["Body"] = message.text

        if message.media_url:
            data["MediaUrl"] = message.media_url

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base_url}/Messages.json",
                auth=self._auth,
                data=data,
                timeout=30,
            )
            return response.status_code == 201

    async def send_text(self, recipient_id: str, text: str) -> bool:
        """Send a text message."""
        return await self.send_message(OutgoingMessage(
            recipient_id=recipient_id,
            text=text,
        ))

    async def send_image(
        self,
        recipient_id: str,
        image_url: str | None = None,
        image_data: bytes | None = None,
        caption: str | None = None,
    ) -> bool:
        """Send an image.

        Note: For image_data, you'd need to host it somewhere first.
        Twilio requires a publicly accessible URL.
        """
        if not image_url:
            # Would need to upload image_data somewhere and get URL
            # For now, just send caption as text
            if caption:
                return await self.send_text(recipient_id, caption)
            return False

        return await self.send_message(OutgoingMessage(
            recipient_id=recipient_id,
            text=caption,
            media_url=image_url,
        ))

    def parse_webhook(self, payload: dict[str, Any]) -> IncomingMessage | None:
        """Parse Twilio webhook payload.

        Twilio sends form data, which FastAPI can parse into a dict.
        """
        sender = payload.get("From", "")
        body = payload.get("Body", "")

        # Check for media
        num_media = int(payload.get("NumMedia", 0))
        media_url = None
        message_type = MessageType.TEXT

        if num_media > 0:
            media_url = payload.get("MediaUrl0")
            media_content_type = payload.get("MediaContentType0", "")

            if "image" in media_content_type:
                message_type = MessageType.IMAGE
            elif "audio" in media_content_type:
                message_type = MessageType.AUDIO

        # Determine platform (SMS vs WhatsApp)
        platform = "whatsapp" if sender.startswith("whatsapp:") else "sms"

        return IncomingMessage(
            platform=platform,
            sender_id=sender,
            sender_name=payload.get("ProfileName"),  # WhatsApp only
            message_type=message_type,
            text=body if body else None,
            media_url=media_url,
            raw_payload=payload,
        )


class SMSBridge(TwilioBridge):
    """Convenience class specifically for SMS."""

    platform = "sms"

    async def send_text(self, recipient_id: str, text: str) -> bool:
        """Send SMS. Ensures recipient doesn't have whatsapp: prefix."""
        if recipient_id.startswith("whatsapp:"):
            recipient_id = recipient_id.replace("whatsapp:", "")
        return await super().send_text(recipient_id, text)


class WhatsAppBridge(TwilioBridge):
    """Convenience class specifically for WhatsApp."""

    platform = "whatsapp"

    async def send_text(self, recipient_id: str, text: str) -> bool:
        """Send WhatsApp message. Ensures recipient has whatsapp: prefix."""
        if not recipient_id.startswith("whatsapp:"):
            recipient_id = f"whatsapp:{recipient_id}"
        return await super().send_text(recipient_id, text)

    async def send_template(
        self,
        recipient_id: str,
        template_name: str,
        template_params: list[str] | None = None,
    ) -> bool:
        """Send a WhatsApp template message.

        Templates must be pre-approved by WhatsApp.
        Used for initiating conversations (WhatsApp requires this).
        """
        if not recipient_id.startswith("whatsapp:"):
            recipient_id = f"whatsapp:{recipient_id}"

        # Build content SID for template
        # Note: This is simplified - real implementation needs template SID
        data = {
            "From": f"whatsapp:{self._config.whatsapp_number}",
            "To": recipient_id,
            "ContentSid": template_name,
        }

        if template_params:
            data["ContentVariables"] = str(dict(enumerate(template_params, 1)))

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base_url}/Messages.json",
                auth=self._auth,
                data=data,
                timeout=30,
            )
            return response.status_code == 201
