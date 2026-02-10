"""Messaging bridges for Guide.

Workers can interact with Guide through:
- SMS (via Twilio)
- WhatsApp (via Twilio)
- Telegram
"""

from guide.bridges.base import MessageBridge, IncomingMessage, OutgoingMessage
from guide.bridges.twilio import TwilioBridge
from guide.bridges.telegram import TelegramBridge
from guide.bridges.webhook import WebhookHandler

__all__ = [
    "MessageBridge",
    "IncomingMessage",
    "OutgoingMessage",
    "TwilioBridge",
    "TelegramBridge",
    "WebhookHandler",
]
