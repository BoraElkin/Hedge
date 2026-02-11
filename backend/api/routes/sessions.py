"""Session management routes."""

from __future__ import annotations

import os
import json
from datetime import datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Header, UploadFile
from pydantic import BaseModel
from supabase import create_client, Client
from livekit import api as livekit_api

from .auth import get_current_user, get_supabase
from .usage import check_can_start_session
from backend.agent.vision import get_vision

router = APIRouter()


class StartSessionRequest(BaseModel):
    task_template: str = "general"
    custom_context: str | None = None


class StartSessionResponse(BaseModel):
    session_id: str
    livekit_url: str
    livekit_token: str
    room_name: str


class SessionInfo(BaseModel):
    id: str
    task_template: str
    custom_context: str | None
    duration_seconds: int | None
    rating: int | None
    started_at: str
    ended_at: str | None


class EndSessionRequest(BaseModel):
    rating: int | None = None  # 1-5 post-session rating


class ChatSessionResponse(BaseModel):
    """Response for chat-mode session (no LiveKit)."""

    session_id: str
    task_template: str
    custom_context: str | None


class GuidanceResponse(BaseModel):
    """AI guidance response."""

    message: str
    hazards: list[str] = []
    suggested_action: str | None = None


class MessageRequest(BaseModel):
    """Text message request."""

    message: str


def get_livekit_api() -> livekit_api.LiveKitAPI:
    """Get LiveKit API client."""
    url = os.getenv("LIVEKIT_URL", "wss://your-app.livekit.cloud")
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not api_key or not api_secret:
        raise HTTPException(status_code=500, detail="LiveKit not configured")

    return livekit_api.LiveKitAPI(url, api_key, api_secret)


