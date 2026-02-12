#!/usr/bin/env python3
"""Verify HVAC Copilot setup and test connections.

Run this after setting up your .env file to verify everything works.

Usage:
    python scripts/verify_setup.py
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()


def check_env_var(name: str, required: bool = True) -> tuple[bool, str]:
    """Check if an environment variable is set."""
    value = os.getenv(name)
    if value and value != f"your-{name.lower().replace('_', '-')}":
        masked = value[:8] + "..." if len(value) > 12 else "***"
        return True, masked
    return False, "NOT SET" if required else "not set (optional)"


def test_google_api() -> tuple[bool, str]:
    """Test Google/Gemini API connection."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key or api_key.startswith("your-"):
        return False, "API key not configured"

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents="Say 'Hello HVAC' in exactly 2 words",
            config=types.GenerateContentConfig(max_output_tokens=10),
        )
        return True, f"OK - {response.text.strip()}"
    except Exception as e:
        return False, f"Error: {str(e)[:50]}"


def test_supabase() -> tuple[bool, str]:
    """Test Supabase connection."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")

    if not url or url.startswith("https://your-"):
        return False, "URL not configured"
    if not key or key.startswith("your-"):
        return False, "Key not configured"

    try:
        from supabase import create_client

        client = create_client(url, key)
        # Try a simple query (will fail if tables don't exist, but connection works)
        result = client.table("users").select("id").limit(1).execute()
        return True, f"OK - Connected"
    except Exception as e:
        error = str(e)
        if "relation" in error and "does not exist" in error:
            return True, "Connected (run migrations)"
        return False, f"Error: {error[:50]}"


def test_livekit() -> tuple[bool, str]:
    """Test LiveKit configuration."""
    url = os.getenv("LIVEKIT_URL")
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not url or url.startswith("wss://your-"):
        return False, "URL not configured"
    if not api_key or api_key.startswith("your-"):
        return False, "API key not configured"
    if not api_secret or api_secret.startswith("your-"):
        return False, "API secret not configured"

    try:
        from livekit import api as livekit_api

        # Just verify we can create a token (doesn't require network)
        token = livekit_api.AccessToken(api_key, api_secret)
        token.with_identity("test-user")
        token.with_grants(livekit_api.VideoGrants(room_join=True, room="test"))
        jwt = token.to_jwt()
        return True, f"OK - Token generated ({len(jwt)} chars)"
    except Exception as e:
        return False, f"Error: {str(e)[:50]}"


def main():
    print("=" * 60)
    print("HVAC Copilot - Setup Verification")
    print("=" * 60)
    print()

    # Check environment variables
    print("Environment Variables:")
    print("-" * 40)

    env_checks = [
        ("GOOGLE_API_KEY", True),
        ("SUPABASE_URL", True),
        ("SUPABASE_ANON_KEY", True),
        ("LIVEKIT_URL", True),
        ("LIVEKIT_API_KEY", True),
        ("LIVEKIT_API_SECRET", True),
        ("STRIPE_SECRET_KEY", False),
        ("OPENAI_API_KEY", False),
    ]

    all_required_set = True
    for name, required in env_checks:
        ok, value = check_env_var(name, required)
        status = "✓" if ok else ("✗" if required else "○")
        req_label = "(required)" if required else "(optional)"
        print(f"  {status} {name}: {value} {req_label}")
        if required and not ok:
            all_required_set = False

    print()

    if not all_required_set:
        print("⚠️  Some required variables are not set.")
        print("   Copy .env.example to .env and fill in your values.")
        print()
        return 1

    # Test connections
    print("Service Connections:")
    print("-" * 40)

    tests = [
        ("Google/Gemini API", test_google_api),
        ("Supabase", test_supabase),
        ("LiveKit", test_livekit),
    ]

    all_ok = True
    for name, test_func in tests:
        try:
            ok, message = test_func()
            status = "✓" if ok else "✗"
            print(f"  {status} {name}: {message}")
            if not ok:
                all_ok = False
        except Exception as e:
            print(f"  ✗ {name}: Exception - {str(e)[:40]}")
            all_ok = False

    print()
    print("=" * 60)

    if all_ok:
        print("✓ All checks passed! Ready to run the server.")
        print()
        print("Next steps:")
        print("  1. Run Supabase migrations (if not done):")
        print("     - Go to Supabase Dashboard > SQL Editor")
        print("     - Paste contents of backend/db/migrations/001_initial_schema.sql")
        print("     - Click 'Run'")
        print()
        print("  2. Start the API server:")
        print("     cd backend && uvicorn api.main:app --reload")
        print()
        print("  3. Start the LiveKit agent (in another terminal):")
        print("     cd backend && python -m agent.hvac_agent dev")
        return 0
    else:
        print("✗ Some checks failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
