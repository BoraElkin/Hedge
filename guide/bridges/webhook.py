"""Webhook handlers for messaging bridges.

Integrates with FastAPI to handle incoming webhooks from Twilio and Telegram.
"""

from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, Request, Response, Form
from fastapi.responses import PlainTextResponse

from guide.bridges.base import IncomingMessage, MessageRouter, OutgoingMessage
from guide.core.guide import AIGuide
from guide.core.session import SessionManager


router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Global instances (initialized in setup)
_message_router: MessageRouter | None = None
_session_manager: SessionManager | None = None
_guide: AIGuide | None = None


def setup_webhooks(
    message_router: MessageRouter,
    session_manager: SessionManager,
    guide: AIGuide,
) -> None:
    """Initialize webhook handlers with required dependencies."""
    global _message_router, _session_manager, _guide
    _message_router = message_router
    _session_manager = session_manager
    _guide = guide

    # Set up the message handler
    message_router.set_handler(_handle_message)


def _handle_message(incoming: IncomingMessage) -> OutgoingMessage | None:
    """Handle an incoming message and generate a response."""
    if not _session_manager or not _guide:
        return None

    # Get or create session for this user
    user_key = f"{incoming.platform}:{incoming.sender_id}"
    session_id = _message_router.get_user_session(user_key) if _message_router else None

    if session_id:
        session = _session_manager.get_session(session_id)
    else:
        session = None

    # Handle special commands
    text = (incoming.text or "").strip().lower()

    if text in ("start", "/start", "hello", "hi"):
        # Create new session
        session = _session_manager.create_session(trade="general")
        if _message_router:
            _message_router.set_user_session(user_key, session.id)

        return OutgoingMessage(
            recipient_id=incoming.sender_id,
            text=(
                "Hi! I'm your AI work guide. I can help you with:\n\n"
                "- HVAC repairs\n"
                "- Plumbing fixes\n"
                "- Electrical work\n"
                "- General repairs\n\n"
                "Tell me what you're trying to do, or send a photo of what you're looking at."
            ),
        )

    if text in ("help", "/help"):
        return OutgoingMessage(
            recipient_id=incoming.sender_id,
            text=(
                "Commands:\n\n"
                "- Send a photo - I'll analyze it and guide you\n"
                "- Type your question - I'll help you out\n"
                "- Say 'next' - Move to next step\n"
                "- Say 'repeat' - Repeat current instruction\n"
                "- Say 'help' - Get more details on current step\n"
                "- Say 'stop' - End current session\n\n"
                "Just tell me what you're working on to get started."
            ),
        )

    if text in ("stop", "/stop", "end", "done", "quit"):
        if session:
            _session_manager.delete_session(session.id)
            if _message_router:
                _message_router.set_user_session(user_key, "")

        return OutgoingMessage(
            recipient_id=incoming.sender_id,
            text="Session ended. Stay safe!\n\nSay 'start' to begin a new session.",
        )

    # Create session if needed
    if not session:
        session = _session_manager.create_session(trade="general")
        if _message_router:
            _message_router.set_user_session(user_key, session.id)

    # Process based on message type
    if incoming.media_data:
        # Image message - analyze it
        response = _guide.process_image(
            session=session,
            image_data=incoming.media_data,
            user_message=incoming.text,
        )
    elif incoming.text:
        # Text message
        # Check if this looks like starting a new task
        if not session.task_description and len(incoming.text) > 10:
            response = _guide.start_task(
                session=session,
                task_description=incoming.text,
            )
        else:
            response = _guide.process_message(
                session=session,
                message=incoming.text,
            )
    else:
        return OutgoingMessage(
            recipient_id=incoming.sender_id,
            text="I didn't understand that. Send me a photo or tell me what you're working on.",
        )

    # Build response message
    reply_text = response.message

    # Add step indicator if in procedure
    if response.current_step and response.total_steps:
        reply_text = f"Step {response.current_step}/{response.total_steps}\n\n{reply_text}"

    # Add warnings
    if response.warnings:
        warning_text = "\n".join(f"WARNING: {w}" for w in response.warnings)
        reply_text = f"{warning_text}\n\n{reply_text}"

    return OutgoingMessage(
        recipient_id=incoming.sender_id,
        text=reply_text,
    )


# --- Webhook endpoints ---


@router.post("/twilio")
async def twilio_webhook(request: Request):
    """Handle Twilio SMS/WhatsApp webhooks."""
    if not _message_router:
        return PlainTextResponse("Not configured", status_code=503)

    # Twilio sends form data
    form = await request.form()
    payload = dict(form)

    await _message_router.handle_incoming("twilio", payload)

    # Twilio expects empty response or TwiML
    return PlainTextResponse("")


@router.post("/telegram")
async def telegram_webhook(request: Request):
    """Handle Telegram bot webhooks."""
    if not _message_router:
        return Response(status_code=503)

    payload = await request.json()
    await _message_router.handle_incoming("telegram", payload)

    return Response(status_code=200)


class WebhookHandler:
    """Convenience class for setting up webhook handling."""

    def __init__(
        self,
        session_manager: SessionManager,
        guide: AIGuide,
    ) -> None:
        self.message_router = MessageRouter()
        self.session_manager = session_manager
        self.guide = guide

    def setup(self) -> APIRouter:
        """Set up webhooks and return the router."""
        setup_webhooks(self.message_router, self.session_manager, self.guide)
        return router

    def add_twilio(
        self,
        account_sid: str,
        auth_token: str,
        phone_number: str,
        whatsapp_number: str | None = None,
    ) -> None:
        """Add Twilio SMS/WhatsApp bridge."""
        from guide.bridges.twilio import TwilioBridge, TwilioConfig

        config = TwilioConfig(
            account_sid=account_sid,
            auth_token=auth_token,
            phone_number=phone_number,
            whatsapp_number=whatsapp_number,
        )
        bridge = TwilioBridge(config)
        self.message_router.register_bridge(bridge)

    def add_telegram(self, bot_token: str) -> None:
        """Add Telegram bridge."""
        from guide.bridges.telegram import TelegramBridge

        bridge = TelegramBridge(bot_token)
        self.message_router.register_bridge(bridge)
