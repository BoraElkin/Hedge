"""Authentication routes using Supabase."""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, EmailStr
from supabase import create_client, Client

router = APIRouter()


def get_supabase() -> Client:
    """Get Supabase client."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_PUBLISHABLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    return create_client(url, key)


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    supabase: Client = Depends(get_supabase),
) -> dict:
    """Validate JWT and return current user."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = authorization.replace("Bearer ", "")

    try:
        # Verify the JWT with Supabase
        user = supabase.auth.get_user(token)
        if not user or not user.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"id": user.user.id, "email": user.user.email}
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")


class SignUpRequest(BaseModel):
    email: EmailStr
    password: str


class SignInRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    user_id: str
    email: str


@router.post("/signup", response_model=AuthResponse)
async def signup(request: SignUpRequest, supabase: Client = Depends(get_supabase)):
    """Create a new user account."""
    try:
        response = supabase.auth.sign_up({
            "email": request.email,
            "password": request.password,
        })

        if not response.user:
            raise HTTPException(status_code=400, detail="Sign up failed")

        # Also create a record in our users table
        supabase.table("users").insert({
            "id": response.user.id,
            "email": response.user.email,
            "plan": "free",
        }).execute()

        return AuthResponse(
            access_token=response.session.access_token if response.session else "",
            refresh_token=response.session.refresh_token if response.session else "",
            user_id=response.user.id,
            email=response.user.email or "",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login", response_model=AuthResponse)
async def login(request: SignInRequest, supabase: Client = Depends(get_supabase)):
    """Sign in with email and password."""
    try:
        response = supabase.auth.sign_in_with_password({
            "email": request.email,
            "password": request.password,
        })

        if not response.user or not response.session:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        return AuthResponse(
            access_token=response.session.access_token,
            refresh_token=response.session.refresh_token,
            user_id=response.user.id,
            email=response.user.email or "",
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/logout")
async def logout(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Sign out the current user."""
    try:
        supabase.auth.sign_out()
        return {"status": "logged out"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current user info."""
    return current_user


@router.post("/refresh")
async def refresh_token(
    refresh_token: str,
    supabase: Client = Depends(get_supabase),
):
    """Refresh the access token."""
    try:
        response = supabase.auth.refresh_session(refresh_token)
        if not response.session:
            raise HTTPException(status_code=401, detail="Could not refresh token")

        return {
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))
