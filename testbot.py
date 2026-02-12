#!/usr/bin/env python3
"""Test ClawdBot - Maintains conversation context properly."""

import os
from pathlib import Path
import base64

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn
import anthropic

load_dotenv()

app = FastAPI(title="ClawdBot Test")

# Initialize Claude client
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Store conversation history per user (user_id -> list of messages)
conversations: dict[str, list[dict]] = {}


async def chat(user_id: str, text: str, image_data: bytes | None = None) -> str:
    """Chat with Claude, maintaining full conversation history."""

    # Get or create conversation history
    if user_id not in conversations:
        conversations[user_id] = []

    history = conversations[user_id]

    # Build message content
    content = []

    # Add image first if provided
    if image_data:
        # Detect image format
        media_type = "image/jpeg"  # default
        if image_data.startswith(b'\x89PNG'):
            media_type = "image/png"
        elif image_data.startswith(b'GIF'):
            media_type = "image/gif"
        elif image_data.startswith(b'\xff\xd8\xff'):
            media_type = "image/jpeg"
        elif image_data.startswith(b'WEBP', 8):
            media_type = "image/webp"

        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": base64.b64encode(image_data).decode()
            }
        })

    # Add text
    if text:
        content.append({
            "type": "text",
            "text": text
        })

    # Add user message to history
    history.append({
        "role": "user",
        "content": content if len(content) > 1 or image_data else text
    })

    # Get response from Claude with full conversation context
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system="""You are ClawdBot, an AI assistant that helps with physical work tasks like HVAC, plumbing, electrical work, etc.

When users send you photos:
- Analyze what you see in detail
- Identify any issues or hazards
- Provide step-by-step guidance
- Remember what you've seen in previous messages

When users ask questions:
- Refer back to previous context and images
- Provide clear, actionable advice
- Be safety-conscious
- Walk them through tasks step by step

Always maintain context from the entire conversation.""",
        messages=history
    )

    assistant_message = response.content[0].text

    # Add assistant response to history
    history.append({
        "role": "assistant",
        "content": assistant_message
    })

    # Keep only last 30 messages to avoid context limits
    if len(history) > 30:
        conversations[user_id] = history[-30:]

    return assistant_message


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the chat interface."""
    chat_html = Path("guide/api/chat.html").read_text()
    return HTMLResponse(content=chat_html)


@app.post("/api/chat")
async def chat_endpoint(
    text: str = Form(""),
    sender_id: str = Form("web-test-user"),
    image: UploadFile = File(None)
):
    """Handle chat messages from the web interface."""

    image_data = None
    if image:
        image_data = await image.read()

    # Process message with full context
    response_text = await chat(sender_id, text, image_data)

    return JSONResponse({
        "message": response_text,
        "status": "success"
    })


@app.get("/health")
async def health():
    """Health check."""
    return {
        "status": "healthy",
        "mode": "test",
        "active_users": len(conversations),
        "total_messages": sum(len(msgs) for msgs in conversations.values())
    }


@app.post("/reset")
async def reset_conversation(sender_id: str = Form("web-test-user")):
    """Reset conversation for a user."""
    if sender_id in conversations:
        del conversations[sender_id]
    return {"status": "reset"}


def main():
    """Start test server."""

    print("\n" + "="*60)
    print("  🧪 ClawdBot - Test Environment")
    print("="*60)
    print(f"\n  🌐 Open in browser: http://localhost:8000")
    print(f"\n  ✨ Test all features without Twilio!")
    print(f"  📸 Send photos, ask questions, get AI guidance")
    print(f"  🧠 Full conversation memory maintained")
    print("\n" + "="*60 + "\n")

    # Run server
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )


if __name__ == "__main__":
    main()
