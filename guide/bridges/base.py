"""Base classes for messaging bridges."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable


class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    LOCATION = "location"


@dataclass
class IncomingMessage:
    """A message received from a user."""

    platform: str  # "sms", "whatsapp", "telegram", etc.
    sender_id: str  # Platform-specific user ID
    sender_name: str | None = None
    message_type: MessageType = MessageType.TEXT
    text: str | None = None
    media_url: str | None = None
    media_data: bytes | None = None
    location: tuple[float, float] | None = None  # (lat, lon)
    timestamp: datetime = field(default_factory=datetime.now)
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class OutgoingMessage:
    """A message to send to a user."""

    recipient_id: str
    text: str | None = None
    media_url: str | None = None
    media_data: bytes | None = None
    media_type: str = "image/jpeg"
    buttons: list[dict[str, str]] | None = None  # Quick reply buttons


class MessageBridge(ABC):
    """Abstract base class for messaging platform bridges.

    Implementations handle:
    - Receiving messages from the platform (webhooks)
    - Sending messages to users
    - Media handling (images, audio)
    """

    platform: str

    @abstractmethod
    async def send_message(self, message: OutgoingMessage) -> bool:
        """Send a message to a user. Returns True if successful."""

    @abstractmethod
    async def send_text(self, recipient_id: str, text: str) -> bool:
        """Send a simple text message."""

    @abstractmethod
    async def send_image(
        self,
        recipient_id: str,
        image_url: str | None = None,
        image_data: bytes | None = None,
        caption: str | None = None,
    ) -> bool:
        """Send an image with optional caption."""

    @abstractmethod
    def parse_webhook(self, payload: dict[str, Any]) -> IncomingMessage | None:
        """Parse an incoming webhook payload into an IncomingMessage."""

    async def download_media(self, media_url: str) -> bytes | None:
        """Download media from a URL. Default implementation uses httpx."""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(media_url, timeout=30)
                response.raise_for_status()
                return response.content
        except Exception:
            return None


class MessageRouter:
    """Routes incoming messages to Guide sessions and sends responses.

    This is the glue between messaging platforms and the Guide AI.
    """

    def __init__(self) -> None:
        self._bridges: dict[str, MessageBridge] = {}
        self._user_sessions: dict[str, str] = {}  # user_id -> session_id
        self._message_handler: Callable[[IncomingMessage], OutgoingMessage | None] | None = None

    def register_bridge(self, bridge: MessageBridge) -> None:
        """Register a messaging bridge."""
        self._bridges[bridge.platform] = bridge

    def set_handler(
        self,
        handler: Callable[[IncomingMessage], OutgoingMessage | None],
    ) -> None:
        """Set the message handler function."""
        self._message_handler = handler

    async def handle_incoming(self, platform: str, payload: dict[str, Any]) -> bool:
        """Handle an incoming webhook from a platform."""
        bridge = self._bridges.get(platform)
        if not bridge:
            return False

        message = bridge.parse_webhook(payload)
        if not message:
            return False

        # Download media if present
        if message.media_url and not message.media_data:
            message.media_data = await bridge.download_media(message.media_url)

        # Process through handler
        if self._message_handler:
            response = self._message_handler(message)
            if response:
                response.recipient_id = message.sender_id
                await bridge.send_message(response)
                return True

        return False

    def get_user_session(self, user_id: str) -> str | None:
        """Get the session ID for a user."""
        return self._user_sessions.get(user_id)

    def set_user_session(self, user_id: str, session_id: str) -> None:
        """Associate a user with a session."""
        self._user_sessions[user_id] = session_id
