"""Session management routes."""

from __future__ import annotations

import os
import json
from datetime import datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from supabase import create_client, Client
from livekit import api as livekit_api

from .auth import get_current_user, get_supabase
from .usage import check_can_start_session

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
