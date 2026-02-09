"""Messaging bridges for Guide.

These bridges allow workers to interact with Guide through their
preferred messaging platform:
- SMS (via Twilio)
- WhatsApp (via Twilio or Meta)
- Telegram
- Slack
- Discord
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
