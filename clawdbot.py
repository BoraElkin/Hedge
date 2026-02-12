#!/usr/bin/env python3
"""ClawdBot - AI assistant accessible via WhatsApp/SMS.

Workers text your Twilio number and get real-time AI guidance.
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import Response
import uvicorn

from guide.bridges.twilio import TwilioBridge, TwilioConfig
from guide.bridges.base import IncomingMessage, OutgoingMessage, MessageType
from guide.core.guide import AIGuide
from guide.core.session import SessionManager
from guide.core.knowledge import KnowledgeBase

# Load environment
load_dotenv()

# Initialize components
app = FastAPI(title="ClawdBot")
session_manager = SessionManager()
guide = AIGuide()

# Track user sessions (user_id -> session_id)
user_sessions: dict[str, str] = {}

# Twilio config
twilio_config = TwilioConfig(
    account_sid=os.getenv("TWILIO_ACCOUNT_SID"),
    auth_token=os.getenv("TWILIO_AUTH_TOKEN"),
    phone_number=os.getenv("TWILIO_PHONE_NUMBER"),
    whatsapp_number=os.getenv("TWILIO_WHATSAPP_NUMBER"),
)

twilio_bridge = TwilioBridge(config=twilio_config)


async def handle_message(incoming: IncomingMessage) -> OutgoingMessage:
    """Process incoming message and generate AI response."""

    # Get or create session for this user
    if incoming.sender_id not in user_sessions:
        session = session_manager.create_session(trade="general")
        user_sessions[incoming.sender_id] = session.id
    else:
        session_id = user_sessions[incoming.sender_id]
        session = session_manager.get_session(session_id)

    if not session:
        # Session expired, create new one
        session = session_manager.create_session(trade="general")
        user_sessions[incoming.sender_id] = session.id

    # Handle different message types
    if incoming.message_type == MessageType.TEXT:
        # Check for commands
        text = incoming.text.lower().strip()

        if text in ["help", "start", "hi", "hello"]:
            return OutgoingMessage(
                recipient_id=incoming.sender_id,
                text=(
                    "👋 Hi! I'm ClawdBot, your AI work assistant.\n\n"
                    "I can help you with:\n"
                    "• Send a photo - I'll analyze it and guide you\n"
                    "• Tell me what you're working on\n"
                    "• Ask questions - Get expert advice\n\n"
                    "What are you working on?"
                )
            )

        # Start a task
        response = guide.start_task(
            session=session,
            task_description=incoming.text
        )

        return OutgoingMessage(
            recipient_id=incoming.sender_id,
            text=response.message
        )

    elif incoming.message_type == MessageType.IMAGE:
        # Process image with vision AI
        if not incoming.media_data and incoming.media_url:
            # Download if needed
            incoming.media_data = await twilio_bridge.download_media(incoming.media_url)

        if incoming.media_data:
            response = guide.process_image(
                session=session,
                image_data=incoming.media_data,
                user_message=incoming.text or "What do you see? Any guidance?"
            )

            return OutgoingMessage(
                recipient_id=incoming.sender_id,
                text=response.message
            )

    # Fallback
    return OutgoingMessage(
        recipient_id=incoming.sender_id,
        text="I received your message but couldn't process it. Try sending text or an image."
    )


@app.post("/webhooks/twilio")
async def twilio_webhook(request: Request):
    """Handle incoming Twilio messages (SMS and WhatsApp)."""

    # Parse form data from Twilio
    form_data = await request.form()
    payload = dict(form_data)

    # Parse into IncomingMessage
    incoming = twilio_bridge.parse_webhook(payload)

    if not incoming:
        return Response(content="", status_code=200)

    # Generate AI response
    response = await handle_message(incoming)

    # Send response via Twilio
    await twilio_bridge.send_message(response)

    # Twilio expects 200 OK
    return Response(content="", status_code=200)


@app.get("/")
async def root():
    """Health check."""
    return {
        "service": "ClawdBot",
        "status": "online",
        "description": "AI work assistant via WhatsApp/SMS",
        "webhook": "/webhooks/twilio",
        "phone": twilio_config.phone_number,
        "whatsapp": twilio_config.whatsapp_number or "Not configured"
    }


@app.get("/health")
async def health():
    """Detailed health check."""
    return {
        "status": "healthy",
        "twilio_configured": bool(twilio_config.account_sid),
        "active_sessions": len([s for s in session_manager.list_sessions() if s]),
        "total_users": len(user_sessions),
    }


def main():
    """Start ClawdBot server."""

    print("\n" + "="*60)
    print("  🤖 ClawdBot - AI Work Assistant")
    print("="*60)
    print(f"\n  📱 SMS Number: {twilio_config.phone_number}")
    print(f"  💬 WhatsApp: {twilio_config.whatsapp_number or 'Not configured'}")
    print(f"\n  🌐 Server: http://0.0.0.0:8000")
    print(f"  📍 Webhook: /webhooks/twilio")
    print("\n" + "="*60)
    print("\n  Configure Twilio webhook to point to:")
    print(f"  https://your-domain.com/webhooks/twilio")
    print("\n" + "="*60 + "\n")

    # Run server
    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        log_level="info"
    )


if __name__ == "__main__":
    main()