@router.post("/start", response_model=StartSessionResponse)
async def start_session(
    request: StartSessionRequest,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Start a new guidance session.

    1. Check usage limits (free tier: 3 sessions/week, 10 min each)
    2. Create LiveKit room
    3. Generate access token for the technician
    4. Store session in database
    5. Return connection details
    """
    user_id = current_user["id"]

    # Check if user can start a session
    can_start, reason = await check_can_start_session(user_id, supabase)
    if not can_start:
        raise HTTPException(status_code=403, detail=reason)

    # Generate unique room name
    session_id = str(uuid4())
    room_name = f"hvac-{session_id[:8]}"

    # Create room metadata with task context
    room_metadata = json.dumps({
        "task_template": request.task_template,
        "custom_context": request.custom_context,
        "user_id": user_id,
    })

    # Create LiveKit room
    lk = get_livekit_api()
    try:
        await lk.room.create_room(
            livekit_api.CreateRoomRequest(
                name=room_name,
                empty_timeout=60 * 15,  # 15 min timeout if empty
                max_participants=2,  # Just technician + agent
                metadata=room_metadata,
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not create room: {e}")

    # Generate access token for the technician
    token = livekit_api.AccessToken(
        os.getenv("LIVEKIT_API_KEY"),
        os.getenv("LIVEKIT_API_SECRET"),
    )
    token.with_identity(user_id)
    token.with_name(current_user.get("email", "Technician"))
    token.with_grants(
        livekit_api.VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
        )
    )
    jwt_token = token.to_jwt()

    # Store session in database
    supabase.table("sessions").insert({
        "id": session_id,
        "user_id": user_id,
        "task_template": request.task_template,
        "custom_context": request.custom_context,
        "room_name": room_name,
        "started_at": datetime.utcnow().isoformat(),
    }).execute()

    return StartSessionResponse(
        session_id=session_id,
        livekit_url=os.getenv("LIVEKIT_URL", "wss://your-app.livekit.cloud"),
        livekit_token=jwt_token,
        room_name=room_name,
    )


@router.post("/{session_id}/end")
async def end_session(
    session_id: str,
    request: EndSessionRequest,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """End a guidance session.

    1. Calculate duration
    2. Store rating if provided
    3. Update session record
    4. Close LiveKit room
    """
    user_id = current_user["id"]

    # Get the session
    result = supabase.table("sessions").select("*").eq("id", session_id).eq("user_id", user_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Session not found")

    session = result.data[0]

    if session.get("ended_at"):
        raise HTTPException(status_code=400, detail="Session already ended")

    # Calculate duration
    started_at = datetime.fromisoformat(session["started_at"].replace("Z", "+00:00"))
    ended_at = datetime.utcnow()
    duration_seconds = int((ended_at - started_at).total_seconds())

    # Update session
    supabase.table("sessions").update({
        "ended_at": ended_at.isoformat(),
        "duration_seconds": duration_seconds,
        "rating": request.rating,
    }).eq("id", session_id).execute()

    # Close LiveKit room
    try:
        lk = get_livekit_api()
        await lk.room.delete_room(livekit_api.DeleteRoomRequest(room=session["room_name"]))
    except Exception:
        pass  # Room might already be closed

    return {
        "session_id": session_id,
        "duration_seconds": duration_seconds,
        "status": "ended",
    }


@router.get("/history", response_model=list[SessionInfo])
async def get_session_history(
    limit: int = 20,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Get session history for the current user."""
    user_id = current_user["id"]

    result = (
        supabase.table("sessions")
        .select("*")
        .eq("user_id", user_id)
        .order("started_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )

    return [
        SessionInfo(
            id=s["id"],
            task_template=s["task_template"],
            custom_context=s.get("custom_context"),
            duration_seconds=s.get("duration_seconds"),
            rating=s.get("rating"),
            started_at=s["started_at"],
            ended_at=s.get("ended_at"),
        )
        for s in result.data
    ]


@router.get("/{session_id}", response_model=SessionInfo)
async def get_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Get details of a specific session."""
    user_id = current_user["id"]

    result = supabase.table("sessions").select("*").eq("id", session_id).eq("user_id", user_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Session not found")

    s = result.data[0]
    return SessionInfo(
        id=s["id"],
        task_template=s["task_template"],
        custom_context=s.get("custom_context"),
        duration_seconds=s.get("duration_seconds"),
        rating=s.get("rating"),
        started_at=s["started_at"],
        ended_at=s.get("ended_at"),
    )


# =============================================================================
# Chat Mode Endpoints (Image Upload + Text Messages)
# =============================================================================


@router.post("/chat/start", response_model=ChatSessionResponse)
async def start_chat_session(
    request: StartSessionRequest,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Start a chat-mode session (image upload, no video streaming).

    Use this for lower-bandwidth situations or quick questions with photos.
    For real-time video guidance, use /sessions/start instead.
    """
    user_id = current_user["id"]

    # Check if user can start a session
    can_start, reason = await check_can_start_session(user_id, supabase)
    if not can_start:
        raise HTTPException(status_code=403, detail=reason)

    # Generate session ID
    session_id = str(uuid4())

    # Store session in database (no LiveKit room)
    supabase.table("sessions").insert({
        "id": session_id,
        "user_id": user_id,
        "task_template": request.task_template,
        "custom_context": request.custom_context,
        "room_name": None,  # No LiveKit room for chat mode
        "started_at": datetime.utcnow().isoformat(),
    }).execute()

    return ChatSessionResponse(
        session_id=session_id,
        task_template=request.task_template,
        custom_context=request.custom_context,
    )


@router.post("/{session_id}/image", response_model=GuidanceResponse)
async def send_image(
    session_id: str,
    image: UploadFile = File(...),
    message: str | None = Form(None),
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Send an image for AI analysis (chat mode).

    Upload a photo of what you're working on. The AI will analyze it
    and provide guidance based on your task context.
    """
    user_id = current_user["id"]

    # Get the session
    result = supabase.table("sessions").select("*").eq("id", session_id).eq("user_id", user_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Session not found")

    session = result.data[0]

    if session.get("ended_at"):
        raise HTTPException(status_code=400, detail="Session has ended")

    # Read image data
    image_data = await image.read()

    if not image_data:
        raise HTTPException(status_code=400, detail="No image data received")

    # Get task context
    task_context = session.get("custom_context") or session.get("task_template", "general")
    task_template = session.get("task_template", "general")

    # Analyze image with Gemini
    try:
        vision = get_vision()
        response = vision.analyze(
            image_data=image_data,
            task_context=task_context,
            user_message=message,
            task_template=task_template,
        )

        return GuidanceResponse(
            message=response.message,
            hazards=response.hazards,
            suggested_action=response.suggested_action,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vision analysis failed: {str(e)}")


@router.post("/{session_id}/message", response_model=GuidanceResponse)
async def send_message(
    session_id: str,
    request: MessageRequest,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Send a text message (chat mode).

    Ask a question or provide context. For best results, include
    an image with your message using the /image endpoint.
    """
    user_id = current_user["id"]

    # Get the session
    result = supabase.table("sessions").select("*").eq("id", session_id).eq("user_id", user_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Session not found")

    session = result.data[0]

    if session.get("ended_at"):
        raise HTTPException(status_code=400, detail="Session has ended")

    # Get task context
    task_context = session.get("custom_context") or session.get("task_template", "general")
    task_template = session.get("task_template", "general")

    # For text-only messages, use Gemini text model
    try:
        from google import genai
        from google.genai import types

        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="Google API not configured")

        client = genai.Client(api_key=api_key)

        # Build prompt with context
        from backend.agent.prompts import get_system_prompt

        system_prompt = get_system_prompt(task_template, task_context)

        prompt = f"""{system_prompt}

The technician asks: {request.message}

Respond helpfully and concisely. If you need to see something to give good advice, ask them to send a photo."""

        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=1024,
            ),
        )

        return GuidanceResponse(
            message=response.text,
            hazards=[],
            suggested_action=None,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Message processing failed: {str(e)}")
