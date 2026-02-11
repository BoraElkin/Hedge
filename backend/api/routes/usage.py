"""Usage tracking routes for free tier limits."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from supabase import Client

from .auth import get_current_user, get_supabase

router = APIRouter()

# Free tier limits
FREE_SESSIONS_PER_WEEK = 3
FREE_SESSION_MAX_MINUTES = 10


class UsageStatus(BaseModel):
    plan: str  # "free", "pro", "team"
    sessions_this_week: int
    sessions_remaining: int | None  # None for unlimited (Pro)
    max_session_minutes: int | None  # None for unlimited (Pro)
    can_start_session: bool
    upgrade_url: str | None


async def check_can_start_session(user_id: str, supabase: Client) -> tuple[bool, str | None]:
    """Check if user can start a new session.

    Returns (can_start, reason_if_not)
    """
    # Get user's plan
    user_result = supabase.table("users").select("plan").eq("id", user_id).execute()

    if not user_result.data:
        return False, "User not found"

    plan = user_result.data[0].get("plan", "free")

    # Pro and team users have unlimited sessions
    if plan in ("pro", "team"):
        return True, None

    # Free tier: check weekly limit
    week_ago = datetime.utcnow() - timedelta(days=7)

    sessions_result = (
        supabase.table("sessions")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .gte("started_at", week_ago.isoformat())
        .execute()
    )

    sessions_this_week = sessions_result.count or 0

    if sessions_this_week >= FREE_SESSIONS_PER_WEEK:
        return False, f"Free tier limit reached ({FREE_SESSIONS_PER_WEEK} sessions/week). Upgrade to Pro for unlimited sessions."

    return True, None


async def get_user_plan(user_id: str, supabase: Client) -> str:
    """Get user's current plan."""
    result = supabase.table("users").select("plan").eq("id", user_id).execute()
    if result.data:
        return result.data[0].get("plan", "free")
    return "free"


@router.get("/status", response_model=UsageStatus)
async def get_usage_status(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Get current usage status for the user."""
    user_id = current_user["id"]
    plan = await get_user_plan(user_id, supabase)

    # Count sessions this week
    week_ago = datetime.utcnow() - timedelta(days=7)
    sessions_result = (
        supabase.table("sessions")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .gte("started_at", week_ago.isoformat())
        .execute()
    )
    sessions_this_week = sessions_result.count or 0

    if plan in ("pro", "team"):
        return UsageStatus(
            plan=plan,
            sessions_this_week=sessions_this_week,
            sessions_remaining=None,  # Unlimited
            max_session_minutes=None,  # Unlimited
            can_start_session=True,
            upgrade_url=None,
        )

    # Free tier
    sessions_remaining = max(0, FREE_SESSIONS_PER_WEEK - sessions_this_week)

    return UsageStatus(
        plan=plan,
        sessions_this_week=sessions_this_week,
        sessions_remaining=sessions_remaining,
        max_session_minutes=FREE_SESSION_MAX_MINUTES,
        can_start_session=sessions_remaining > 0,
        upgrade_url="/billing/upgrade",  # TODO: Stripe checkout URL
    )


@router.get("/history")
async def get_usage_history(
    days: int = 30,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Get usage history for the past N days."""
    user_id = current_user["id"]
    since = datetime.utcnow() - timedelta(days=days)

    result = (
        supabase.table("sessions")
        .select("started_at, duration_seconds, task_template")
        .eq("user_id", user_id)
        .gte("started_at", since.isoformat())
        .order("started_at", desc=True)
        .execute()
    )

    # Aggregate by day
    daily_usage: dict[str, dict] = {}
    for session in result.data:
        date = session["started_at"][:10]  # YYYY-MM-DD
        if date not in daily_usage:
            daily_usage[date] = {"sessions": 0, "total_minutes": 0}
        daily_usage[date]["sessions"] += 1
        if session.get("duration_seconds"):
            daily_usage[date]["total_minutes"] += session["duration_seconds"] / 60

    return {
        "period_days": days,
        "total_sessions": len(result.data),
        "total_minutes": sum(
            (s.get("duration_seconds") or 0) / 60 for s in result.data
        ),
        "daily_breakdown": daily_usage,
    }
